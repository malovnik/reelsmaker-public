"""T10.6 — Smart Transition Chooser.

Для каждой границы между сегментами рилса выбирает тип transition:
- hard_cut (default) — резкий срез, 0 мс
- j_cut — аудио следующего начинается за 0.25-0.35 сек до смены видео
- l_cut — аудио предыдущего продолжается 0.20-0.30 сек после смены видео
- dissolve — cross-fade 0.4 сек (смена времени/места)
- dip_to_black — fade через чёрный 0.5 сек (конец секции)
- match_cut — визуальное продолжение (используем T2.6 aHash similarity)

Эвристики (research editing-craft-2026.md §B таблица):
- Смена speaker → J-cut 0.25-0.35 сек (28% случаев из MovieCuts dataset)
- Конец `?` риторический → L-cut 0.20-0.30 сек
- Смена темы (semantic distance > 0.5) → J-cut 0.30-0.45 сек
- Эмоциональный пик (energy peak) → L-cut 0.25-0.40 сек (19% случаев)
- Конец `.` → hard cut 0.05-0.10 сек
- Near-identical aHash (<8 bits hamming) → match_cut
- Разная location (low aHash similarity + сильный visual shift) → dissolve
- Конец рилса (последний сегмент) → dip_to_black 0.4 сек

Выбор регулируется через PacingProfileTemplate weights (T10.5) — каждый
profile даёт базовые relative weights, эвристики модифицируют их.

Интерфейс:
    from videomaker.services.transition_chooser import choose_transitions
    transitions = choose_transitions(
        segment_boundaries=[...],
        template=PACING_PROFILES["balanced"],
    )
    # → list[TransitionSpec]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from videomaker.core.logging import get_logger
from videomaker.services.pacing_profile import PacingProfileTemplate

log = get_logger(__name__)


TransitionType = Literal[
    "hard_cut",
    "j_cut",
    "l_cut",
    "dissolve",
    "dip_to_black",
    "match_cut",
]


@dataclass(slots=True, frozen=True)
class SegmentBoundary:
    """Метаданные для принятия решения о типе transition на границе."""

    segment_index: int
    """0-based index сегмента в рилсе (boundary between segment_index and segment_index+1)."""

    is_last: bool
    """True если это переход к финальному сегменту рилса."""

    speaker_change: bool
    """Сменился ли speaker (diarization) через эту границу."""

    topic_change_score: float
    """0..1 сила тематического shift (semantic distance)."""

    energy_peak: bool
    """True если конец предыдущего сегмента — эмоциональный пик."""

    ends_with_question: bool
    """True если текст предыдущего segment кончается на `?`."""

    ends_with_period: bool
    """True если текст предыдущего segment кончается на `.`."""

    ahash_hamming: int | None
    """Hamming distance aHash между последним кадром A и первым кадром B.
    None если недоступно. Близкие кадры (<8 bits) → match_cut кандидат."""


@dataclass(slots=True, frozen=True)
class TransitionSpec:
    """Выбранный transition для boundary."""

    boundary_index: int
    type: TransitionType
    duration_sec: float
    reasoning: str


#: Длительности по типу (research editing-craft-2026.md):
_TYPE_DURATIONS = {
    "hard_cut": 0.0,
    "j_cut": 0.30,
    "l_cut": 0.25,
    "dissolve": 0.40,
    "dip_to_black": 0.50,
    "match_cut": 0.0,
}


def choose_transitions(
    boundaries: list[SegmentBoundary],
    template: PacingProfileTemplate,
) -> list[TransitionSpec]:
    """Возвращает transition для каждого boundary.

    Алгоритм:
    1. Для каждого boundary применяем эвристики → candidate type.
    2. Если эвристика не сработала — sampled из template weights.
    3. Для последнего boundary — всегда dip_to_black (или hard_cut если
       profile не поддерживает dissolve).
    """
    specs: list[TransitionSpec] = []

    for i, b in enumerate(boundaries):
        spec = _choose_for_boundary(b, template)
        specs.append(
            TransitionSpec(
                boundary_index=i,
                type=spec[0],
                duration_sec=_TYPE_DURATIONS[spec[0]],
                reasoning=spec[1],
            )
        )

    log.info(
        "transitions_chosen",
        count=len(specs),
        distribution={t: sum(1 for s in specs if s.type == t) for t in {s.type for s in specs}},
        template=template.name,
    )
    return specs


def _choose_for_boundary(
    b: SegmentBoundary, template: PacingProfileTemplate
) -> tuple[TransitionType, str]:
    # Rule 1: конец рилса
    if b.is_last:
        if template.transition_dissolve > 0:
            return ("dip_to_black", "конец рилса → dip_to_black")
        return ("hard_cut", "конец рилса, dissolve отключён в profile")

    # Rule 2: match_cut по aHash
    if b.ahash_hamming is not None and b.ahash_hamming <= 8:
        return (
            "match_cut",
            f"aHash hamming={b.ahash_hamming} → визуальный match_cut",
        )

    # Rule 3: сильный topic shift
    if b.topic_change_score > 0.6:
        if template.transition_dissolve > 0.05:
            return (
                "dissolve",
                f"topic shift {b.topic_change_score:.2f} → dissolve",
            )
        return ("j_cut", f"topic shift {b.topic_change_score:.2f} → J-cut")

    # Rule 4: смена speaker → J-cut
    if b.speaker_change:
        return ("j_cut", "смена speaker → J-cut 0.30с")

    # Rule 5: риторический вопрос
    if b.ends_with_question:
        return ("l_cut", "риторический вопрос → L-cut 0.25с")

    # Rule 6: эмоциональный пик
    if b.energy_peak:
        return ("l_cut", "emotional peak → L-cut 0.25с")

    # Rule 7: конец предложения → hard cut
    if b.ends_with_period:
        return ("hard_cut", "конец предложения → hard cut")

    # Fallback: template weights
    return _sample_by_weights(template)


def _sample_by_weights(
    template: PacingProfileTemplate,
) -> tuple[TransitionType, str]:
    """Детерминированный fallback — берём transition с max weight."""
    options: list[tuple[TransitionType, float]] = [
        ("hard_cut", template.transition_hard_cut),
        ("j_cut", template.transition_j_cut),
        ("l_cut", template.transition_l_cut),
        ("dissolve", template.transition_dissolve),
    ]
    options.sort(key=lambda x: x[1], reverse=True)
    winner = options[0][0]
    return (winner, f"fallback по template.{template.name} weights")


__all__ = [
    "SegmentBoundary",
    "TransitionSpec",
    "TransitionType",
    "choose_transitions",
]
