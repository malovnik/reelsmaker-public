"""Kartoziya Stage 5.8 — Reels Composer (NEW, не из videoeditor).

Превращает выход Kartoziya-пайплайна (Canvas + RankedEvidence + StoryScript +
StoryVariants) в финальный `AnalysisResult` с `list[ReelPlan]` для текущего
`renderer.py`. Мост между story-engineering и видео-нарезкой.

Решает задачу #2 (предсказуемое N рилсов с контролируемой уникальностью):

1. **Target count** по линейной формуле Никиты — **12 рилсов на каждые 20 минут
   видео, tolerance ±3 per 20-min block**. Масштабируется от короткого видео
   до 5 часов:
   - 10 мин → (6, 3, 9)
   - 20 мин → (12, 9, 15)
   - 40 мин → (24, 18, 30)
   - 60 мин → (36, 27, 45)
   - 120 мин → (72, 54, 90)
   - 300 мин (5 ч) → (180, 135, 225)

2. **Источники кандидатов** (по приоритету уникальности):
   - `package_of_shorts` variant — каждый short = готовый ReelPlan (hook+payoff).
   - `punchy_summary` variant — 1 тизер-рилс.
   - `story_script` base arc — нарезка длинного arc'а окнами 20-90s.
   - Высокоrank'ованные single evidence (hook_candidate/peak_candidate) —
     одно-сегментные рилсы.

3. **Greedy Jaccard-uniqueness филь тр:** после сортировки по score кандидат
   принимается только если tokens_jaccard с любым уже принятым < 0.65
   (= минимум 35% уникальности текста).

4. **Нормализация длительности** — рилс длиннее 90s нарезается на sub-reels
   по логическим breakpoint'ам (role / evidence_id change); короче 10s не
   принимаются.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from videomaker.core.logging import get_logger
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import RankedEvidence, RankedEvidenceItem
from videomaker.models.reel_plan import (
    AnalysisResult,
    ReelPlan,
    ReelSegment,
)
from videomaker.models.story_script import (
    StoryScript,
    StorySegment,
    StoryVariants,
)
from videomaker.services.canvas_embedder import cosine_similarity
from videomaker.services.transcribers.base import TranscribedWord

log = get_logger(__name__)

#: Порог паузы (в секундах) между соседними словами для определения
#: sentence boundary в cleaned_transcript. Silence > 0.5s после word с
#: финальной пунктуацией или просто > 0.8s без пунктуации — граница фразы.
_SENTENCE_SILENCE_THRESHOLD_SEC = 0.5
_SENTENCE_LONG_PAUSE_THRESHOLD_SEC = 0.8
_SENTENCE_FINAL_PUNCT = (".", "!", "?", "…", "?!")

#: Минимальная длительность рилса для платформ (Reels/TikTok/Shorts).
#: 30s — platform floor (Instagram Reels surface'ит от 30s стабильно,
#: TikTok/YouTube Shorts без ограничений). Было 37s — искусственно
#: задран, все evidence padded к этому полу → distribution колом 37-43s
#: независимо от natural драматургии. Теперь 30s позволяет коротким
#: punchy рилсам жить natural.
#: Iteration 2026-04-22: bump от 30 до 45 для смещения распределения в
#: диапазон 45-80s. Группы <45s мёрджатся с соседями через Pass 1, давая
#: более "плотные" рилсы с двумя-тремя смысловыми блоками. Короткие punchy
#: варианты 30-40s жертвуются ради консистентной длины.
REEL_MIN_DURATION_SEC = 45.0

#: Максимальная длительность. 80s = конкретный user-spec верхний предел
#: разнообразия длительностей + запас ~10s до Instagram/TikTok 90s limit.
#: Было 88s — сузили для чёткого диапазона.
REEL_MAX_DURATION_SEC = 80.0

#: Целевая длительность — только как «якорь» для fallback-расширения,
#: НЕ как гравитация для всех рилсов. Раньше здесь стоял 52s, и composer
#: через Pass 3 тянул все группы к этому значению, поэтому финальные
#: рилсы вылезали все ~45+7s независимо от драматургии. Сейчас target
#: равен минимуму (37s) — сегменты расширяются только если их размер
#: ниже платформенного порога, иначе сохраняют длительность от story_doctor.
#:
#: Иными словами: рилсы свободно живут в [REEL_MIN, REEL_MAX] = [37, 88],
#: распределение определяется драматургией (где замкнулась мысль), а не
#: наперёд заданной средней.
#:
#: ВАЖНО: все measurements в этом модуле (predicted_duration_sec,
#: REEL_MIN, REEL_MAX, group_duration) относятся к ЧИСТОМУ КОНТЕНТУ —
#: сумме длительностей ReelSegment'ов. intro/outro видеоматериалы живут
#: отдельно в ``ProjectGraph.intro_path`` / ``outro_path`` и не учитываются
#: здесь. Это инвариант: composer не знает про intro/outro.
REEL_TARGET_DURATION_SEC = 62.0

#: Порог «дополнительной» сборки для структурного boundary в
#: ``_split_arc_into_shorts``. Когда current group набрала >= этого значения
#: и следующий сегмент — структурный переход (peak/payoff/hook), арка
#: разрезается здесь, а не ждёт overflow на REEL_MAX (88s). Без этой
#: эвристики длинный arc (~105s) из коротких сегментов слепляется в одну
#: overflow-группу — composer её отбрасывает в `_arc_group_to_candidate`,
#: и вся полезная арочная структура теряется. Значение 45s = оптимум:
#: выше REEL_MIN, даёт реалистичный трёхактный рилс, не слишком агрессивно
#: дробит короткие арки.
REEL_SPLIT_AT_STRUCTURAL_SEC = 45.0

#: Jaccard-порог схожести текстов. Два рилса считаются дубликатами если их
#: tokens Jaccard ≥ этого значения. 0.65 → минимум 35% уникальности контента.
UNIQUENESS_JACCARD_THRESHOLD = 0.65

#: T1.1 slice 4: semantic порог для cross-reel diversity. Рилсы с cosine
#: (avg_embedding) ≥ этого значения считаются семантическими дубликатами —
#: одна мысль разными словами/сценами. Порог 0.88 строже 0.80 (evidence
#: dedup) — у рилсов embedding более размытые из-за усреднения, поэтому
#: похожесть должна быть близка к 1 чтобы считать дубликатом.
SEMANTIC_REEL_SIMILARITY_THRESHOLD = 0.88

#: Multi-arc variant A (2026-04-21): loose thresholds для overproduction+ranking
#: режима. При multi_arc_enabled composer получает N StoryScript'ов, по одному
#: на canvas moment. Multiple angles одного топика — это не баг а feature
#: (OpusClip pattern: ~30 candidates → ranking top-N). Поэтому dedup
#: ослабляется до near-exact-duplicate порога, LLM-отобранные уникальные
#: углы сохраняются.
#: Iteration log:
#: * v1 (a212f4f): 0.85/0.95/0.70/0.90 → 10 reels out of 18 arcs (job 54fcef5f)
#: * v2 (e3bba6d): 0.92/0.97/0.85/0.95 → 5 reels out of 12 arcs (job a5331d13)
#: * v3 (4a94460): 1.01/1.01/1.01/1.01 — DISABLE dedup полностью для multi_arc.
#:   Overproduction pattern: все per_moment_arc candidates проходят фильтр
#:   без дедуп-cap'ов. Ranking по composite_score → user_target_count cuts.
#:   Если arcs <= 1.0 порога — никогда не отбросятся. Ratio 1.01 безопасен
#:   потому что real overlap всегда в [0.0, 1.0].
#: * v4 (2026-04-22, fix 2/4): soft thresholds как safety net ПОСЛЕ расширения
#:   window_scales до (0.7, 1.5). Дубли из одного moment (r1=r2=r3=r4 идентичные)
#:   срезаем через Jaccard 0.88 (near-identical текст) + semantic 0.92
#:   (embedding cosine, embedding-based dedup точнее Jaccard). temporal 0.95
#:   ловит arcs с почти 100%-overlapping segments. cross_reel 1.01 остаётся
#:   disabled — multi-angle по определению перекрывает sources.
_MULTI_ARC_UNIQUENESS_JACCARD_THRESHOLD = 0.88
_MULTI_ARC_SEMANTIC_REEL_SIMILARITY_THRESHOLD = 0.92
_MULTI_ARC_CROSS_REEL_SEGMENT_OVERLAP_RATIO = 1.01
_MULTI_ARC_TEMPORAL_OVERLAP_DUP_RATIO = 0.95

#: Минимальное число токенов, ниже которого сравнение Jaccard недостоверно —
#: короткие рилсы пропускаем через фильтр без сравнения.
MIN_TOKENS_FOR_UNIQUENESS_CHECK = 8

#: Роли, разрешённые в качестве закрытия arc group. Группа, оканчивающаяся
#: на "setup" или "development", воспринимается как обрыв мысли — такие
#: группы мёрджатся со следующей (OpusClip-style semantic closure).
_CLOSURE_ROLES: frozenset[str] = frozenset({"peak", "payoff"})


# StorySegment.role → ReelSegment.order_role (у ReelSegment нет "setup").
_ROLE_MAP: dict[str, str] = {
    "hook": "hook",
    "setup": "development",
    "development": "development",
    "peak": "peak",
    "payoff": "payoff",
}

_TOKENIZER = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)


@dataclass(slots=True)
class _Candidate:
    """Кандидат-рилс до фильтрации/нумерации."""

    score: float
    plan: ReelPlan
    tokens: set[str]
    source: str  # "package_of_shorts" / "punchy_summary" / "base_arc" / "evidence_single"
    avg_embedding: list[float] | None = None
    """Усреднённый embedding по сегментам рилса (из RankedEvidenceItem.embedding).
    Заполняется в `_populate_candidate_embeddings` после построения всех candidates.
    None если ни один сегмент не нашёлся в lookup или у всех embedding=None.
    Используется `_greedy_uniqueness_filter` для 3-го уровня фильтрации —
    semantic cross-reel diversity."""


def _candidate_label(c: _Candidate) -> str:
    """Короткий идентификатор кандидата для логирования отбора."""
    reel_id = c.plan.reel_id or "?"
    hook = c.plan.hook[:40] if c.plan.hook else ""
    return f"{reel_id}|{c.source}|{hook}"


#: Допустимый диапазон пользовательского override количества рилсов.
#: MAX покрывает 5-часовое видео по формуле 12 рилсов на 20 мин + tolerance
#: (300 мин / 20 × 12 = 180 target, +45 tolerance → 225 ceiling).
USER_TARGET_REEL_COUNT_MIN = 3
USER_TARGET_REEL_COUNT_MAX = 225


def _user_target_tolerance(n: int) -> int:
    """Допуск вокруг user_target_count: 10% от N, floor 3.

    Uniqueness-фильтр отбрасывает близкие кандидаты даже при строгом count,
    поэтому ±tolerance нужен чтобы не проваливаться ниже user wish.
    Для больших N (50+) константный ±3 слишком жёсткий — масштабируем.
    """
    return max(3, round(n * 0.10))


def compose_reels(
    canvas: ProjectCanvas,
    ranked: RankedEvidence,
    story_script: StoryScript,
    variants: StoryVariants,
    *,
    source_duration_sec: float,
    llm_model: str = "gemini-2.5-flash-lite",
    provider: str = "gemini",
    user_target_count: int | None = None,
    pacing_profile_name: str | None = None,
    cross_context_penalty_enabled: bool = True,
    reel_count_enforce_floor_ceiling: bool = False,
    reel_count_dedup_jaccard_threshold: float = 0.7,
    per_moment_arcs: list[StoryScript] | None = None,
    cleaned_words: list[TranscribedWord] | None = None,
) -> AnalysisResult:
    """Собирает финальный `AnalysisResult` с отранжированными рилсами.

    ``user_target_count`` — опциональный override авто-диапазона по длительности.
    Значение вне ``[USER_TARGET_REEL_COUNT_MIN, USER_TARGET_REEL_COUNT_MAX]``
    вызывает ``ValueError``. При заданном override:
      - ``target_count = user_target_count``
      - ``min_count = max(1, user_target_count - _user_target_tolerance(N))``
      - ``max_count = min(USER_TARGET_REEL_COUNT_MAX, user_target_count + tol)``
    """
    if user_target_count is not None:
        if not (USER_TARGET_REEL_COUNT_MIN <= user_target_count <= USER_TARGET_REEL_COUNT_MAX):
            raise ValueError(
                f"user_target_count must be in "
                f"[{USER_TARGET_REEL_COUNT_MIN}, {USER_TARGET_REEL_COUNT_MAX}], "
                f"got {user_target_count}"
            )
        target_count = user_target_count
        tolerance = _user_target_tolerance(user_target_count)
        min_count = max(1, user_target_count - tolerance)
        max_count = min(USER_TARGET_REEL_COUNT_MAX, user_target_count + tolerance)
    else:
        target_count, min_count, max_count = _compute_target_range(source_duration_sec)
    log.info(
        "reels_composer_start",
        duration_sec=source_duration_sec,
        target=target_count,
        min=min_count,
        max=max_count,
        user_override=user_target_count is not None,
    )

    evidence_by_id = {e.id: e for e in ranked.items}

    candidates: list[_Candidate] = []
    use_per_moment_arcs = per_moment_arcs is not None and len(per_moment_arcs) > 0
    if use_per_moment_arcs:
        # Multi-arc variant A: один StoryScript на canvas moment. Legacy
        # источники (package_of_shorts / punchy_summary / base_arc / singles /
        # thematic) отключены — composer работает на полностью подготовленных
        # story_doctor арках, по одному candidate на moment.
        assert per_moment_arcs is not None  # narrowing for type-checker
        per_moment_arc_candidates = _candidates_from_per_moment_arcs(
            per_moment_arcs,
            evidence_by_id,
            source_duration_sec,
            cleaned_words=cleaned_words,
        )
        candidates.extend(per_moment_arc_candidates)
        log.info(
            "composer_candidates_breakdown",
            mode="multi_arc_variant_a",
            per_moment_arcs_input=len(per_moment_arcs),
            per_moment_arcs_accepted=len(per_moment_arc_candidates),
            total=len(candidates),
        )
    else:
        pkg_candidates = _candidates_from_package_of_shorts(
            variants, evidence_by_id, source_duration_sec
        )
        punchy_candidates = _candidates_from_punchy_summary(
            variants, evidence_by_id, source_duration_sec
        )
        base_arc_candidates = _candidates_from_base_arc(
            story_script, evidence_by_id, source_duration_sec
        )
        singles_candidates = _candidates_from_singles(ranked, source_duration_sec)
        # T2.3 Thematic composer — нелинейная пересборка через semantic clustering
        # embedding'ов. Дополняет chronological-candidates арками объединёнными
        # идеей, а не временем. Использует T1.1 embeddings.
        thematic_candidates = _candidates_from_thematic_clusters(
            ranked, source_duration_sec
        )

        candidates.extend(pkg_candidates)
        candidates.extend(punchy_candidates)
        candidates.extend(base_arc_candidates)
        candidates.extend(singles_candidates)
        candidates.extend(thematic_candidates)

        log.info(
            "composer_candidates_breakdown",
            mode="legacy",
            package_of_shorts=len(pkg_candidates),
            punchy_summary=len(punchy_candidates),
            base_arc=len(base_arc_candidates),
            singles=len(singles_candidates),
            thematic_clusters=len(thematic_candidates),
            total=len(candidates),
            arc_len=len(story_script.arc),
            arc_total_duration=round(
                sum(s.duration_sec for s in story_script.arc), 1
            ),
        )

    # T1.1 slice 4: заполняем avg_embedding для cross-reel diversity filter.
    # Lookup по (round(start,1), round(end,1)) в ranked.items — почти все
    # single-evidence candidates попадут в hit, arc/group candidates могут
    # оставаться без avg_embedding → в фильтре обходятся по legacy path.
    _populate_candidate_embeddings(candidates, ranked)

    # T10.9 Cross-Context Risk Score — penalty для кандидатов собранных из
    # далёких/тематически разных segments. Снижает риск «телевизионного»
    # эффекта где composer склеил скандальную нарезку из контекста.
    if cross_context_penalty_enabled:
        _apply_cross_context_penalty(candidates, ranked)

    # T10.5 Pacing profile preference — снижает score кандидатов чья
    # duration сильно отличается от shot_duration_mode выбранного profile.
    # Гарантирует консистентный pacing между рилсами одного job.
    if pacing_profile_name:
        _apply_pacing_profile_preference(candidates, pacing_profile_name)

    # Arc-narrative boost: multi-segment candidates (base_arc,
    # package_of_shorts, thematic_clusters) получают score × 1.25 bonus.
    # Это реализует драматургическую философию Картозии — рилс с полной
    # аркой (hook→setup→peak→payoff) ценнее одиночной сильной реплики
    # даже если индивидуальные composite_score'ы сегментов чуть ниже.
    # Без этого boost'а highest-score singles всегда обгоняют arc-based
    # candidates в greedy filter → все рилсы деградируют в evidence_single.
    _apply_arc_narrative_boost(candidates)

    # Сортировка: высокий score первым — greedy фильтр отсеет похожие.
    candidates.sort(key=lambda c: c.score, reverse=True)

    # Multi-arc variant A overproduction mode: loose dedup thresholds
    # чтобы multiple angles одного canvas moment сохранялись как отдельные
    # candidate reels. Ranking по composite_score выберет top-N.
    # В legacy mode работают strict default thresholds (unchanged).
    if use_per_moment_arcs:
        accepted = _greedy_uniqueness_filter(
            candidates,
            max_count=max_count,
            threshold=_MULTI_ARC_UNIQUENESS_JACCARD_THRESHOLD,
            semantic_threshold=_MULTI_ARC_SEMANTIC_REEL_SIMILARITY_THRESHOLD,
            cross_reel_overlap_ratio=_MULTI_ARC_CROSS_REEL_SEGMENT_OVERLAP_RATIO,
        )
    else:
        accepted = _greedy_uniqueness_filter(candidates, max_count=max_count)

    # Если кандидатов меньше min_count — принимаем дополнительные с ослабленным
    # порогом (минимум что-то отдать рендереру, чем пусто).
    if len(accepted) < min_count:
        fallback_threshold = (
            _MULTI_ARC_UNIQUENESS_JACCARD_THRESHOLD + 0.05
            if use_per_moment_arcs
            else UNIQUENESS_JACCARD_THRESHOLD + 0.15
        )
        fallback_cross_overlap = (
            _MULTI_ARC_CROSS_REEL_SEGMENT_OVERLAP_RATIO
            if use_per_moment_arcs
            else _CROSS_REEL_SEGMENT_OVERLAP_RATIO
        )
        fallback_semantic = (
            _MULTI_ARC_SEMANTIC_REEL_SIMILARITY_THRESHOLD
            if use_per_moment_arcs
            else SEMANTIC_REEL_SIMILARITY_THRESHOLD
        )
        accepted = _greedy_uniqueness_filter(
            candidates,
            max_count=max_count,
            threshold=fallback_threshold,
            semantic_threshold=fallback_semantic,
            cross_reel_overlap_ratio=fallback_cross_overlap,
        )

    # Phase 2 tech-debt: post-ranking предикт-реел-каунт floor/ceiling.
    # Применяется поверх 3-уровнего _greedy_uniqueness_filter, даёт predictable
    # N по длительности видео + Jaccard dedup на настраиваемом пороге.
    if reel_count_enforce_floor_ceiling:
        before_enforce = len(accepted)
        accepted = _enforce_reel_count_floor_ceiling(
            accepted,
            source_duration_sec=source_duration_sec,
            jaccard_threshold=reel_count_dedup_jaccard_threshold,
        )
        log.info(
            "reel_count_enforced",
            before=before_enforce,
            after=len(accepted),
            threshold=reel_count_dedup_jaccard_threshold,
            source_duration_min=round(source_duration_sec / 60.0, 1),
        )

    final_reels = _renumber_and_finalize(accepted)

    log.info(
        "reels_composer_done",
        target=target_count,
        accepted=len(final_reels),
        total_candidates=len(candidates),
    )

    return AnalysisResult(
        reels=final_reels,
        llm_model=llm_model,
        provider=provider,
        stats={
            "source_duration_sec": source_duration_sec,
            "target_reel_count": target_count,
            "min_reel_count": min_count,
            "max_reel_count": max_count,
            "actual_reel_count": len(final_reels),
            "candidates_total": len(candidates),
            "ranked_evidence_count": len(ranked.items),
            "variants_count": len(variants.variants),
            "uniqueness_jaccard_threshold": UNIQUENESS_JACCARD_THRESHOLD,
            "canvas_central_theme": canvas.central_theme,
            "bookend_motif_id": story_script.bookend_motif_id,
            "user_requested_reel_count": user_target_count,
        },
    )


# ---------------------------------------------------------------------------
# Target range по длительности
# ---------------------------------------------------------------------------


def _compute_target_range(duration_sec: float) -> tuple[int, int, int]:
    """Возвращает (target, min, max) количество рилсов по линейной формуле.

    Спецификация: **12 рилсов на каждые 20 минут видео, tolerance ±3
    per 20-min block**. Масштабируется линейно от короткого видео до 5 часов.

    Ориентиры:
      - 10 мин → (6, 3, 9)
      - 20 мин → (12, 9, 15)
      - 40 мин → (24, 18, 30)
      - 60 мин → (36, 27, 45)
      - 120 мин → (72, 54, 90)
      - 300 мин (5 ч) → (180, 135, 225)

    Floor ``max(3, ...)`` защищает короткие видео от target<3.
    Ceiling ``USER_TARGET_REEL_COUNT_MAX`` применяется к max_count только —
    target и min_count могут превышать MAX если видео длинное (свыше 5 ч).
    """
    blocks = max(0.0, duration_sec) / 1200.0  # 1200s = 20min
    target = max(3, round(12 * blocks))
    tolerance = max(3, round(3 * blocks))
    min_count = max(1, target - tolerance)
    max_count = min(USER_TARGET_REEL_COUNT_MAX, target + tolerance)
    return target, min_count, max_count


# ---------------------------------------------------------------------------
# Источники кандидатов
# ---------------------------------------------------------------------------


def _candidates_from_package_of_shorts(
    variants: StoryVariants,
    evidence_by_id: dict[str, RankedEvidenceItem],
    source_duration_sec: float,
) -> list[_Candidate]:
    """package_of_shorts: каждый short-arc — 1 ReelPlan."""
    variant = variants.by_kind("package_of_shorts")
    if variant is None or not variant.arc:
        return []
    # Группируем подряд идущие segments по роли: hook открывает новую мини-историю.
    groups = _split_arc_into_shorts(variant.arc)
    groups = _merge_short_groups(groups)
    # Cross-group assembly: для групп без closure — pull payoff из всей arc.
    groups = [_pull_closure_from_arc(g, variant.arc) for g in groups]
    return [
        c
        for c in (
            _arc_group_to_candidate(
                group,
                evidence_by_id,
                source="package_of_shorts",
                hook_fallback=variant.central_theme,
                source_duration_sec=source_duration_sec,
            )
            for group in groups
        )
        if c is not None
    ]


def _candidates_from_punchy_summary(
    variants: StoryVariants,
    evidence_by_id: dict[str, RankedEvidenceItem],
    source_duration_sec: float,
) -> list[_Candidate]:
    """punchy_summary: один тизер-рилс."""
    variant = variants.by_kind("punchy_summary")
    if variant is None or not variant.arc:
        return []
    candidate = _arc_group_to_candidate(
        variant.arc,
        evidence_by_id,
        source="punchy_summary",
        hook_fallback=variant.central_theme,
        source_duration_sec=source_duration_sec,
    )
    return [candidate] if candidate is not None else []


def _candidates_from_base_arc(
    story_script: StoryScript,
    evidence_by_id: dict[str, RankedEvidenceItem],
    source_duration_sec: float,
) -> list[_Candidate]:
    """Нарезка base arc на окна REEL_MIN..REEL_MAX по логическим breakpoints."""
    if not story_script.arc:
        return []
    groups = _split_arc_into_shorts(story_script.arc)
    groups = _merge_short_groups(groups)
    # Cross-group assembly: premise из одной части + payoff из другой.
    groups = [_pull_closure_from_arc(g, story_script.arc) for g in groups]
    return [
        c
        for c in (
            _arc_group_to_candidate(
                group,
                evidence_by_id,
                source="base_arc",
                hook_fallback=story_script.central_theme,
                source_duration_sec=source_duration_sec,
            )
            for group in groups
        )
        if c is not None
    ]



def _candidates_from_per_moment_arcs(
    per_moment_arcs: list[StoryScript],
    evidence_by_id: dict[str, RankedEvidenceItem],
    source_duration_sec: float,
    cleaned_words: list[TranscribedWord] | None = None,
) -> list[_Candidate]:
    """Multi-arc variant A: один кандидат на StoryScript, построенный вокруг canvas moment.

    Каждый StoryScript уже содержит полную hook-development-payoff структуру
    от story_doctor (per-moment). Здесь мы не разрезаем arc повторно через
    ``_split_arc_into_shorts``: если arc > REEL_MAX — внутри
    ``_arc_group_to_candidate`` работает R3_hard_floor trim который
    сохраняет critical roles и берёт top-scored optional в budget REEL_MAX.

    ``cleaned_words`` пробрасывается до ``_arc_group_to_candidate`` для
    sentence boundary snap в R2-lite phase.

    Source tag ``per_moment_arc`` входит в ``_ARC_BOOSTED_SOURCES`` — к score
    применяется ``_ARC_NARRATIVE_BOOST`` (×1.25) на общих основаниях с
    остальными multi-segment arc candidates.

    Pull-to-target (fix 3/4, 2026-04-22): multi_arc — 1 StoryScript = 1
    group, Pass 3 conditional pull не работает (нечего мёрджить). Здесь
    передаём ``extend_to_target`` вниз — _arc_group_to_candidate тянет
    source timestamps каждого segment'а через transcript context до
    достижения target_duration. Это настоящий fix pull-to-target для
    multi_arc ветки.
    """
    target_duration = _get_target_duration()
    candidates: list[_Candidate] = []
    for arc in per_moment_arcs:
        if not arc.arc:
            continue
        cand = _arc_group_to_candidate(
            list(arc.arc),
            evidence_by_id,
            source="per_moment_arc",
            hook_fallback=arc.central_theme,
            source_duration_sec=source_duration_sec,
            cleaned_words=cleaned_words,
            extend_to_target=target_duration,
        )
        if cand is not None:
            candidates.append(cand)
    return candidates


def _candidates_from_singles(
    ranked: RankedEvidence,
    source_duration_sec: float,
) -> list[_Candidate]:
    """Отдельные high-score evidence → single-segment reels.

    Короткие evidence (<REEL_MIN) расширяются симметрично до REEL_MIN в
    пределах source (с клампом по границам). Длинные (>REEL_MAX) не
    отбрасываются — truncate'аются до REEL_MAX вокруг центра evidence.
    """
    result: list[_Candidate] = []
    for item in ranked.items:
        start, end = _normalize_segment_bounds(
            item.start,
            item.end,
            source_duration_sec=source_duration_sec,
        )
        if start is None or end is None:
            continue
        duration = end - start
        plan = ReelPlan(
            reel_id=_safe_reel_id(f"e-{item.id}"),
            hook=_trim_hook(item.text),
            predicted_duration_sec=duration,
            target_audience="",
            segments=[
                ReelSegment(
                    source_start=start,
                    source_end=end,
                    reasoning=item.reasoning or f"{item.category} from {item.source_agent}",
                    order_role=_category_to_role(item.category),  # type: ignore[arg-type]
                ),
            ],
        )
        tokens = _tokenize(item.text)
        result.append(
            _Candidate(
                score=item.composite_score,
                plan=plan,
                tokens=tokens,
                source="evidence_single",
            )
        )
    return result


#: Порог cosine для объединения evidence в thematic кластер.
#: 0.72 — чуть мягче reducer dedup (0.80) чтобы кластеризовать
#: смысловые перефразы, а не только точные дубликаты (те уже
#: отфильтрованы в _dedup_hybrid). Получаем families идей.
_THEMATIC_CLUSTER_THRESHOLD = 0.72
_THEMATIC_MIN_CLUSTER_SIZE = 3
_THEMATIC_MAX_CLUSTERS = 20


def _candidates_from_thematic_clusters(
    ranked: RankedEvidence,
    source_duration_sec: float,
) -> list[_Candidate]:
    """T2.3 Thematic composer: нелинейная пересборка рилсов по темам.

    Использует semantic embeddings (T1.1) для union-find кластеризации
    ranked.items по cosine similarity. Каждый кластер с ≥ 3 items и хотя бы
    одним hook+payoff становится thematic_cluster candidate — рилс
    объединён ИДЕЕЙ, а не chronological-order.

    Structure:
    1. Union-find по cosine ≥ _THEMATIC_CLUSTER_THRESHOLD.
    2. Фильтр: размер кластера ≥ 3, содержит hook_candidate + payoff_candidate.
    3. Для каждого подходящего кластера:
       - hook = top-scored hook_candidate, сегмент source_start/end.
       - body = top 1-2 development/peak из кластера (середина).
       - payoff = top-scored payoff_candidate.
    4. Формируем ReelPlan с role-порядком (не source-chronology).

    Graceful-degrade: если <5 items имеют embedding — возвращаем [].
    Thematic candidates конкурируют с другими через _greedy_uniqueness_filter.
    """
    items_with_emb = [i for i in ranked.items if i.embedding is not None]
    if len(items_with_emb) < _THEMATIC_MIN_CLUSTER_SIZE:
        return []

    clusters = _cluster_by_cosine(items_with_emb, _THEMATIC_CLUSTER_THRESHOLD)
    clusters.sort(key=len, reverse=True)

    result: list[_Candidate] = []
    for cluster in clusters[:_THEMATIC_MAX_CLUSTERS]:
        if len(cluster) < _THEMATIC_MIN_CLUSTER_SIZE:
            continue
        candidate = _build_thematic_candidate(cluster, source_duration_sec)
        if candidate is not None:
            result.append(candidate)
    return result


def _cluster_by_cosine(
    items: list[RankedEvidenceItem],
    threshold: float,
) -> list[list[RankedEvidenceItem]]:
    """Union-find кластеризация по cosine.

    Item i присоединяется к кластеру j если cosine(emb_i, центроид_j) >=
    threshold. Центроид обновляется как среднее embedding'ов кластера.
    O(N²) — приемлемо для N ≤ 200 (ranked_cap).
    """
    clusters: list[dict] = []
    for item in items:
        if item.embedding is None:
            continue
        attached = False
        for cluster in clusters:
            centroid = cluster["centroid"]
            sim = cosine_similarity(item.embedding, centroid)
            if sim >= threshold:
                cluster["items"].append(item)
                new_centroid = _avg_embeddings(
                    [i.embedding for i in cluster["items"] if i.embedding]
                )
                if new_centroid is not None:
                    cluster["centroid"] = new_centroid
                attached = True
                break
        if not attached:
            clusters.append({
                "centroid": list(item.embedding),
                "items": [item],
            })
    return [c["items"] for c in clusters]


def _avg_embeddings(embs: list[list[float]]) -> list[float] | None:
    if not embs:
        return None
    dim = len(embs[0])
    if any(len(e) != dim for e in embs):
        return None
    sums = [0.0] * dim
    for e in embs:
        for i, v in enumerate(e):
            sums[i] += v
    n = len(embs)
    return [v / n for v in sums]


def _build_thematic_candidate(
    cluster: list[RankedEvidenceItem],
    source_duration_sec: float,
) -> _Candidate | None:
    """Собирает ReelPlan из кластера с role-порядком (hook → body → payoff).

    Hook = top-scored hook_candidate. Payoff = top-scored payoff_candidate.
    Body = top 1-2 development/peak (не hook/payoff) из кластера.
    Обязательно наличие hook и payoff, иначе кластер не арка.
    """
    by_cat: dict[str, list[RankedEvidenceItem]] = {}
    for item in cluster:
        by_cat.setdefault(item.category, []).append(item)

    def _top(cat: str) -> RankedEvidenceItem | None:
        bucket = by_cat.get(cat) or []
        if not bucket:
            return None
        return max(bucket, key=lambda x: x.composite_score)

    hook = _top("hook_candidate")
    payoff = _top("payoff_candidate")
    if hook is None or payoff is None:
        return None

    # Body — лучшие из peak/development, не включая hook/payoff.
    used_ids = {hook.id, payoff.id}
    body_pool = [
        i for i in cluster
        if i.id not in used_ids
        and i.category in {"peak_candidate", "development_material"}
    ]
    body_pool.sort(key=lambda x: x.composite_score, reverse=True)
    body = body_pool[:2]

    ordered = [hook, *body, payoff]
    segments: list[ReelSegment] = []
    total_duration = 0.0
    for item in ordered:
        start, end = _normalize_segment_bounds(
            item.start, item.end, source_duration_sec=source_duration_sec,
        )
        if start is None or end is None:
            continue
        seg_role = _category_to_role(item.category)
        segments.append(
            ReelSegment(
                source_start=start,
                source_end=end,
                reasoning=item.reasoning or f"thematic {item.category}",
                order_role=seg_role,  # type: ignore[arg-type]
            )
        )
        total_duration += end - start

    if len(segments) < 2 or total_duration < REEL_MIN_DURATION_SEC:
        return None
    if total_duration > REEL_MAX_DURATION_SEC:
        return None

    avg_score = sum(i.composite_score for i in ordered) / len(ordered)
    combined_text = " ".join(i.text for i in ordered)

    plan = ReelPlan(
        reel_id=_safe_reel_id(f"th-{hook.id}"),
        hook=_trim_hook(hook.text),
        predicted_duration_sec=total_duration,
        target_audience="",
        segments=segments,
    )
    return _Candidate(
        score=avg_score,
        plan=plan,
        tokens=_tokenize(combined_text),
        source="thematic_cluster",
    )


# ---------------------------------------------------------------------------
# Нарезка arc → группы (мини-истории)
# ---------------------------------------------------------------------------


def _split_arc_into_shorts(arc: list[StorySegment]) -> list[list[StorySegment]]:
    """Разбивает arc на мини-истории по структурным маркерам или длительности.

    Правила (приоритет сверху вниз):
    1. Новая группа стартует с role="hook" (если встречается в середине arc
       и в текущей группе уже есть не-hook сегмент).
    2. Структурный boundary: если набрано >= REEL_SPLIT_AT_STRUCTURAL_SEC (45s)
       и следующий segment — peak/payoff/hook (переход между актами), делим.
       Без этого правила arc 90-120s из коротких 10-15s сегментов вылеплявал
       одну overflow-группу, которую composer отбрасывал в
       ``_arc_group_to_candidate`` → singles-only fallback.
    3. Группа закрывается если суммарная длительность превышает
       REEL_MAX_DURATION_SEC (safety net).
    4. Одна группа всегда содержит хотя бы 1 segment.
    """
    if not arc:
        return []

    structural_boundary_roles = {"peak", "payoff", "hook"}

    groups: list[list[StorySegment]] = []
    current: list[StorySegment] = []
    current_duration = 0.0

    for seg in arc:
        has_nonhook_in_current = any(s.role != "hook" for s in current)
        is_hook_boundary = (
            seg.role == "hook" and current and has_nonhook_in_current
        )
        is_structural_boundary = (
            current_duration >= REEL_SPLIT_AT_STRUCTURAL_SEC
            and has_nonhook_in_current
            and seg.role in structural_boundary_roles
        )
        would_overflow = current_duration + seg.duration_sec > REEL_MAX_DURATION_SEC

        if (
            is_hook_boundary
            or is_structural_boundary
            or would_overflow
        ) and current:
            groups.append(current)
            current = []
            current_duration = 0.0

        current.append(seg)
        current_duration += seg.duration_sec

    if current:
        groups.append(current)

    return groups


def _pull_closure_from_arc(
    group: list[StorySegment],
    all_arc: list[StorySegment],
) -> list[StorySegment]:
    """Cross-group assembly: если группа БЕЗ peak/payoff, притянуть лучший
    payoff-сегмент из остальной arc.

    OpusClip: "find gold nuggets from different parts and combine into a
    coherent short". Когда merge со следующей группой невозможен (упрёмся
    в REEL_MAX при полном добавлении), точечный pull ОДНОГО payoff-сегмента
    всё ещё возможен.

    Преференции выбора payoff:
    1. role=payoff + payoff_conclusion (closure-полный)
    2. role=payoff без closure
    3. role=peak (fallback)

    Не принимает payoff с тем же evidence_id, что уже в группе.
    Если суммарная длительность > REEL_MAX — не тянем, возвращаем группу
    как есть.
    """
    if not group or not all_arc:
        return group
    if any(s.role in _CLOSURE_ROLES for s in group):
        return group

    group_keys = {(s.evidence_id, s.source_start_sec) for s in group}
    candidates = [
        s
        for s in all_arc
        if s.role in _CLOSURE_ROLES and (s.evidence_id, s.source_start_sec) not in group_keys
    ]
    if not candidates:
        return group

    payoffs_with_closure = [s for s in candidates if s.role == "payoff" and s.payoff_conclusion]
    payoffs_any = [s for s in candidates if s.role == "payoff"]
    peaks = [s for s in candidates if s.role == "peak"]

    ordered = payoffs_with_closure or payoffs_any or peaks
    if not ordered:
        return group

    best = ordered[0]
    current_duration = sum(s.duration_sec for s in group)
    if current_duration + best.duration_sec > REEL_MAX_DURATION_SEC:
        return group

    return [*group, best]


def _merge_short_groups(
    groups: list[list[StorySegment]],
) -> list[list[StorySegment]]:
    """Двухпроходный мёрдж групп под REEL_TARGET=45s.

    Mandatory pass (1): группы короче ``REEL_MIN`` (<31s) ОБЯЗАТЕЛЬНО
    сливаются с соседями пока sum <= ``REEL_MAX`` — без этого рилс не
    выживет валидатор длины.

    Opportunistic pass (2): группы короче ``REEL_TARGET`` (<45s) сливаются
    со следующей если sum <= ``REEL_MAX``. Это даёт **narrative completeness**
    в духе OpusClip: рилс получает контекст + разрешение, а не обрывок мысли
    в 31-36 секунд. Если следующая тоже короткая — можно набрать две-три
    короткие группы в одну 45s-историю.

    Финальная проверка хвоста — короткая последняя группа приклеивается к
    предыдущей (если помещается).
    """
    if not groups:
        return []

    def _has_complete_short_arc(group: list[StorySegment]) -> bool:
        """Группа имеет complete short arc если:
        1. Содержит role=hook (или setup как opening)
        2. И закрывается на role in _CLOSURE_ROLES (peak/payoff)
        Такая группа может быть short но драматургически законченной;
        Pass 1 mandatory её НЕ склеивает с соседом — вместо этого
        ``_arc_group_to_candidate`` расширит timing через source padding.
        Защищает package_of_shorts Short 1/2/3 от слипания в один
        5-segment monstr-рилс с мешаниной из разных историй.
        """
        if not group:
            return False
        has_opening = any(s.role in {"hook", "setup"} for s in group)
        has_closure = group[-1].role in _CLOSURE_ROLES
        return has_opening and has_closure

    def _pass(
        threshold: float,
        current_groups: list[list[StorySegment]],
        *,
        require_closure: bool = False,
        skip_complete_short_arcs: bool = False,
    ) -> list[list[StorySegment]]:
        merged: list[list[StorySegment]] = []
        i = 0
        while i < len(current_groups):
            current = list(current_groups[i])
            current_duration = sum(s.duration_sec for s in current)
            while i + 1 < len(current_groups):
                needs_more_time = current_duration < threshold
                needs_closure = require_closure and current[-1].role not in _CLOSURE_ROLES
                # Mandatory pass: если current уже complete short arc
                # (hook/setup → ... → peak/payoff), не принудительно
                # склеиваем. _arc_group_to_candidate расширит source range.
                if (
                    skip_complete_short_arcs
                    and _has_complete_short_arc(current)
                    and current_duration >= REEL_MIN_DURATION_SEC * 0.6
                ):
                    break
                if not (needs_more_time or needs_closure):
                    break
                next_group = current_groups[i + 1]
                next_duration = sum(s.duration_sec for s in next_group)
                if current_duration + next_duration > REEL_MAX_DURATION_SEC:
                    break
                current.extend(next_group)
                current_duration += next_duration
                i += 1
            merged.append(current)
            i += 1
        return merged

    # Pass 1: mandatory — убрать всё <REEL_MIN. НО complete short arcs
    # (hook→payoff/peak) с duration >= 0.6*REEL_MIN (~22s) защищены от
    # слипания: _arc_group_to_candidate extend'ит их до REEL_MIN через
    # source padding.
    merged = _pass(
        REEL_MIN_DURATION_SEC,
        groups,
        skip_complete_short_arcs=_get_skip_complete_short_arcs(),
    )

    # Pass 2: closure — если group заканчивается на setup/development,
    # тянем вперёд пока не зацепим peak/payoff или не упрёмся в REEL_MAX.
    # Это исправляет "обрыв мысли посередине" (OpusClip semantic closure).
    merged = _pass(0.0, merged, require_closure=True)

    # Pass 3 (Fix 3, 2026-04-21): Conditional opportunistic merge к TARGET.
    # Раньше Pass 3 подтягивал ВСЕ группы к 52s (удалён в 3c139c4, т.к.
    # усреднял драматургию). Теперь pull работает только если группа не
    # имеет достаточно development-сегментов ("thin arc"). Группы с богатой
    # структурой сохраняют свою длительность. Strength + target настраиваются
    # через PerformanceSettings (reel_target_duration_sec / reel_target_pull_strength).
    pull_strength = _get_pull_strength()
    target_duration = _get_target_duration()
    if pull_strength != "off":
        thin_arcs_before = sum(
            1
            for g in merged
            if sum(s.duration_sec for s in g) < target_duration
            and sum(1 for s in g if s.role == "development") < 2
        )
        merged = _conditional_pass_3(merged, target_duration, pull_strength)
        log.info(
            "composer_pass3_conditional",
            target=target_duration,
            strength=pull_strength,
            groups_after=len(merged),
            thin_arcs_before=thin_arcs_before,
        )

    # Tail: короткая последняя группа (< REEL_MIN) — к предыдущей.
    # Пограничный случай: платформенный минимум не достигнут — клей к соседу.
    if len(merged) >= 2:
        last_duration = sum(s.duration_sec for s in merged[-1])
        if last_duration < REEL_MIN_DURATION_SEC:
            prev_duration = sum(s.duration_sec for s in merged[-2])
            if prev_duration + last_duration <= REEL_MAX_DURATION_SEC:
                merged[-2].extend(merged[-1])
                merged.pop()

    return merged


def _conditional_pass_3(
    groups: list[list[StorySegment]],
    target: float,
    strength: Literal["soft", "hard"],
) -> list[list[StorySegment]]:
    """Conditional opportunistic merge — тянет к ``target`` только thin arcs.

    * ``strength="soft"`` — merge применяется ТОЛЬКО к группам где
      sum_duration < target И число development-сегментов < 2. Группы с
      богатой структурой (>=2 development) не тянутся — драматургия уже
      полноценная.
    * ``strength="hard"`` — merge применяется ко всем группам < target
      (legacy-поведение до коммита 3c139c4).

    В обоих случаях sum_duration после merge не превышает
    :data:`REEL_MAX_DURATION_SEC`. Слияние идёт вперёд (с i+1), как и в
    других passes, чтобы не ломать тайминг.
    """
    if not groups:
        return []

    merged: list[list[StorySegment]] = []
    i = 0
    while i < len(groups):
        current = list(groups[i])
        current_duration = sum(s.duration_sec for s in current)
        while i + 1 < len(groups):
            if current_duration >= target:
                break
            dev_count = sum(1 for s in current if s.role == "development")
            should_pull = strength == "hard" or (
                strength == "soft" and dev_count < 2
            )
            if not should_pull:
                break
            next_group = groups[i + 1]
            next_duration = sum(s.duration_sec for s in next_group)
            if current_duration + next_duration > REEL_MAX_DURATION_SEC:
                break
            current.extend(next_group)
            current_duration += next_duration
            i += 1
        merged.append(current)
        i += 1
    return merged


def _get_target_duration() -> float:
    """Читает ``reel_target_duration_sec`` с приоритетом PerformanceSettings.

    Resolution order (Fix 5):
    1. PerformanceSettings (UI override из /settings/performance)
    2. core.config.Settings (env defaults)
    3. ``REEL_TARGET_DURATION_SEC`` (=REEL_MIN, safety fallback)

    Clamp к [REEL_MIN, REEL_MAX] защищает от некорректного override
    и держит контракт composer'а.
    """
    try:
        from videomaker.services.runtime_settings_store import (
            get_cached_performance_settings,
        )

        perf = get_cached_performance_settings()
        if perf is not None:
            return max(
                REEL_MIN_DURATION_SEC,
                min(REEL_MAX_DURATION_SEC, perf.reel_target_duration_sec),
            )
    except Exception:
        pass
    try:
        from videomaker.core.config import get_settings

        raw = get_settings().reel_target_duration_sec
        return max(
            REEL_MIN_DURATION_SEC, min(REEL_MAX_DURATION_SEC, raw)
        )
    except Exception:
        return REEL_TARGET_DURATION_SEC


def _get_pull_strength() -> Literal["off", "soft", "hard"]:
    """Читает ``reel_target_pull_strength`` с приоритетом PerformanceSettings.

    Resolution order (Fix 5):
    1. PerformanceSettings (UI override)
    2. core.config.Settings (env default)
    3. ``"soft"`` (safety fallback)

    Default ``soft`` выбран потому что thin arcs (< 2 development) — это
    характерный признак недоразвитого рилса, и их расширение повышает
    воспринимаемое качество без усреднения длительности всех рилсов.
    """
    try:
        from videomaker.services.runtime_settings_store import (
            get_cached_performance_settings,
        )

        perf = get_cached_performance_settings()
        if perf is not None:
            return perf.reel_target_pull_strength
    except Exception:
        pass
    try:
        from videomaker.core.config import get_settings

        return get_settings().reel_target_pull_strength
    except Exception:
        return "soft"


def _get_skip_complete_short_arcs() -> bool:
    """Читает ``skip_complete_short_arcs`` с приоритетом PerformanceSettings.

    Resolution order:
    1. PerformanceSettings (UI override из /settings/performance)
    2. core.config.Settings (env defaults)
    3. ``True`` (safety fallback — legacy behavior)
    """
    try:
        from videomaker.services.runtime_settings_store import (
            get_cached_performance_settings,
        )

        perf = get_cached_performance_settings()
        if perf is not None:
            return perf.skip_complete_short_arcs
    except Exception:
        pass
    try:
        from videomaker.core.config import get_settings

        return get_settings().skip_complete_short_arcs
    except Exception:
        return True


def _normalize_segment_bounds(
    start: float,
    end: float,
    *,
    source_duration_sec: float,
    min_target: float = REEL_MIN_DURATION_SEC,
    max_target: float = REEL_MAX_DURATION_SEC,
) -> tuple[float | None, float | None]:
    """Приводит [start, end] к допустимой длительности рилса.

    Философия padding (после ребалансировки April 2026):
    * duration > max_target (88s) → truncate вокруг центра до max_target.
    * duration >= min_target (30s) → keep natural. closure_validator может
      semantic-extend до ближайшего sentence boundary. Natural arcs 30-80s
      проходят без искажений длины.
    * duration < min_target → pad до min_target + deterministic jitter(0-10s)
      от hash(start,end,bounds). Jitter детерминирован (tests stable), но
      разнообразит final distribution (30-40s вместо плоского peak).

    Раньше padding вёл к target_duration (~52s) для ВСЕХ рилсов < target,
    что давало peak 52-56s независимо от natural length evidence.

    ``target_duration`` и ``max_target`` сохранены в сигнатуре для callers
    которые вручную задают target (composer Pass 3 pull'ит к TARGET для
    thin arcs). Default target не применяется как gravity pull.
    """

    if end <= start or source_duration_sec <= 0.0:
        return None, None

    start = max(0.0, min(start, source_duration_sec))
    end = max(0.0, min(end, source_duration_sec))
    if end <= start:
        return None, None

    duration = end - start

    # Truncate безмерно длинные evidence (>88s) вокруг центра.
    if duration > max_target:
        center = (start + end) / 2.0
        half = max_target / 2.0
        new_start = max(0.0, center - half)
        new_end = min(source_duration_sec, new_start + max_target)
        new_start = max(0.0, new_end - max_target)
        return new_start, new_end

    # Natural length >= MIN → keep as-is.
    if duration >= min_target:
        return start, end

    # Short evidence (<30s) → pad до MIN + jitter для разнообразия.
    # Jitter детерминирован от (start,end) — tests stable, но distribution varies.
    jitter_key = f"{start:.3f}|{end:.3f}".encode()
    jitter_sec = (hash(jitter_key) & 0xFF) / 255.0 * 10.0  # 0..10s
    pad_target = min_target + jitter_sec

    needed = pad_target - duration
    pad = needed / 2.0
    new_start = max(0.0, start - pad)
    new_end = min(source_duration_sec, end + pad)
    current = new_end - new_start
    if current < pad_target:
        deficit = pad_target - current
        if new_start <= 0.0:
            new_end = min(source_duration_sec, new_end + deficit)
        elif new_end >= source_duration_sec:
            new_start = max(0.0, new_start - deficit)
    # Minimum viable check: source дал хотя бы MIN?
    achieved = new_end - new_start
    if achieved < min_target:
        return None, None
    return new_start, new_end








def _trim_story_group_to_max(
    group: list[StorySegment],
    evidence_by_id: dict[str, RankedEvidenceItem],
    max_sec: float,
) -> list[StorySegment]:
    """Режет group до суммарной длительности ≤ ``max_sec``, сохраняя arc.

    Phase R3_hard_floor: когда story_doctor строит arc длиннее чем
    REEL_MAX_DURATION_SEC (например 5-минутные per_moment arcs в cba7103d),
    вместо discard делаем smart trim:

    1. **Critical roles** — hook, peak, payoff — keep все, без компрессии.
    2. **Optional roles** — setup, development — сортируются по
       ``composite_score`` из evidence, берётся максимум влезающий в budget.
    3. Результат sorted by ``source_start_sec`` для сохранения chronology.

    Edge case: если critical roles alone > max_sec — возвращаем только
    first hook + last payoff/peak. Если и это не помогло — первые 2
    critical. Composer всё равно проверит финальный range [MIN, MAX].
    """
    total = sum(seg.duration_sec for seg in group)
    if total <= max_sec:
        return list(group)

    critical_roles = {"hook", "peak", "payoff"}
    critical_items = [s for s in group if s.role in critical_roles]
    optional_items = [s for s in group if s.role not in critical_roles]

    critical_dur = sum(s.duration_sec for s in critical_items)
    remaining_budget = max_sec - critical_dur

    if remaining_budget <= 0.0:
        first_hook = next(
            (s for s in critical_items if s.role == "hook"), None
        )
        last_payoff = next(
            (
                s
                for s in reversed(critical_items)
                if s.role in ("payoff", "peak")
            ),
            None,
        )
        minimal = [s for s in (first_hook, last_payoff) if s is not None]
        if minimal:
            minimal.sort(key=lambda s: s.source_start_sec)
            return minimal
        return critical_items[:2] if len(critical_items) >= 2 else critical_items

    scored_optional: list[tuple[StorySegment, float]] = []
    for seg in optional_items:
        ev = evidence_by_id.get(seg.evidence_id)
        score = ev.composite_score if ev else 0.0
        scored_optional.append((seg, score))
    scored_optional.sort(key=lambda t: t[1], reverse=True)

    kept_optional: list[StorySegment] = []
    cumulative = 0.0
    for seg, _ in scored_optional:
        if cumulative + seg.duration_sec > remaining_budget:
            continue
        kept_optional.append(seg)
        cumulative += seg.duration_sec

    result = critical_items + kept_optional
    result.sort(key=lambda s: s.source_start_sec)
    return result


def _snap_segment_to_sentence_boundaries(
    seg_start: float,
    seg_end: float,
    words: list[TranscribedWord],
    *,
    max_shift_sec: float = 2.0,
) -> tuple[float, float]:
    """R2-lite sentence boundary snap: корректирует seg_start/seg_end к
    ближайшим word boundaries с предпочтением sentence-level разрывов.

    Предпочтение:
    * seg_start → word.start где предыдущий word оканчивался пунктуацией
      или silence ≥ _SENTENCE_LONG_PAUSE_THRESHOLD_SEC (= начало фразы)
    * seg_end → word.end где слово оканчивается пунктуацией или за ним
      silence ≥ threshold (= конец фразы)

    Если sentence boundary не найден в окне ±``max_shift_sec`` — snap к
    ближайшему word boundary (не посреди слова). Bonus score 0.5 секунды
    отдаётся sentence boundaries при равных расстояниях.

    Safety: если snap ломает порядок или сильно укорачивает segment
    (< 0.5s), возвращается вход без изменений.
    """
    if not words:
        return seg_start, seg_end

    snapped_start = seg_start
    best_start_score = float("inf")
    for i, word in enumerate(words):
        if word.start < seg_start - max_shift_sec:
            continue
        if word.start > seg_start + max_shift_sec:
            break
        is_sentence_start = False
        if i == 0:
            is_sentence_start = True
        else:
            prev = words[i - 1]
            prev_text = prev.word.strip() if prev.word else ""
            prev_ends_punct = (
                prev_text.endswith(_SENTENCE_FINAL_PUNCT) if prev_text else False
            )
            silence_before = max(0.0, word.start - prev.end)
            if (
                prev_ends_punct
                or silence_before >= _SENTENCE_LONG_PAUSE_THRESHOLD_SEC
            ):
                is_sentence_start = True
        distance = abs(word.start - seg_start)
        bonus = 0.5 if is_sentence_start else 0.0
        score = distance - bonus
        if score < best_start_score:
            best_start_score = score
            snapped_start = word.start

    snapped_end = seg_end
    best_end_score = float("inf")
    for i, word in enumerate(words):
        if word.end < seg_end - max_shift_sec:
            continue
        if word.end > seg_end + max_shift_sec:
            break
        word_text = word.word.strip() if word.word else ""
        ends_punct = (
            word_text.endswith(_SENTENCE_FINAL_PUNCT) if word_text else False
        )
        next_word_start = (
            words[i + 1].start if i + 1 < len(words) else word.end
        )
        silence_after = max(0.0, next_word_start - word.end)
        is_sentence_end = (
            ends_punct or silence_after >= _SENTENCE_LONG_PAUSE_THRESHOLD_SEC
        )
        distance = abs(word.end - seg_end)
        bonus = 0.5 if is_sentence_end else 0.0
        score = distance - bonus
        if score < best_end_score:
            best_end_score = score
            snapped_end = word.end

    if snapped_end <= snapped_start + 0.5:
        return seg_start, seg_end

    return snapped_start, snapped_end


def _arc_group_to_candidate(
    group: list[StorySegment],
    evidence_by_id: dict[str, RankedEvidenceItem],
    *,
    source: str,
    hook_fallback: str,
    source_duration_sec: float,
    cleaned_words: list[TranscribedWord] | None = None,
    extend_to_target: float | None = None,
) -> _Candidate | None:
    """Конвертирует группу StorySegment'ов в _Candidate + tokens.

    Длительность рилса = сумма длительностей segments (concat без пауз).
    Если сумма < REEL_MIN — расширяем первый segment влево и последний
    вправо в source-пространстве, ограничиваясь границами source.

    Если сумма > REEL_MAX:
      * legacy sources (base_arc/package_of_shorts/...) — возвращаем None,
        т.к. они уже прошли ``_split_arc_into_shorts``
      * ``per_moment_arc`` (multi_arc variant A) — R3_hard_floor trim через
        ``_trim_story_group_to_max`` вместо discard. Причина: story_doctor
        при узком canvas moment window может построить arc 3-5 минут
        (например в job cba7103d 26 из 27 arcs оказались > REEL_MAX и все
        были отброшены). Trim сохраняет critical roles (hook/peak/payoff)
        и берёт top-scored optional роли в budget REEL_MAX.

    ``cleaned_words`` — опционально для sentence boundary snap в
    R2-lite phase (применяется в ReelSegment bounds после построения).

    ``extend_to_target`` — если задан и превышает total_duration, segments
    симметрично расширяются в transcript context до достижения target.
    Используется только для multi_arc-sourced candidates (where Pass 3
    conditional pull не работает из-за single-group structure).
    Max extension per segment = 15s. None = legacy behavior (extension
    только до REEL_MIN).
    """
    if not group:
        return None
    if source_duration_sec <= 0.0:
        return None

    raw_duration = sum(seg.duration_sec for seg in group)
    if raw_duration > REEL_MAX_DURATION_SEC:
        if source != "per_moment_arc":
            return None
        trimmed = _trim_story_group_to_max(
            list(group), evidence_by_id, REEL_MAX_DURATION_SEC
        )
        if not trimmed:
            return None
        trimmed_duration = sum(seg.duration_sec for seg in trimmed)
        if trimmed_duration > REEL_MAX_DURATION_SEC + 0.5:
            log.warning(
                "multi_arc_trim_failed",
                original_duration=round(raw_duration, 1),
                trimmed_duration=round(trimmed_duration, 1),
                max=REEL_MAX_DURATION_SEC,
                critical_count=sum(
                    1
                    for s in trimmed
                    if s.role in ("hook", "peak", "payoff")
                ),
            )
            return None
        log.info(
            "multi_arc_trimmed",
            original_duration=round(raw_duration, 1),
            trimmed_duration=round(trimmed_duration, 1),
            original_segments=len(group),
            trimmed_segments=len(trimmed),
        )
        group = trimmed
        raw_duration = trimmed_duration

    first = group[0]
    last = group[-1]
    extend_left = 0.0
    extend_right = 0.0

    # Padding философия (после ребалансировки April 2026):
    #
    #   raw >= REEL_MIN (30s)  → keep natural (no forced pad)
    #                            closure_validator может позже semantic-extend.
    #   raw <  REEL_MIN        → pad до pad_target = MIN + jitter(0..10s).
    #                            Jitter детерминирован от hash текста первого
    #                            сегмента → разные рилсы получают разный pad,
    #                            distribution становится 30-40-35-38s вместо
    #                            плоского пика на MIN.
    #
    # Раньше padding гравитировал к REEL_TARGET=REEL_MIN, все короткие рилсы
    # оказывались ровно на minimum. Natural arcs 40-80s теперь выживают
    # в полный рост; короткие punchy — получают platform-minimum с разбросом.
    if raw_duration < REEL_MIN_DURATION_SEC:
        # Deterministic jitter для разнообразия длин в финальном наборе.
        # Hash от evidence_id первого сегмента → одинаковый вход даёт
        # одинаковый выход (tests remain deterministic).
        jitter_key = (first.evidence_id or first.text_preview or "").encode()
        jitter_sec = (hash(jitter_key) & 0xFF) / 255.0 * 10.0  # 0..10s
        pad_target = REEL_MIN_DURATION_SEC + jitter_sec

        deficit = pad_target - raw_duration
        left_room = max(0.0, first.source_start_sec)
        right_room = max(0.0, source_duration_sec - last.source_end_sec)
        half = deficit / 2.0
        extend_left = min(left_room, half)
        extend_right = min(right_room, half)
        remaining = deficit - extend_left - extend_right
        if remaining > 1e-6:
            spare_right = right_room - extend_right
            take_right = min(spare_right, remaining)
            extend_right += take_right
            remaining -= take_right
        if remaining > 1e-6:
            spare_left = left_room - extend_left
            take_left = min(spare_left, remaining)
            extend_left += take_left
            remaining -= take_left
        # Minimum viable check: если source не дал даже до REEL_MIN — отбрасываем.
        achieved = raw_duration + extend_left + extend_right
        if achieved < REEL_MIN_DURATION_SEC - 1e-6:
            return None

    segments: list[ReelSegment] = []
    for idx, seg in enumerate(group):
        seg_start = seg.source_start_sec - extend_left if idx == 0 else seg.source_start_sec
        seg_end = seg.source_end_sec + extend_right if idx == len(group) - 1 else seg.source_end_sec
        # Числовая устойчивость под клампом.
        seg_start = max(0.0, seg_start)
        seg_end = min(source_duration_sec, seg_end)
        # R2-lite sentence boundary snap (2026-04-21): для multi_arc реалов
        # корректируем seg_start/seg_end к word-boundaries с предпочтением
        # sentence-level разрывов. Избегаем обрыва на середине слова или
        # фразы. Snap в окне ±2 сек; если sentence boundary не найден —
        # fallback к ближайшему word boundary.
        if source == "per_moment_arc" and cleaned_words:
            seg_start, seg_end = _snap_segment_to_sentence_boundaries(
                seg_start, seg_end, cleaned_words, max_shift_sec=2.0
            )
            seg_start = max(0.0, seg_start)
            seg_end = min(source_duration_sec, seg_end)
        if seg_end <= seg_start:
            continue
        segments.append(
            ReelSegment(
                source_start=seg_start,
                source_end=seg_end,
                reasoning=seg.reasoning or f"{seg.role} from {source}",
                order_role=_ROLE_MAP.get(seg.role, "development"),  # type: ignore[arg-type]
            )
        )
    if not segments:
        return None

    # Защита от overlap: когда Story Doctor или _pull_closure_from_arc
    # положили в группу два сегмента с пересекающимся source-диапазоном
    # (два агента нашли один и тот же кусок речи под разными ролями),
    # ffmpeg при concat проигрывает одну и ту же фразу дважды. Отсеиваем.
    #
    # Multi-arc variant A: для per_moment_arc используем loose threshold
    # (0.90 вместо 0.60) — story_doctor строит arcs вокруг разных canvas
    # moments, их сегменты могут legitimate пересекаться под разными углами
    # (OpusClip overproduction pattern).
    temporal_dup_ratio = (
        _MULTI_ARC_TEMPORAL_OVERLAP_DUP_RATIO
        if source == "per_moment_arc"
        else _TEMPORAL_OVERLAP_DUP_RATIO
    )
    segments = _dedupe_temporal_overlaps(
        segments, temporal_dup_ratio=temporal_dup_ratio
    )
    if not segments:
        return None

    duration = sum(s.source_end - s.source_start for s in segments)

    # Source extension (fix 3/4, 2026-04-22): для multi_arc-sourced
    # candidate если extend_to_target задан и превышает total_duration,
    # расширяем каждый segment симметрично через transcript context.
    # Это настоящий fix pull-to-target для multi_arc: внутри одной
    # StoryScript нет соседних groups для мёрджа, зато есть transcript
    # context вокруг каждого evidence'а. Max extension per segment = 15s
    # чтобы не тянуть произвольный кусок транскрипта.
    if (
        extend_to_target is not None
        and extend_to_target > REEL_MIN_DURATION_SEC
        and duration < extend_to_target
        and duration >= REEL_MIN_DURATION_SEC
    ):
        deficit = extend_to_target - duration
        per_segment_bonus = min(15.0, deficit / max(1, len(segments)))
        extended_segments: list[ReelSegment] = []
        for seg in segments:
            new_start = max(0.0, seg.source_start - per_segment_bonus / 2.0)
            new_end = min(
                source_duration_sec, seg.source_end + per_segment_bonus / 2.0
            )
            if cleaned_words:
                new_start, new_end = _snap_segment_to_sentence_boundaries(
                    new_start, new_end, cleaned_words, max_shift_sec=2.0
                )
                new_start = max(0.0, new_start)
                new_end = min(source_duration_sec, new_end)
            if new_end <= new_start:
                extended_segments.append(seg)
                continue
            extended_segments.append(
                seg.model_copy(
                    update={"source_start": new_start, "source_end": new_end}
                )
            )
        segments = _dedupe_temporal_overlaps(
            extended_segments, temporal_dup_ratio=temporal_dup_ratio
        )
        if not segments:
            return None
        duration = sum(s.source_end - s.source_start for s in segments)

    if duration < REEL_MIN_DURATION_SEC - 0.05 or duration > REEL_MAX_DURATION_SEC + 0.05:
        return None

    # Hook text: первый hook-segment либо первый segment. Fallback = central_theme.
    hook_text = _select_hook_text(group, evidence_by_id, fallback=hook_fallback)

    # Score = среднее composite_score с visual penalty per-segment.
    # Формула: composite * (0.6 + 0.4 * visual_score). При vision disabled
    # visual_score=1.0 → multiplier=1.0 (no-op). При полностью провальном
    # визуале (0.0) — only 60% базового score (penalty, не блокировка).
    scores: list[float] = []
    for seg in group:
        ev = evidence_by_id.get(seg.evidence_id)
        if ev is None:
            continue
        visual_multiplier = 0.6 + 0.4 * seg.visual_score
        scores.append(ev.composite_score * visual_multiplier)
    score = sum(scores) / len(scores) if scores else 0.5

    # Токены для uniqueness — по всем evidence-текстам группы, плюс hook_text.
    tokens: set[str] = set()
    for seg in group:
        ev = evidence_by_id.get(seg.evidence_id)
        if ev:
            tokens |= _tokenize(ev.text)
        elif seg.text_preview:
            tokens |= _tokenize(seg.text_preview)
    tokens |= _tokenize(hook_text)

    # reel_id временный — финальная нумерация в _renumber_and_finalize.
    first_start = int(group[0].source_start_sec)
    reel_id = _safe_reel_id(f"{source[:8]}-{first_start}")

    plan = ReelPlan(
        reel_id=reel_id,
        hook=_trim_hook(hook_text),
        predicted_duration_sec=duration,
        target_audience="",
        segments=segments,
    )
    return _Candidate(score=score, plan=plan, tokens=tokens, source=source)


def _select_hook_text(
    group: list[StorySegment],
    evidence_by_id: dict[str, RankedEvidenceItem],
    *,
    fallback: str,
) -> str:
    """Выбирает текст hook'а: hook-segment → первый segment → fallback."""
    hook_segments = [s for s in group if s.role == "hook"] or group
    first = hook_segments[0]
    ev = evidence_by_id.get(first.evidence_id)
    if ev and ev.text:
        return ev.text
    if first.text_preview:
        return first.text_preview
    return fallback or "рилс"


