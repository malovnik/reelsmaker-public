"""Cross-Chapter Ranker — Phase 5 top-down pipeline.

Финальный selection-этап: из N ExtendedArc выбирает top-K ReelCandidate
для рендера. Greedy selection с тремя constraint'ами:

    1. **Composite score** = 0.4 × hook.score + 0.4 × arc.arc_score +
       0.2 × duration_fit. Сортировка по убыванию.
    2. **Novelty** — cosine similarity с уже принятыми рилсами через
       embeddings payoff_text. Если similarity > NOVELTY_COSINE_THRESHOLD
       (0.72) → reject (topic dup).
    3. **Diversity** — не более CLOSURE_TYPE_MAX_PER_RANK (2) рилсов с
       одинаковым closure_type в топ-N. После cap закрытого типа
       пропускаем arcs этого типа, но не отбрасываем навсегда (резерв).

Output: ``list[ReelCandidate]`` совместимый с существующим render stage.
ReelCandidate упакован в wrapper для downstream composer / renderer,
но совместим с ReelPlan через конвертацию.

Entry: ``rank_and_select(extended_arcs, *, target_count, settings=None,
embedder=None) -> list[ReelCandidate]``

Graceful degradation: если embedding API недоступен → novelty penalty
считаем через Jaccard token overlap payoff_text (дешёвый fallback).
"""

from __future__ import annotations

import re
from collections import Counter

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.narrative import ClosureType, ExtendedArc, ReelCandidate
from videomaker.services.canvas_embedder import cosine_similarity, embed_texts
from videomaker.services.narrative.constants import (
    CLOSURE_TYPE_MAX_PER_RANK,
    NOVELTY_COSINE_THRESHOLD,
    REEL_MAX_DURATION_SEC,
    REEL_MIN_DURATION_SEC,
    REEL_TARGET_DURATION_SEC,
)

log = get_logger(__name__)

#: Веса composite score. Сумма = 1.0. Hook и arc_score вес 0.4 каждая,
#: duration_fit — 0.2 (less critical, но важен для platform algorithm).
_W_HOOK: float = 0.4
_W_ARC: float = 0.4
_W_DURATION_FIT: float = 0.2

#: Если embeddings fail — fallback на Jaccard по токенам payoff_text.
#: Порог: 0.6 Jaccard overlap = считаем topic dup.
_JACCARD_NOVELTY_THRESHOLD: float = 0.6

#: Duration fit score: линейно 1.0 на TARGET, 0.5 на MIN/MAX.
_DURATION_FIT_PEAK: float = REEL_TARGET_DURATION_SEC
_DURATION_FIT_EDGE_MIN: float = REEL_MIN_DURATION_SEC
_DURATION_FIT_EDGE_MAX: float = REEL_MAX_DURATION_SEC


