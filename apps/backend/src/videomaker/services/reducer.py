"""Kartoziya Stage 5.4 — Reducer (Jaccard dedup + LLM composite ranking).

Вход: `ExtractionResult` (плоский список `EvidenceItem` от всех 6 агентов × N chunks).
Выход: `RankedEvidence` (максимум 60 items, сортировка по composite_score).

Алгоритм состоит из двух частей:
1. **Deterministic part** — dedup по |Δstart| < 3s + rough-Jaccard > 0.5, оставляем
   сильнейший. O(N) по window-scan последних 5 keeper'ов.
2. **LLM part** — Flash ранжирует deduped evidence с учётом Canvas темы и
   категорию: hook/peak/payoff/development/cutaway. При LLM-сбое fallback'ит
   на heuristic по агент-категориям.
"""

from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass
from typing import Literal, cast

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import (
    AgentName,
    EvidenceItem,
    RankedEvidence,
    RankedEvidenceItem,
)
from videomaker.services.agents.orchestrator import ExtractionResult
from videomaker.services.canvas_embedder import cosine_similarity, embed_texts
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.prompts import (
    REDUCE_RANK_PROMPT,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter

log = get_logger(__name__)

Category = Literal[
    "hook_candidate",
    "peak_candidate",
    "payoff_candidate",
    "development_material",
    "cutaway_material",
]

DEDUP_WINDOW_SEC = 3.0
MERGE_GAP_SEC = 15.0

#: Hybrid-dedup threshold: два evidence-итема считаются семантическими
#: дубликатами (перефразами одной мысли) если cosine(embedding_a, b) >= 0.80.
#: Калиброван эмпирически для gemini-embedding-001 task=SEMANTIC_SIMILARITY
#: и коротких русских фраз. Jaccard остаётся как fallback для items без
#: embedding (API-fallback или пустой текст).
SEMANTIC_DEDUP_THRESHOLD = 0.80

#: Нижняя граница ranked-pool (защищает 20-30-минутные видео от случайно
#: маленьких чисел). Верхняя — потолок, больше которого Flash Lite начинает
#: обрезать JSON независимо от `max_tokens` (эмпирически ~300 items).
_RANKED_CAP_MIN = 60
_RANKED_CAP_MAX = 300

#: LLM_RANK_INPUT_CAP — сколько top-N evidence по strength отдаём LLM-ранжировщику.
#: Нижняя граница = 80 (прежнее поведение для коротких видео). Верхняя = 400
#: (Flash Lite держит, Pro не используем — слишком дорого на длинных).
_INPUT_CAP_MIN = 80
_INPUT_CAP_MAX = 400

#: Если LLM-ранжировщик вернул меньше этого минимума — дополняем через
#: heuristic fallback из deduped pool. Защищает пайплайн от single-item
#: сценария когда LLM обрезал/сломал JSON.
MIN_RANKED_ITEMS_FROM_LLM = 20


def _compute_rank_caps(source_duration_sec: float) -> tuple[int, int]:
    """Линейно масштабирует ranked+input cap'ы по длительности источника.

    Мотивация: `MAX_RANKED_ITEMS` и `LLM_RANK_INPUT_CAP` раньше были hardcoded
    под 20-30-минутное видео. На 2.5-часовом материале это отрезало реальные
    кандидаты — reducer выдавал ровно 60 ranked, хотя evidence-pool после
    dedup был 250+. Таргет слайдер стал недостижим физически.

    Формула: 2.0 items на минуту источника → 150 мин = 300 ranked. Вход
    ranker-у — 2.5 items/мин (чтобы было из чего выбирать) → 150 мин = 375.
    Для ≤ 30 мин видео обе константы остаются 60/80 (baseline-инвариант).
    """
    duration_min = max(0.0, source_duration_sec / 60.0)
    ranked_cap = max(_RANKED_CAP_MIN, min(_RANKED_CAP_MAX, round(duration_min * 2.0)))
    input_cap = max(_INPUT_CAP_MIN, min(_INPUT_CAP_MAX, round(duration_min * 2.5)))
    return ranked_cap, input_cap


@dataclass(slots=True)
class ReduceResult:
    ranked: RankedEvidence
    pre_dedup_count: int = 0
    post_dedup_count: int = 0


async def reduce_and_rank(
    extraction: ExtractionResult,
    canvas: ProjectCanvas,
    *,
    source_duration_sec: float,
    client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    ensemble_size: int = 1,
    ensemble_veto_threshold: int = 2,
    pipeline_provider: str | None = None,
) -> ReduceResult:
    """Полный pipeline: deterministic dedup → LLM ranking (+ fallback).

    `source_duration_sec` задаёт динамические cap'ы: короткое видео берёт
    дефолтные 60/80, длинное — до 300/400. Без этого длинное видео (1h+)
    никогда не дойдёт до target_reel_count выше 60.

    TIER2-#12: `ensemble_size > 1` → N параллельных вызовов с разной
    temperature (0.1…0.3), median-агрегация composite_score, minority
    veto (item включается только если за него проголосовало >=
    `ensemble_veto_threshold` судей). +7-10 pp scoring accuracy по
    research Q4 (RewardBench 2 bench).
    """
    ranked_cap, input_cap = _compute_rank_caps(source_duration_sec)
    if not extraction.evidence:
        return ReduceResult(ranked=RankedEvidence())

    pre = len(extraction.evidence)

    # T1.1 slice 2: hybrid dedup. Embed'им evidence ДО dedup; _dedup_hybrid
    # использует cosine similarity (порог 0.80) как первичный критерий и
    # Jaccard как fallback для items без embedding. Перефразы одной мысли
    # от разных агентов (напр. hook_hunter и humor_specialist поймали один
    # punchline, но разным текстом) теперь ловятся в dedup, а не тащатся в
    # LLM-ранжировщик.
    cfg_for_embed = get_settings()
    evidence_embedded = await _enrich_evidence_with_embeddings(
        extraction.evidence, settings=cfg_for_embed
    )

    deduped = _dedup_hybrid(evidence_embedded)
    deduped_count = len(deduped)
    log.info(
        "evidence_deduped",
        before=pre,
        after=deduped_count,
        ranked_cap=ranked_cap,
        input_cap=input_cap,
        semantic_available=sum(1 for e in evidence_embedded if e.embedding is not None),
    )

    if not deduped:
        return ReduceResult(ranked=RankedEvidence(), pre_dedup_count=pre)

    # LLM-ранжировщик получает топ-N по strength (не весь pool). На 200+ items
    # Flash обрезает JSON-output → возвращает 1-2 записи. Обрезаем вход чтобы
    # каждый item поместился в output + буфер на reasoning.
    deduped_sorted = sorted(deduped, key=lambda e: e.strength, reverse=True)
    llm_input = deduped_sorted[:input_cap]

    cfg = get_settings()
    llm = client or build_llm_for_tier("flash", cfg, provider_override=pipeline_provider)
    limiter = rate_limiter or get_gemini_rate_limiter()

    system_prompt = (
        f"{build_system_prompt()}\n\n"
        f"{canvas.to_llm_context()}\n\n{REDUCE_RANK_PROMPT}"
    )
    user_payload = _render_evidence_for_llm(llm_input)

    if ensemble_size > 1:
        ranked = await _run_ensemble_reduce(
            llm=llm,
            limiter=limiter,
            system=system_prompt,
            user=user_payload,
            source=llm_input,
            full_source=deduped,
            ranked_cap=ranked_cap,
            ensemble_size=min(ensemble_size, 5),
            veto_threshold=max(1, min(ensemble_veto_threshold, ensemble_size)),
        )
    else:
        async with limiter.acquire():
            try:
                response = await llm.complete_json(
                    system=system_prompt,
                    user=user_payload,
                    temperature=cfg.reducer_temperature,
                    max_tokens=cfg.reducer_max_tokens,
                )
                parsed = parse_json_response(response.text)
            except LLMError as exc:
                log.warning("reduce_llm_failed", error=str(exc))
                return ReduceResult(
                    ranked=_fallback_ranked_evidence(deduped, ranked_cap=ranked_cap),
                    pre_dedup_count=pre,
                    post_dedup_count=deduped_count,
                )

        ranked = _parse_reduce_output(
            parsed, llm_input, full_source=deduped, ranked_cap=ranked_cap
        )
    log.info(
        "reduce_done",
        pre_dedup=pre,
        post_dedup=deduped_count,
        llm_input=len(llm_input),
        ranked_final=len(ranked.items),
    )
    return ReduceResult(
        ranked=ranked,
        pre_dedup_count=pre,
        post_dedup_count=deduped_count,
    )


async def _enrich_evidence_with_embeddings(
    items: list[EvidenceItem],
    *,
    settings: Settings,
) -> list[EvidenceItem]:
    """Batch-embed текста каждого evidence через gemini-embedding-001.

    Возвращает новый список items с populated ``embedding``. При сбое API
    возвращает items как есть (embedding=None), и hybrid-dedup откатывается
    на чистый Jaccard — функционально эквивалентно legacy-поведению.
    """
    if not items:
        return []

    texts = [item.text or "" for item in items]
    embeddings = await embed_texts(texts, settings=settings)
    if embeddings is None or len(embeddings) != len(items):
        return items

    enriched: list[EvidenceItem] = []
    for item, emb in zip(items, embeddings, strict=True):
        if not emb:
            enriched.append(item)
            continue
        enriched.append(item.model_copy(update={"embedding": emb}))
    return enriched


def _dedup_hybrid(items: list[EvidenceItem]) -> list[EvidenceItem]:
    """Hybrid dedup: time-window (3s) × (cosine >= 0.80 OR Jaccard >= 0.5).

    Критерий похожести текста двухступенчатый:

    1. Если у обоих items есть ``embedding`` → cosine similarity (≥ 0.80
       катит дубликат). Ловит перефразы одной мысли разными агентами.
    2. Иначе (любой из items без embedding, API fallback) → Jaccard на
       словах (≥ 0.5) для graceful-degrade.

    Сортировка: по start ASC, при равенстве — по strength DESC (сильнейший
    первый — оседает keeper'ом). Window-scan последних 5 keeper'ов — O(N).
    """
    if not items:
        return []

    sorted_items = sorted(items, key=lambda e: (e.start, -e.strength))
    result: list[EvidenceItem] = []

    for item in sorted_items:
        is_dup = False
        for keeper in result[-5:]:
            if abs(keeper.start - item.start) >= DEDUP_WINDOW_SEC:
                continue
            if _items_semantically_duplicate(keeper, item):
                is_dup = True
                if item.strength > keeper.strength:
                    result[result.index(keeper)] = item
                break
        if not is_dup:
            result.append(item)

    return result


def _items_semantically_duplicate(a: EvidenceItem, b: EvidenceItem) -> bool:
    """True если два items говорят об одной мысли (hybrid critic)."""
    if a.embedding is not None and b.embedding is not None:
        sim = cosine_similarity(a.embedding, b.embedding)
        if sim >= SEMANTIC_DEDUP_THRESHOLD:
            return True
        # Даже если semantic ниже порога, очень близкие по Jaccard тоже
        # катят как дубликат (напр. цитата от двух агентов одним текстом,
        # но embedding разошёлся из-за разницы в one-hot контексте).
        return _text_similarity_rough(a.text, b.text) >= 0.7
    # Fallback для отсутствующих embeddings — legacy-порог 0.5.
    return _text_similarity_rough(a.text, b.text) >= 0.5


def _build_embedding_index(
    items: list[EvidenceItem],
) -> dict[tuple[float, str], list[float]]:
    """Строит lookup ``(round(start,1), text[:80]) → embedding`` из evidence.

    Используется при формировании RankedEvidenceItem чтобы не делать
    повторный embed-вызов: embeddings уже посчитаны в
    `_enrich_evidence_with_embeddings` перед dedup. Если LLM-ranker
    вернул текст идентичный source evidence — находим по ключу и копируем
    embedding; если текст переформулирован (редкий случай) — embedding
    останется None, downstream semantic-retrieval graceful-degrade.
    """
    index: dict[tuple[float, str], list[float]] = {}
    for item in items:
        if item.embedding is None:
            continue
        key = (round(item.start, 1), (item.text or "")[:80])
        index[key] = item.embedding
    return index


def _lookup_embedding(
    index: dict[tuple[float, str], list[float]],
    start: float,
    text: str,
) -> list[float] | None:
    """Возвращает embedding если evidence с таким же (start, text) уже был embed'нут."""
    if not index:
        return None
    return index.get((round(start, 1), (text or "")[:80]))


def _text_similarity_rough(a: str, b: str) -> float:
    """Быстрый rough Jaccard на словах. Достаточно для near-duplicates."""
    if not a or not b:
        return 0.0
    set_a = set(a.lower().split())
    set_b = set(b.lower().split())
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _render_evidence_for_llm(items: list[EvidenceItem]) -> str:
    """Компактное JSON-like представление для LLM."""
    lines: list[str] = ["=== EVIDENCE POOL ==="]
    for i, item in enumerate(items):
        agent_type = item.agent_specific_type or "generic"
        theme = f" theme={item.theme_id}" if item.theme_id else ""
        speaker = f" speaker={item.speaker}" if item.speaker else ""
        lines.append(
            f"[e{i}] agent={item.source_agent}/{agent_type} "
            f"{item.start:.1f}-{item.end:.1f}s "
            f"strength={item.strength:.2f}{theme}{speaker}\n"
            f"  text: {item.text[:250]}"
        )
    return "\n".join(lines)


async def _run_ensemble_reduce(
    *,
    llm: LLMClient,
    limiter: RateLimiter,
    system: str,
    user: str,
    source: list[EvidenceItem],
    full_source: list[EvidenceItem],
    ranked_cap: int,
    ensemble_size: int,
    veto_threshold: int,
) -> RankedEvidence:
    """TIER2-#12: N параллельных judge-вызовов + median-агрегация + veto.

    Temperatures разбросаны равномерно в [0.1, 0.3] — даёт разные
    генерации на одном input без потери quality (≤0.3 — safe для JSON).
    Veto: item попадает в финал только если за него проголосовало
    >= `veto_threshold` судей из ensemble.
    """

    if ensemble_size < 2:
        raise ValueError("ensemble_size must be >= 2 for ensemble mode")

    cfg = get_settings()
    temperatures = [
        0.1 + (i * (0.3 - 0.1)) / max(1, ensemble_size - 1)
        for i in range(ensemble_size)
    ]

    async def _one(temp: float) -> RankedEvidence | None:
        async with limiter.acquire():
            try:
                response = await llm.complete_json(
                    system=system,
                    user=user,
                    temperature=temp,
                    max_tokens=cfg.reducer_max_tokens,
                )
                parsed = parse_json_response(response.text)
            except LLMError as exc:
                log.warning("reduce_ensemble_call_failed", temp=temp, error=str(exc))
                return None
        return _parse_reduce_output(
            parsed, source, full_source=full_source, ranked_cap=ranked_cap
        )

    results = await asyncio.gather(*(_one(t) for t in temperatures))
    valid = [r for r in results if r is not None and r.items]
    if not valid:
        log.warning("reduce_ensemble_all_failed", ensemble_size=ensemble_size)
        return _fallback_ranked_evidence(full_source, ranked_cap=ranked_cap)

    aggregated = _aggregate_ensemble_votes(
        valid, ranked_cap=ranked_cap, veto_threshold=veto_threshold
    )
    log.info(
        "reduce_ensemble_done",
        judges=len(valid),
        expected=ensemble_size,
        veto_threshold=veto_threshold,
        final_items=len(aggregated.items),
    )
    return aggregated


def _aggregate_ensemble_votes(
    ranked_list: list[RankedEvidence],
    *,
    ranked_cap: int,
    veto_threshold: int,
) -> RankedEvidence:
    """Median composite_score + minority veto.

    Ключ item'а: ``(round(start,1), round(end,1), normalized_text_prefix)``
    — устойчив к мелким float-колебаниям в LLM-output. Veto: меньше
    ``veto_threshold`` голосов → item отбрасывается (считаем его
    fluke-ом одного судьи).
    """

    votes: dict[tuple[float, float, str], list[tuple[float, RankedEvidenceItem]]] = {}
    for ranked in ranked_list:
        for item in ranked.items:
            key = (
                round(item.start, 1),
                round(item.end, 1),
                item.text.strip().lower()[:50],
            )
            votes.setdefault(key, []).append((item.composite_score, item))

    finalists: list[RankedEvidenceItem] = []
    for pairs in votes.values():
        if len(pairs) < veto_threshold:
            continue
        scores = [p[0] for p in pairs]
        median_score = statistics.median(scores)
        # Берём первого голосующего как representative (у него заполнены
        # все поля). Median применяем только к composite_score.
        repr_item = pairs[0][1]
        finalists.append(
            RankedEvidenceItem(
                id=repr_item.id,
                source_agent=repr_item.source_agent,
                start=repr_item.start,
                end=repr_item.end,
                text=repr_item.text,
                speaker=repr_item.speaker,
                theme_id=repr_item.theme_id,
                motif_id=repr_item.motif_id,
                category=repr_item.category,
                composite_score=median_score,
                reasoning=(
                    f"[ensemble n={len(pairs)}, median={median_score:.2f}] "
                    f"{repr_item.reasoning}"
                ),
            )
        )

    finalists.sort(key=lambda x: -x.composite_score)
    return RankedEvidence(items=finalists[:ranked_cap])


def _parse_reduce_output(
    data: object,
    source: list[EvidenceItem],
    *,
    full_source: list[EvidenceItem] | None = None,
    ranked_cap: int,
) -> RankedEvidence:
    """Парсит LLM-output в `RankedEvidence`.

    Если LLM вернул `< MIN_RANKED_ITEMS_FROM_LLM`, дополняем heuristic-
    fallback'ом из `full_source` (полный deduped pool) по strength —
    чтобы не получить 1-2 рилса на 30-минутном видео.

    `ranked_cap` масштабируется по длительности источника — см.
    `_compute_rank_caps`.
    """
    backfill_source = full_source if full_source is not None else source

    if not isinstance(data, dict):
        log.warning("reduce_output_not_dict")
        return _fallback_ranked_evidence(backfill_source, ranked_cap=ranked_cap)

    raw_items = data.get("ranked_evidence") or []
    if not isinstance(raw_items, list):
        return _fallback_ranked_evidence(backfill_source, ranked_cap=ranked_cap)

    # T1.1 slice 3: lookup embedding из уже заполненных source-evidence
    # (после hybrid-dedup). Match по (round(start,1), text[:80]).
    embedding_index = _build_embedding_index(source)

    ranked_items: list[RankedEvidenceItem] = []
    for i, raw in enumerate(raw_items[:ranked_cap]):
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text", "")).strip()
        if not text:
            continue
        try:
            start = float(raw.get("start", 0.0))
            end = float(raw.get("end", start))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue

        category = _normalize_category(raw.get("category"))
        try:
            score = max(0.0, min(1.0, float(raw.get("composite_score", 0.5))))
        except (TypeError, ValueError):
            score = 0.5

        source_agent = raw.get("source_agent")
        if source_agent not in {
            "hook_hunter", "emotional_peak_finder", "humor_specialist",
            "dramatic_irony_scanner", "thesis_extractor", "motif_tracker",
        }:
            source_agent = source[0].source_agent if source else "thesis_extractor"

        ranked_items.append(
            RankedEvidenceItem(
                id=str(raw.get("id", f"r{i}")),
                source_agent=cast(AgentName, source_agent),
                start=max(0.0, start),
                end=max(start, end),
                text=text,
                speaker=raw.get("speaker"),
                theme_id=raw.get("theme_id"),
                motif_id=raw.get("motif_id"),
                category=category,
                composite_score=score,
                reasoning=str(raw.get("reasoning", "")).strip(),
                embedding=_lookup_embedding(embedding_index, start, text),
            )
        )

    # Backfill если LLM обрезал output или вернул слишком мало.
    if len(ranked_items) < MIN_RANKED_ITEMS_FROM_LLM and backfill_source:
        _backfill_from_source(ranked_items, backfill_source, ranked_cap=ranked_cap)
        log.warning(
            "reduce_backfilled_from_source",
            llm_returned=len(ranked_items),
            min_expected=MIN_RANKED_ITEMS_FROM_LLM,
            source_pool=len(backfill_source),
        )

    ranked_items.sort(key=lambda e: e.composite_score, reverse=True)

    return RankedEvidence(
        deduped_count=int(data.get("deduped_count", len(backfill_source))),
        merged_scene_count=int(data.get("merged_scene_count", 0)),
        items=ranked_items,
    )


def _backfill_from_source(
    ranked_items: list[RankedEvidenceItem],
    source: list[EvidenceItem],
    *,
    ranked_cap: int,
) -> None:
    """Дополняет ranked_items из source по strength, избегая дубликатов.

    Дубликат определяется по |Δstart| < 1s (грубо, но в нашем pool'е достаточно).
    Добавляет до достижения `ranked_cap`.
    """
    taken_starts = {round(r.start, 1) for r in ranked_items}
    remaining_slots = ranked_cap - len(ranked_items)
    if remaining_slots <= 0:
        return

    sorted_source = sorted(source, key=lambda e: e.strength, reverse=True)
    added = 0
    for e in sorted_source:
        if added >= remaining_slots:
            break
        if round(e.start, 1) in taken_starts:
            continue
        taken_starts.add(round(e.start, 1))
        ranked_items.append(
            RankedEvidenceItem(
                id=f"bf{added}",
                source_agent=e.source_agent,
                start=e.start,
                end=e.end,
                text=e.text,
                speaker=e.speaker,
                theme_id=e.theme_id,
                motif_id=e.motif_id,
                category=_category_for_agent(e.source_agent),
                composite_score=e.strength,
                reasoning=e.reasoning or "backfilled from heuristic source pool",
                embedding=e.embedding,
            )
        )
        added += 1


def _normalize_category(value: object) -> Category:
    s = str(value or "").lower().strip()
    if s in {
        "hook_candidate", "peak_candidate", "payoff_candidate",
        "development_material", "cutaway_material",
    }:
        return cast(Category, s)
    return "development_material"


def _fallback_ranked_evidence(
    source: list[EvidenceItem],
    *,
    ranked_cap: int,
) -> RankedEvidence:
    """Если LLM ranking провалился — ranking as-is по strength."""
    sorted_src = sorted(
        source, key=lambda e: e.strength, reverse=True
    )[:ranked_cap]
    items = [
        RankedEvidenceItem(
            id=f"r{i}",
            source_agent=e.source_agent,
            start=e.start,
            end=e.end,
            text=e.text,
            speaker=e.speaker,
            theme_id=e.theme_id,
            motif_id=e.motif_id,
            category=_category_for_agent(e.source_agent),
            composite_score=e.strength,
            reasoning=e.reasoning,
            embedding=e.embedding,
        )
        for i, e in enumerate(sorted_src)
    ]
    return RankedEvidence(
        deduped_count=len(source),
        merged_scene_count=0,
        items=items,
    )


def _category_for_agent(agent: str) -> Category:
    """Fallback category без LLM — на основе агента-автора."""
    mapping: dict[str, Category] = {
        "hook_hunter": "hook_candidate",
        "emotional_peak_finder": "peak_candidate",
        "humor_specialist": "cutaway_material",
        "dramatic_irony_scanner": "development_material",
        "thesis_extractor": "development_material",
        "motif_tracker": "payoff_candidate",
    }
    return mapping.get(agent, "development_material")