# ---------------------------------------------------------------------------
# Greedy Jaccard uniqueness
# ---------------------------------------------------------------------------


#: Порог пересечения source-range для cross-reel segment dedup (BUG-#J).
#: Два рилса не могут использовать один и тот же кусок source-видео если их
#: сегменты пересекаются на ≥30% длительности — иначе зритель видит один и
#: тот же payoff/hook в двух рилсах подряд.
_CROSS_REEL_SEGMENT_OVERLAP_RATIO = 0.3


def _populate_candidate_embeddings(
    candidates: list[_Candidate],
    ranked: RankedEvidence,
) -> None:
    """Заполняет ``cand.avg_embedding`` на основе ranked.items.

    Lookup-index: ``(round(start,1), round(end,1)) → embedding``.
    Для каждого сегмента кандидата ищем совпадение в index; собираем
    ненулевые embeddings, усредняем → avg_embedding. Если ни один сегмент
    не нашёлся в index — ``avg_embedding`` остаётся None, и
    ``_greedy_uniqueness_filter`` обходит этот кандидат по legacy path
    (только Jaccard + segment overlap).

    Mutating in-place — дешевле чем возвращать новый список dataclass'ов,
    и _Candidate не frozen.
    """
    index: dict[tuple[float, float], list[float]] = {}
    for item in ranked.items:
        if item.embedding is None:
            continue
        key = (round(item.start, 1), round(item.end, 1))
        index[key] = item.embedding

    if not index:
        return

    for cand in candidates:
        collected: list[list[float]] = []
        for seg in cand.plan.segments:
            key = (round(seg.source_start, 1), round(seg.source_end, 1))
            emb = index.get(key)
            if emb:
                collected.append(emb)
        if not collected:
            continue
        cand.avg_embedding = _average_embeddings(collected)


