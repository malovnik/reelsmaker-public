"""Kartoziya Stage 5.5 — Story Doctor (3-act arc с book-end symmetry).

Один Gemini Pro-вызов: Canvas + RankedEvidence → StoryScript.
Ключевая задача — связать HOOK в начале с PAYOFF в финале через общий motif
(book-end). Это требование Картозии: "одна арка = одна мысль".

При LLM-сбое — fallback: собираем простой arc по категориям ranked evidence.
"""

from __future__ import annotations

import collections

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import RankedEvidence, RankedEvidenceItem
from videomaker.models.story_script import (
    AlternateSegment,
    StoryScript,
    StorySegment,
)
from videomaker.services.canvas_embedder import cosine_similarity, embed_texts
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.prompts import (
    STORY_DOCTOR_PROMPT,
    STORY_DOCTOR_TRAVEL_PROMPT,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter

log = get_logger(__name__)

VALID_ROLES = {"hook", "setup", "development", "peak", "payoff"}
VALID_BEATS = {"strain", "relief", "reveal", "triumph", "neutral"}

#: Retrieval query для поиска альтернативных payoff'ов. Описывает
#: драматургический профиль "сильной концовки" — terminal tone,
#: круговая связь с hook, ясный вывод. Embedding этой фразы
#: (SEMANTIC_SIMILARITY) сравнивается с embeddings ranked.items,
#: топ-K по cosine добавляется как alternates.
_CLOSURE_RETRIEVAL_QUERY = (
    "Завершающая мысль. Финальный аккорд. Круговая связь — "
    "возврат к теме начала. Resolution, итог, точка, вывод. "
    "Ощущение завершённости: мысль закрыта, зритель получил payoff."
)

#: Min cosine для признания кандидата семантически релевантным payoff.
#: Ниже — не добавляем (меньше шума в alternates).
_CLOSURE_RETRIEVAL_MIN_COSINE = 0.50

#: Сколько retrieval-based alternates максимум добавляем в script.
#: Выше 3 захламляет pool для closure_validator, ниже — маловат выбор.
_CLOSURE_RETRIEVAL_TOP_K = 3


async def compose_story_script(
    canvas: ProjectCanvas,
    ranked: RankedEvidence,
    *,
    client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    mode: str = "dialogue",
    rhythm_critique: str | None = None,
    pipeline_provider: str | None = None,
    min_arc_segments: int = 3,
    min_arc_duration_sec: float = 20.0,
) -> StoryScript:
    """Собирает 3-act arc через Pro. Пустой evidence → пустой script.

    `mode` ∈ {"dialogue", "travel"}. Dialogue — default, visual-aware prompt из
    Phase 3. Travel — caption-first prompt из Phase 6 (когда транскрипт минимальный).

    `rhythm_critique` (T1.3) — текст ритмической критики от предыдущей итерации.
    Если задан — инжектится в user payload как префикс: «Предыдущая версия имела
    следующие проблемы ритма: ...». Используется в pipeline при rhythm_score <
    порога для переделки арки с явным указанием что исправить.

    `min_arc_segments` / `min_arc_duration_sec` — quality gate для fallback
    trigger. Default (3 / 20s) подходит для legacy single-arc mode где arc
    покрывает всё видео. В multi_arc mode (multi_arc_builder вызывает per-moment)
    evidence window узкий, LLM строит валидные мини-арки из 1-2 segments
    30-40s — default threshold ошибочно триггерит fallback, который собирает
    evidence со всего видео (нарушая тему moment'а). Caller из multi_arc
    передаёт loose values (1 / 10s) → LLM output сохраняется, fallback
    триггерится только при полном LLM failure (exception path).
    """
    if not ranked.items:
        log.warning("story_doctor_no_evidence")
        return StoryScript(central_theme=canvas.central_theme)

    cfg = get_settings()
    llm = client or build_llm_for_tier("pro", cfg, provider_override=pipeline_provider)
    limiter = rate_limiter or get_gemini_rate_limiter()

    ranked_payload = _render_ranked_for_llm(ranked)
    user_payload = (
        f"{rhythm_critique}\n\n{ranked_payload}"
        if rhythm_critique
        else ranked_payload
    )
    prompt = STORY_DOCTOR_TRAVEL_PROMPT if mode == "travel" else STORY_DOCTOR_PROMPT
    system = f"{build_system_prompt()}\n\n{canvas.to_llm_context()}\n\n{prompt}"

    async with limiter.acquire():
        try:
            response = await llm.complete_json(
                system=system,
                user=user_payload,
                temperature=0.4,
                max_tokens=16000,
                # TIER1-#10: Story Doctor строит 3-act arc + payoff-связки —
                # reasoning нужен обязательно, 512 токенов запас для дискуссии
                # alternatives перед финальным решением.
                thinking_budget=512,
            )
            parsed = parse_json_response(response.text)
        except LLMError as exc:
            log.warning("story_doctor_failed", error=str(exc), mode=mode)
            return _fallback_script(canvas, ranked)

    if not isinstance(parsed, dict):
        return _fallback_script(canvas, ranked)

    script = _parse_story_script(parsed, ranked)

    # Quality gate: параметризован через min_arc_segments / min_arc_duration_sec.
    # Defaults (3 / 20s) — для legacy single-arc где arc покрывает всё видео
    # и должна быть полной. Multi_arc caller передаёт loose (1 / 10s) т.к.
    # per-moment LLM arc коротка by design. Без этой проверки parsed script=[]
    # проскальзывает в composer и ломает base_arc ветку (deградация в
    # evidence_single). Fallback_script берёт evidence со ВСЕГО видео — в
    # multi_arc это разрушает тему moment'а, поэтому threshold ослаблен.
    arc_too_short = (
        len(script.arc) < min_arc_segments
        or sum(s.duration_sec for s in script.arc) < min_arc_duration_sec
    )
    if arc_too_short:
        log.warning(
            "story_doctor_arc_too_short",
            arc_len=len(script.arc),
            duration_sec=round(
                sum(s.duration_sec for s in script.arc), 1
            ),
            roles=dict(
                collections.Counter(s.role for s in script.arc)
            ),
        )
        fallback = _fallback_script(canvas, ranked)
        if len(fallback.arc) > len(script.arc):
            log.info(
                "story_doctor_using_fallback_script",
                fallback_arc_len=len(fallback.arc),
                fallback_duration=round(fallback.predicted_duration_sec, 1),
            )
            script = fallback

    # T1.1 slice 3: semantic retrieval для augmentation alternates.
    # Embed'им closure-query, ищем top-3 семантически близких payoff
    # кандидатов в ranked.items и добавляем как AlternateSegment.
    # Downstream closure_validator / composer может подменять слабую концовку.
    script = await _augment_alternates_via_retrieval(script, ranked, settings=cfg)

    log.info(
        "story_doctor_done",
        mode=mode,
        arc_len=len(script.arc),
        duration_sec=script.predicted_duration_sec,
        bookend_motif=script.bookend_motif_id,
        visual_bookend=script.visual_bookend_motif,
        alternates=len(script.alternates),
    )
    return script


async def _augment_alternates_via_retrieval(
    script: StoryScript,
    ranked: RankedEvidence,
    *,
    settings: Settings,
    top_k: int = _CLOSURE_RETRIEVAL_TOP_K,
    min_cosine: float = _CLOSURE_RETRIEVAL_MIN_COSINE,
) -> StoryScript:
    """Обогащает ``script.alternates`` retrieval-based payoff кандидатами.

    Алгоритм:
    1. Embed query ``_CLOSURE_RETRIEVAL_QUERY``.
    2. Считаем cosine(query, item.embedding) для всех ranked items с
       ``category=payoff_candidate`` которые ещё не в ``arc``/``alternates``.
    3. Top-K по cosine, отсекаем ниже ``min_cosine``, добавляем как
       ``AlternateSegment(role_substitute="payoff")``.

    Graceful-degrade: при сбое embed API или отсутствии payoff-candidate
    items с embedding возвращаем script без изменений.
    """
    if not ranked.items:
        return script

    used_ids: set[str] = {s.evidence_id for s in script.arc if s.evidence_id}
    used_ids.update(a.evidence_id for a in script.alternates if a.evidence_id)

    candidates = [
        item
        for item in ranked.items
        if item.category == "payoff_candidate"
        and item.id not in used_ids
        and item.embedding is not None
    ]
    if not candidates:
        log.info("closure_retrieval_skipped_no_payoff_candidates")
        return script

    query_embeddings = await embed_texts(
        [_CLOSURE_RETRIEVAL_QUERY],
        settings=settings,
    )
    if not query_embeddings or not query_embeddings[0]:
        log.warning("closure_retrieval_query_embed_failed")
        return script

    query_vec = query_embeddings[0]

    scored: list[tuple[float, RankedEvidenceItem]] = [
        (cosine_similarity(query_vec, c.embedding), c) for c in candidates
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    new_alternates = list(script.alternates)
    added = 0
    for sim, item in scored:
        if sim < min_cosine or added >= top_k:
            break
        new_alternates.append(
            AlternateSegment(
                role_substitute="payoff",
                evidence_id=item.id,
                reason=f"semantic retrieval closure candidate (cosine {sim:.2f})",
            )
        )
        added += 1

    if added > 0:
        log.info(
            "closure_retrieval_augmented",
            added=added,
            total_alternates=len(new_alternates),
            top_cosine=round(scored[0][0], 3) if scored else 0.0,
        )

    return script.model_copy(update={"alternates": new_alternates})


def _render_ranked_for_llm(ranked: RankedEvidence) -> str:
    lines: list[str] = ["=== RANKED EVIDENCE ==="]
    for item in ranked.items:
        theme = f" theme={item.theme_id}" if item.theme_id else ""
        motif = f" motif={item.motif_id}" if item.motif_id else ""
        speaker = f" speaker={item.speaker}" if item.speaker else ""
        lines.append(
            f"[{item.id}] {item.category} score={item.composite_score:.2f} "
            f"{item.start:.1f}-{item.end:.1f}s{theme}{motif}{speaker}\n"
            f"  text: {item.text[:300]}"
        )
    return "\n".join(lines)


def _parse_story_script(data: dict, ranked: RankedEvidence) -> StoryScript:
    evidence_map = {e.id: e for e in ranked.items}

    arc_items: list[StorySegment] = []
    for raw in data.get("arc") or []:
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role", "")).lower()
        if role not in VALID_ROLES:
            continue

        evidence_id = raw.get("evidence_id")
        evidence = evidence_map.get(str(evidence_id)) if evidence_id else None

        try:
            start = float(raw.get("source_start_sec", evidence.start if evidence else 0.0))
            end = float(
                raw.get(
                    "source_end_sec",
                    evidence.end if evidence else start + 1.0,
                )
            )
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue

        beat = str(raw.get("emotional_beat", "neutral")).lower()
        if beat not in VALID_BEATS:
            beat = "neutral"

        text_preview = evidence.text[:200] if evidence else str(raw.get("text_preview", ""))[:200]

        payoff_conclusion_raw = raw.get("payoff_conclusion")
        payoff_conclusion = (
            str(payoff_conclusion_raw).strip()
            if role == "payoff" and payoff_conclusion_raw
            else None
        )
        arc_items.append(
            StorySegment(
                role=role,  # type: ignore[arg-type]
                evidence_id=str(evidence_id or ""),
                source_start_sec=max(0.0, start),
                source_end_sec=max(start, end),
                speaker=(raw.get("speaker") or (evidence.speaker if evidence else None)),
                reasoning=str(raw.get("reasoning", "")).strip(),
                emotional_beat=beat,  # type: ignore[arg-type]
                text_preview=text_preview,
                payoff_conclusion=payoff_conclusion,
            )
        )

    alternates: list[AlternateSegment] = []
    for raw in data.get("alternates") or []:
        if not isinstance(raw, dict):
            continue
        sub_role = str(raw.get("role_substitute", "")).lower()
        if sub_role not in VALID_ROLES:
            continue
        alternates.append(
            AlternateSegment(
                role_substitute=sub_role,  # type: ignore[arg-type]
                evidence_id=str(raw.get("evidence_id", "")),
                reason=str(raw.get("reason", "")).strip(),
            )
        )

    try:
        predicted_duration = float(data.get("predicted_duration_sec", 0.0))
    except (TypeError, ValueError):
        predicted_duration = sum(s.duration_sec for s in arc_items)

    visual_motif_raw = data.get("visual_bookend_motif")
    if isinstance(visual_motif_raw, str) and visual_motif_raw.strip():
        visual_motif = visual_motif_raw.strip()
    else:
        visual_motif = None

    return StoryScript(
        central_theme=str(data.get("central_theme", "")).strip(),
        bookend_motif_id=data.get("bookend_motif_id") or None,
        bookend_reasoning=str(data.get("bookend_reasoning", "")).strip(),
        visual_bookend_motif=visual_motif,
        arc=arc_items,
        alternates=alternates,
        predicted_duration_sec=max(0.0, predicted_duration),
    )


def _fallback_script(canvas: ProjectCanvas, ranked: RankedEvidence) -> StoryScript:
    """Fallback при LLM-провале Story Doctor — собираем 5-7 segment arc
    из ranked evidence по категориям.

    Структура arc:
      hook → setup (2x) → development (1x) → peak (1-2x) → payoff (1x)
    Минимум 5 сегментов, максимум 7 — достаточно для base_arc candidate
    и composer dramatic-flow. Development'ов 1-2 даёт Pass 3 conditional
    что thin_arc_count нулевой → не тянет сверх меры.

    Deduplication: одинаковый evidence_id не попадает в arc дважды
    (возможно если evidence попадает под несколько категорий).
    """
    seen: set[str] = set()

    def _take(category: str, n: int) -> list[RankedEvidenceItem]:
        picked: list[RankedEvidenceItem] = []
        for item in ranked.by_category(category):  # type: ignore[arg-type]
            if item.id in seen:
                continue
            seen.add(item.id)
            picked.append(item)
            if len(picked) >= n:
                break
        return picked

    hooks = _take("hook_candidate", 1)
    setups = _take("development_material", 2)
    devs = _take("development_material", 1)  # ещё один после setups
    peaks = _take("peak_candidate", 2)
    payoffs = _take("payoff_candidate", 1)

    # Если какой-то категории пусто — подбираем из cutaway_material чтобы
    # держать ≥5 segments. Это компенсирует неравномерное распределение
    # evidence по категориям у Reducer'а.
    cutaway_fill = _take("cutaway_material", 2)

    arc: list[StorySegment] = []
    arc.extend(_build_arc_from_items(hooks, "hook"))
    arc.extend(_build_arc_from_items(setups[:2], "setup"))
    arc.extend(_build_arc_from_items(devs, "development"))
    arc.extend(_build_arc_from_items(peaks[:2], "peak"))
    arc.extend(_build_arc_from_items(payoffs, "payoff"))

    # Если arc всё ещё < 5 — добиваем cutaway как development.
    while len(arc) < 5 and cutaway_fill:
        item = cutaway_fill.pop(0)
        arc.append(
            StorySegment(
                role="development",
                evidence_id=item.id,
                source_start_sec=item.start,
                source_end_sec=item.end,
                speaker=item.speaker,
                reasoning="fallback cutaway filler",
                text_preview=item.text[:200],
            )
        )

    return StoryScript(
        central_theme=canvas.central_theme,
        arc=arc,
        predicted_duration_sec=sum(s.duration_sec for s in arc),
    )


def _build_arc_from_items(
    items: list[RankedEvidenceItem],
    role: str,
) -> list[StorySegment]:
    return [
        StorySegment(
            role=role,  # type: ignore[arg-type]
            evidence_id=e.id,
            source_start_sec=e.start,
            source_end_sec=e.end,
            speaker=e.speaker,
            reasoning="fallback selected by category",
            text_preview=e.text[:200],
        )
        for e in items
    ]