async def rank_and_select(
    extended_arcs: list[ExtendedArc],
    *,
    target_count: int,
    settings: Settings | None = None,
) -> list[ReelCandidate]:
    """Ранжирует и выбирает top-N рилсов из ExtendedArc.

    ``target_count`` — желаемое число рилсов. Если валидных arcs меньше —
    возвращаем столько, сколько есть. Если больше — greedy top с
    constraint-aware filtering.
    """

    if not extended_arcs:
        return []
    if target_count <= 0:
        return []

    cfg = settings or get_settings()

    # Валидация: отбросить arcs вне допустимого duration диапазона.
    valid_arcs = [a for a in extended_arcs if _is_duration_valid(a)]
    invalid_count = len(extended_arcs) - len(valid_arcs)
    if invalid_count > 0:
        log.info(
            "cross_chapter_ranker_invalid_durations_dropped",
            dropped=invalid_count,
            kept=len(valid_arcs),
        )
    if not valid_arcs:
        return []

    # Compute composite scores.
    scored = _score_all(valid_arcs)

    # Embed payoff_text для novelty calculation.
    embeddings = await _embed_payoffs(valid_arcs, settings=cfg)
    use_embeddings = embeddings is not None and len(embeddings) == len(valid_arcs)
    if not use_embeddings:
        log.warning(
            "cross_chapter_ranker_embeddings_fallback_to_jaccard",
            arcs=len(valid_arcs),
        )

    embedding_by_index = (
        {i: embeddings[i] for i in range(len(valid_arcs))}  # type: ignore[index]
        if use_embeddings and embeddings is not None
        else {}
    )

    # Greedy selection с constraints.
    selected: list[ReelCandidate] = []
    closure_counter: Counter[ClosureType] = Counter()

    # Sort by composite descending.
    ordered_indices = sorted(
        range(len(valid_arcs)),
        key=lambda i: scored[i]["composite"],
        reverse=True,
    )

    rank = 0
    for idx in ordered_indices:
        if len(selected) >= target_count:
            break

        arc = valid_arcs[idx]
        closure_type = arc.arc.closure_type

        # Diversity constraint: cap по closure_type.
        if closure_counter[closure_type] >= CLOSURE_TYPE_MAX_PER_RANK:
            log.debug(
                "cross_chapter_ranker_diversity_skip",
                chapter_id=arc.arc.chapter_id,
                closure_type=closure_type,
                cap=CLOSURE_TYPE_MAX_PER_RANK,
            )
            continue

        # Novelty constraint.
        novelty_score = _compute_novelty(
            idx,
            arc,
            selected_indices=[s.rank - 1 for s in selected],
            valid_arcs=valid_arcs,
            embedding_by_index=embedding_by_index,
            use_embeddings=use_embeddings,
        )
        # Novelty reject если > threshold similarity (= < 1 - threshold novelty).
        min_novelty = 1.0 - NOVELTY_COSINE_THRESHOLD if use_embeddings else (
            1.0 - _JACCARD_NOVELTY_THRESHOLD
        )
        if novelty_score < min_novelty:
            log.debug(
                "cross_chapter_ranker_novelty_skip",
                chapter_id=arc.arc.chapter_id,
                novelty=round(novelty_score, 3),
                min_required=round(min_novelty, 3),
            )
            continue

        rank += 1
        final_score = scored[idx]["composite"] * novelty_score
        reason = _build_selection_reason(
            scored[idx],
            novelty_score=novelty_score,
            closure_counter=closure_counter,
            closure_type=closure_type,
        )
        selected.append(
            ReelCandidate(
                id=f"reel_{rank:03d}",
                source_arc=arc,
                rank=rank,
                final_score=_clamp01(final_score),
                novelty_score=_clamp01(novelty_score),
                selection_reason=reason,
            )
        )
        closure_counter[closure_type] += 1

    # Если после diversity/novelty остались места, делаем второй проход
    # без diversity cap (но с novelty check). Это защита: на узких темах
    # мы бы иначе выдали 1-2 рилса вместо target_count.
    if len(selected) < target_count:
        selected = _second_pass_fill(
            selected=selected,
            ordered_indices=ordered_indices,
            valid_arcs=valid_arcs,
            scored=scored,
            embedding_by_index=embedding_by_index,
            use_embeddings=use_embeddings,
            target_count=target_count,
        )

    log.info(
        "cross_chapter_ranker_done",
        total_arcs=len(valid_arcs),
        selected=len(selected),
        target=target_count,
        use_embeddings=use_embeddings,
        closure_distribution=dict(closure_counter),
    )
    return selected


# ─── Scoring ─────────────────────────────────────────────────────────────


def _score_all(arcs: list[ExtendedArc]) -> list[dict[str, float]]:
    """Composite score для каждого arc."""

    scored: list[dict[str, float]] = []
    for arc in arcs:
        hook_score = arc.arc.hook.score
        arc_score = arc.arc.arc_score
        duration_fit = _duration_fit_score(arc.duration_sec())
        composite = (
            _W_HOOK * hook_score + _W_ARC * arc_score + _W_DURATION_FIT * duration_fit
        )
        scored.append(
            {
                "hook": hook_score,
                "arc": arc_score,
                "duration_fit": duration_fit,
                "composite": composite,
            }
        )
    return scored


def _duration_fit_score(duration_sec: float) -> float:
    """Линейный score: 1.0 на TARGET (42s), 0.5 на MIN (28s) / MAX (75s).

    Формула: линейный interpolant между peak и каждым edge.
    Вне [MIN, MAX] — 0.0 (уже отфильтровано в valid_arcs).
    """

    if duration_sec <= 0:
        return 0.0
    if duration_sec < _DURATION_FIT_EDGE_MIN or duration_sec > _DURATION_FIT_EDGE_MAX:
        return 0.0
    if duration_sec <= _DURATION_FIT_PEAK:
        # Линейно 0.5 на MIN → 1.0 на PEAK.
        ratio = (duration_sec - _DURATION_FIT_EDGE_MIN) / (
            _DURATION_FIT_PEAK - _DURATION_FIT_EDGE_MIN
        )
        return 0.5 + 0.5 * ratio
    # Линейно 1.0 на PEAK → 0.5 на MAX.
    ratio = (duration_sec - _DURATION_FIT_PEAK) / (
        _DURATION_FIT_EDGE_MAX - _DURATION_FIT_PEAK
    )
    return 1.0 - 0.5 * ratio


# ─── Novelty computation ─────────────────────────────────────────────────