def _average_embeddings(embeddings: list[list[float]]) -> list[float] | None:
    """Среднее по элементам одинаковой размерности (или None при mismatch)."""
    if not embeddings:
        return None
    dim = len(embeddings[0])
    if any(len(e) != dim for e in embeddings):
        return None
    sums = [0.0] * dim
    for e in embeddings:
        for i, v in enumerate(e):
            sums[i] += v
    n = len(embeddings)
    return [v / n for v in sums]


def _greedy_uniqueness_filter(
    candidates: list[_Candidate],
    *,
    max_count: int,
    threshold: float = UNIQUENESS_JACCARD_THRESHOLD,
    semantic_threshold: float = SEMANTIC_REEL_SIMILARITY_THRESHOLD,
    cross_reel_overlap_ratio: float = _CROSS_REEL_SEGMENT_OVERLAP_RATIO,
) -> list[_Candidate]:
    """Жадный фильтр с тремя уровнями дедупа:

    1. **Cross-reel segment overlap** — один и тот же source-диапазон не
       может попасть в два рилса (BUG-#J fix). Два разных рилса не могут
       делить payoff/hook сцену — иначе зритель видит одно и то же дважды.
       Threshold ``cross_reel_overlap_ratio`` (default 0.3).
    2. **Semantic similarity (T1.1 slice 4)** — cosine(avg_embedding) ≥
       ``semantic_threshold`` (0.88). Ловит рилсы, которые не пересекаются
       по source-времени но рассказывают одну мысль другими сценами.
       Включается только если у обоих кандидатов avg_embedding is not None
       (graceful-degrade при API fail / mismatch).
    3. **Jaccard текстов рилсов** — fallback / дополнительный сигнал для
       лексического сходства (tokens ≥ ``threshold``).

    В multi_arc_variant_a mode передаются loose thresholds
    (``_MULTI_ARC_*`` константы) чтобы пропустить overlapping arcs разных
    углов подачи одной темы (OpusClip overproduction pattern).
    """
    accepted: list[_Candidate] = []
    used_segments: list[tuple[float, float]] = []
    rejected_level1 = 0  # cross-reel segment overlap
    rejected_level2 = 0  # semantic similarity
    rejected_level3 = 0  # Jaccard tokens
    rejected_ids_cross_reel: list[str] = []
    rejected_ids_semantic: list[str] = []
    rejected_ids_jaccard: list[str] = []
    cap_reached = False

    for cand in candidates:
        if len(accepted) >= max_count:
            cap_reached = True
            break

        cand_segments = [
            (s.source_start, s.source_end) for s in cand.plan.segments
        ]

        # Уровень 1: проверка по source-диапазонам ПЕРВОЙ (дешевле остальных).
        has_overlap = _candidate_overlaps_used_segments(
            cand_segments, used_segments, ratio=cross_reel_overlap_ratio
        )
        if has_overlap:
            rejected_level1 += 1
            rejected_ids_cross_reel.append(_candidate_label(cand))
            continue

        # Уровень 2: semantic similarity (если embeddings доступны у обоих).
        if cand.avg_embedding is not None:
            is_semantic_dup = any(
                prev.avg_embedding is not None
                and cosine_similarity(cand.avg_embedding, prev.avg_embedding)
                >= semantic_threshold
                for prev in accepted
            )
            if is_semantic_dup:
                rejected_level2 += 1
                rejected_ids_semantic.append(_candidate_label(cand))
                continue

        # Уровень 3: Jaccard семантики (только если тянущий токены сэмпл).
        if len(cand.tokens) >= MIN_TOKENS_FOR_UNIQUENESS_CHECK:
            is_lexical_duplicate = any(
                _jaccard(cand.tokens, prev.tokens) >= threshold for prev in accepted
            )
            if is_lexical_duplicate:
                rejected_level3 += 1
                rejected_ids_jaccard.append(_candidate_label(cand))
                continue

        accepted.append(cand)
        used_segments.extend(cand_segments)

    log.info(
        "greedy_uniqueness_breakdown",
        input=len(candidates),
        accepted=len(accepted),
        rejected_cross_reel=rejected_level1,
        rejected_semantic=rejected_level2,
        rejected_jaccard=rejected_level3,
        cap_reached=cap_reached,
        max_count=max_count,
        cross_reel_overlap_ratio=cross_reel_overlap_ratio,
        semantic_threshold=semantic_threshold,
        jaccard_threshold=threshold,
        rejected_ids_cross_reel=rejected_ids_cross_reel,
        rejected_ids_semantic=rejected_ids_semantic,
        rejected_ids_jaccard=rejected_ids_jaccard,
    )
    return accepted


def _candidate_overlaps_used_segments(
    cand_segments: list[tuple[float, float]],
    used_segments: list[tuple[float, float]],
    *,
    ratio: float,
) -> bool:
    """True если хотя бы один сегмент кандидата пересекается с уже
    использованными в предыдущих рилсах на ≥ratio собственной длительности."""

    for c_start, c_end in cand_segments:
        c_len = max(1e-6, c_end - c_start)
        for u_start, u_end in used_segments:
            inter_start = max(c_start, u_start)
            inter_end = min(c_end, u_end)
            inter = max(0.0, inter_end - inter_start)
            if inter / c_len >= ratio:
                return True
    return False


#: Порог пересечения по времени, при котором сегмент считается дублем уже
#: принятого. Консервативно: 60%+ overlap = действительно тот же кусок
#: (у нас overlap бывает когда два агента помечают одну фразу разными
#: ролями; частичное пересечение 20-40% — легитимный A/B приём, не режем).
_TEMPORAL_OVERLAP_DUP_RATIO = 0.6


def _dedupe_temporal_overlaps(
    segments: list[ReelSegment],
    *,
    temporal_dup_ratio: float = _TEMPORAL_OVERLAP_DUP_RATIO,
) -> list[ReelSegment]:
    """Отбрасывает сегменты с overlap по source-времени ≥ threshold с уже принятым.

    Сохраняет порядок (hook идёт первым и принимается безусловно). Второй и
    далее сегменты проверяются на пересечение со всеми уже принятыми — если
    хотя бы один перекрывается на ``temporal_dup_ratio``+ собственной длительности,
    сегмент отбрасывается. Это закрывает баг `_pull_closure_from_arc`, который мог
    добавить сегмент с тем же куском источника что уже в hook.

    ``temporal_dup_ratio`` — override для multi_arc mode (передаётся
    ``_MULTI_ARC_TEMPORAL_OVERLAP_DUP_RATIO=0.90`` чтобы позволить
    overlapping arcs разных углов подачи).
    """
    if len(segments) <= 1:
        return list(segments)

    accepted: list[ReelSegment] = []
    for seg in segments:
        seg_len = max(1e-6, seg.source_end - seg.source_start)
        is_duplicate = False
        for prev in accepted:
            inter_start = max(seg.source_start, prev.source_start)
            inter_end = min(seg.source_end, prev.source_end)
            inter = max(0.0, inter_end - inter_start)
            if inter / seg_len >= temporal_dup_ratio:
                is_duplicate = True
                break
        if not is_duplicate:
            accepted.append(seg)
    return accepted


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _target_count_by_duration(source_duration_sec: float) -> tuple[int, int]:
    """Returns (floor, ceiling) для N рилсов по длительности источника.

    Критерии Никиты для predictable reel count (Phase 2 tech-debt cleanup):
      - <10 мин → (3, 8)
      - 10-15 мин → (10, 15)
      - 15-30 мин → (12, 20)
      - 30-60 мин → (15, 25)
      - 60+ мин → (20, 30)
    """
    minutes = max(0.0, source_duration_sec) / 60.0
    if minutes < 10:
        return (3, 8)
    if minutes < 15:
        return (10, 15)
    if minutes < 30:
        return (12, 20)
    if minutes < 60:
        return (15, 25)
    return (20, 30)