async def _embed_payoffs(
    arcs: list[ExtendedArc],
    *,
    settings: Settings,
) -> list[list[float]] | None:
    """Embed payoff_text через Gemini embeddings. None при сбое API."""

    texts = [a.arc.payoff_text or a.arc.hook.text for a in arcs]
    return await embed_texts(texts, settings=settings)


def _compute_novelty(
    idx: int,
    arc: ExtendedArc,
    *,
    selected_indices: list[int],
    valid_arcs: list[ExtendedArc],
    embedding_by_index: dict[int, list[float]],
    use_embeddings: bool,
) -> float:
    """1 - max similarity с уже selected."""

    if not selected_indices:
        return 1.0

    if use_embeddings:
        current_embedding = embedding_by_index.get(idx)
        if current_embedding is None:
            return 1.0
        max_sim = 0.0
        for sel_idx in selected_indices:
            sel_embedding = embedding_by_index.get(sel_idx)
            sim = cosine_similarity(current_embedding, sel_embedding)
            if sim > max_sim:
                max_sim = sim
        return max(0.0, min(1.0, 1.0 - max_sim))

    # Fallback: Jaccard over tokens.
    current_tokens = _tokenize(arc.arc.payoff_text or arc.arc.hook.text)
    max_jaccard = 0.0
    for sel_idx in selected_indices:
        sel_arc = valid_arcs[sel_idx]
        sel_tokens = _tokenize(sel_arc.arc.payoff_text or sel_arc.arc.hook.text)
        jaccard = _jaccard(current_tokens, sel_tokens)
        if jaccard > max_jaccard:
            max_jaccard = jaccard
    return max(0.0, 1.0 - max_jaccard)


def _tokenize(text: str) -> set[str]:
    """Lowercase токенизация без пунктуации для Jaccard."""

    if not text:
        return set()
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return {t for t in cleaned.split() if len(t) >= 3}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return intersection / union


# ─── Second pass fill (без diversity cap) ─────────────────────────────────


def _second_pass_fill(
    *,
    selected: list[ReelCandidate],
    ordered_indices: list[int],
    valid_arcs: list[ExtendedArc],
    scored: list[dict[str, float]],
    embedding_by_index: dict[int, list[float]],
    use_embeddings: bool,
    target_count: int,
) -> list[ReelCandidate]:
    """Заполнить оставшиеся места без diversity cap, но с novelty check.

    Используется когда narrow set closure_type в материале — лучше выдать
    несколько однотипных closure, чем оставить пустые слоты.
    """

    taken_chapter_ids = {s.source_arc.arc.chapter_id for s in selected}
    taken_indices = [s.rank - 1 for s in selected]
    current = list(selected)
    rank = len(current)

    # Second pass: более мягкий порог. Если первый проход не заполнил
    # target_count, значит материал узкий — лучше выдать топики с higher
    # similarity чем оставить пустые слоты. Threshold 0.85 = reject только
    # явные дубли ("practically identical"), а не related topics.
    second_pass_sim_cap = 0.85
    min_novelty = 1.0 - second_pass_sim_cap

    for idx in ordered_indices:
        if len(current) >= target_count:
            break
        arc = valid_arcs[idx]
        if arc.arc.chapter_id in taken_chapter_ids:
            continue

        novelty_score = _compute_novelty(
            idx,
            arc,
            selected_indices=taken_indices,
            valid_arcs=valid_arcs,
            embedding_by_index=embedding_by_index,
            use_embeddings=use_embeddings,
        )
        if novelty_score < min_novelty:
            continue

        rank += 1
        final_score = scored[idx]["composite"] * novelty_score
        current.append(
            ReelCandidate(
                id=f"reel_{rank:03d}",
                source_arc=arc,
                rank=rank,
                final_score=_clamp01(final_score),
                novelty_score=_clamp01(novelty_score),
                selection_reason="second_pass_no_diversity_cap",
            )
        )
        taken_chapter_ids.add(arc.arc.chapter_id)
        taken_indices.append(idx)

    return current


# ─── Validation + helpers ─────────────────────────────────────────────────


def _is_duration_valid(arc: ExtendedArc) -> bool:
    duration = arc.duration_sec()
    return REEL_MIN_DURATION_SEC <= duration <= REEL_MAX_DURATION_SEC


def _build_selection_reason(
    scores: dict[str, float],
    *,
    novelty_score: float,
    closure_counter: Counter[ClosureType],
    closure_type: ClosureType,
) -> str:
    parts = [
        f"hook={scores['hook']:.2f}",
        f"arc={scores['arc']:.2f}",
        f"dur_fit={scores['duration_fit']:.2f}",
        f"novelty={novelty_score:.2f}",
    ]
    if closure_counter[closure_type] == 0:
        parts.append(f"first_{closure_type}")
    return " | ".join(parts)[:200]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


__all__ = ["rank_and_select"]