def _enforce_reel_count_floor_ceiling(
    ranked: list[_Candidate],
    *,
    source_duration_sec: float,
    jaccard_threshold: float,
) -> list[_Candidate]:
    """Post-ranking фильтр: Jaccard token-overlap dedup + ceiling по длительности.

    Отдельный слой поверх ``_greedy_uniqueness_filter``: применяется уже после
    финального ранжирования кандидатов и гарантирует predictable N рилсов
    независимо от сложных цепочек дедупов выше (cross-reel segment overlap,
    semantic similarity, lexical Jaccard). Floor не раздуваем — если после
    dedup осталось меньше target, новые рилсы не создаём.
    """

    floor, ceiling = _target_count_by_duration(source_duration_sec)

    accepted: list[_Candidate] = []
    accepted_tokens: list[set[str]] = []
    for cand in ranked:
        cand_tokens = cand.tokens
        if not cand_tokens:
            # Без текста — принимаем как есть (не используем в дальнейших
            # Jaccard сравнениях).
            accepted.append(cand)
            accepted_tokens.append(set())
            continue
        max_sim = max(
            (_jaccard(cand_tokens, prev) for prev in accepted_tokens if prev),
            default=0.0,
        )
        if max_sim < jaccard_threshold:
            accepted.append(cand)
            accepted_tokens.append(cand_tokens)

    if len(accepted) > ceiling:
        accepted = accepted[:ceiling]
    # floor используем только для логирования — new reels не создаём
    log.debug(
        "reel_count_floor_ceiling_eval",
        floor=floor,
        ceiling=ceiling,
        after_dedup=len(accepted),
    )
    return accepted


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    """Извлекает токены-слова нижнего регистра. Короткие (<3 символов) убираем."""
    if not text:
        return set()
    tokens = _TOKENIZER.findall(text.lower())
    return {t for t in tokens if len(t) >= 3}


def _category_to_role(category: str) -> str:
    """RankedEvidence.category → ReelSegment.order_role."""
    return {
        "hook_candidate": "hook",
        "peak_candidate": "peak",
        "payoff_candidate": "payoff",
        "development_material": "development",
        "cutaway_material": "development",
    }.get(category, "development")


def _trim_hook(text: str) -> str:
    """Обрезает hook до разумной длины (≤140 символов)."""
    clean = (text or "рилс").strip()
    if len(clean) <= 140:
        return clean
    return clean[:137].rstrip() + "..."


_REEL_ID_SAFE = re.compile(r"[^A-Za-z0-9_-]")


def _safe_reel_id(raw: str) -> str:
    """Приводит произвольную строку к pattern ^[A-Za-z0-9_-]{1,32}$."""
    cleaned = _REEL_ID_SAFE.sub("-", raw)[:32]
    return cleaned or "r"


#: Multi-segment arc-based candidates получают ×1.25 к score в greedy
#: filter. Значение 1.25 — эмпирический баланс: singleton с топ-score 0.95
#: без боoста побеждал arc-candidate со avg 0.85 (0.85 < 0.95). С boost
#: 0.85 × 1.25 = 1.06 > 0.95, arc побеждает. Больше 1.3 — arc всегда
#: доминирует даже на слабом evidence, это ломает diversity.
_ARC_NARRATIVE_BOOST = 1.25
_ARC_BOOSTED_SOURCES = {
    "base_arc",
    "package_of_shorts",
    "thematic_cluster",
    "per_moment_arc",
}


def _apply_arc_narrative_boost(candidates: list[_Candidate]) -> None:
    """Multiplies score of multi-segment arc-based candidates by
    ``_ARC_NARRATIVE_BOOST``.

    Без boost'а highest-score single evidence (composite 0.9-0.95) всегда
    обгоняют arc-based candidates (avg 0.8-0.88) в greedy filter — все
    финальные рилсы деградируют в evidence_single с 1 segment каждый.
    Boost возвращает приоритет драматургической cборке Картозии:
    hook → setup → peak → payoff как одно целое ценнее одинокой
    punchy реплики даже если её composite выше.
    """
    for cand in candidates:
        if cand.source in _ARC_BOOSTED_SOURCES and len(cand.plan.segments) >= 2:
            cand.score *= _ARC_NARRATIVE_BOOST


def _apply_cross_context_penalty(
    candidates: list[_Candidate],
    ranked: RankedEvidence,
) -> None:
    """T10.9 — Cross-Context Risk penalty на основе temporal gap и semantic
    distance между segments кандидата.

    Для single-segment кандидатов penalty всегда 0 (cross-context невозможен).
    Penalty применяется как multiplier к candidate.score:
    new_score = score * (1 - 0.3 * risk.score)
    Максимум −30% веса даже при полном cross-context — candidate остаётся
    жизнеспособным, но опускается в ранжировании.

    Semantic signal извлекается через best-overlap matching ranked items:
    для каждого ReelSegment ищем ranked.item чей (start, end) пересекается
    c segment на >= 50% и берём его embedding.
    """
    from videomaker.services.cross_context_risk import (
        SegmentRiskInput,
        assess_cross_context_risk,
    )

    for cand in candidates:
        segments = cand.plan.segments
        if len(segments) < 2:
            continue
        risk_inputs: list[SegmentRiskInput] = []
        for seg in segments:
            embedding = _find_overlapping_embedding(
                ranked, seg.source_start, seg.source_end
            )
            risk_inputs.append(
                SegmentRiskInput(
                    source_start_sec=seg.source_start,
                    source_end_sec=seg.source_end,
                    embedding=embedding,
                    sentiment_score=None,
                    text_preview="",
                )
            )
        risk = assess_cross_context_risk(risk_inputs)
        # T9 — сохраняем risk.score в ReelPlan чтобы frontend мог показать
        # warning badge при risk > 0.6. Пишем даже score=0 — это явное
        # указание что composer посчитал risk и не нашёл проблем.
        cand.plan.cross_context_risk = float(risk.score)
        if risk.score > 0:
            cand.score *= 1.0 - 0.3 * risk.score


def _find_overlapping_embedding(
    ranked: RankedEvidence, start_sec: float, end_sec: float
) -> list[float] | None:
    """Ищет ranked.item с максимальным overlap по (start, end) и возвращает
    его embedding. None если overlap < 0.5 для всех."""
    best_overlap = 0.0
    best_embedding: list[float] | None = None
    seg_duration = max(0.001, end_sec - start_sec)
    for item in ranked.items:
        if not getattr(item, "embedding", None):
            continue
        overlap = max(
            0.0,
            min(end_sec, item.end) - max(start_sec, item.start),
        )
        ratio = overlap / seg_duration
        if ratio > best_overlap and ratio >= 0.5:
            best_overlap = ratio
            best_embedding = list(item.embedding or [])
    return best_embedding


def _apply_pacing_profile_preference(
    candidates: list[_Candidate],
    profile_name: str,
) -> None:
    """T10.5 — Consistency signature: preference для кандидатов чья duration
    близка к shot_duration_mode выбранного pacing profile.

    Penalty = 10% score за каждые 50% отклонения от mode. Это мягкая
    preference — не исключает кандидатов с sub-optimal duration, только
    смещает ранжирование в сторону consistent pacing.
    """
    from videomaker.services.pacing_profile import get_template

    template = get_template(profile_name)
    target_duration_sec = template.shot_duration_mode * 10  # approx reel 10 shots
    # reel_duration предпочитаем 20-60 сек независимо от pacing profile
    for cand in candidates:
        duration = cand.plan.predicted_duration_sec
        if duration <= 0:
            continue
        # Preference для рилсов где duration ближе к ожидаемому для profile:
        # dynamic → короче (~20-35), documentary → длиннее (~40-60)
        expected = max(20.0, min(60.0, target_duration_sec * 0.2))
        rel_deviation = abs(duration - expected) / expected
        penalty = min(0.15, rel_deviation * 0.1)
        cand.score *= 1.0 - penalty


def _renumber_and_finalize(candidates: list[_Candidate]) -> list[ReelPlan]:
    """Переименовывает reel_id в последовательное r1/r2/… и возвращает ReelPlan-ы."""
    result: list[ReelPlan] = []
    for i, cand in enumerate(candidates, start=1):
        plan = cand.plan
        result.append(
            ReelPlan(
                reel_id=f"r{i}",
                hook=plan.hook,
                predicted_duration_sec=plan.predicted_duration_sec,
                target_audience=plan.target_audience,
                segments=plan.segments,
                cross_context_risk=plan.cross_context_risk,
            )
        )
    return result
