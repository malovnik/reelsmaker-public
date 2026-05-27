"""B-roll insertion engine — предлагает overlay на development segments.

Для каждого segment с role='development' в StoryScript находит до N B-roll
кандидатов через VisualEvidenceIndex. Возвращает BRollSuggestion — это
предложение (не применение): реальная вставка в рендер — задача пайплайна
с конкретной стратегией overlay (picture-in-picture / split-screen / cutaway).

Фильтры:
* Только development segments (не hook/peak/payoff — те структурно важны)
* exclude_timestamps — все source_start_sec уже в arc, чтобы B-roll не пересекался
* min_score=0.3 — отсекаем случайные совпадения по каждому токену
"""

from __future__ import annotations

from dataclasses import dataclass

from videomaker.models.story_script import StoryScript
from videomaker.services.broll.index import VisualEvidenceIndex
from videomaker.services.broll.retriever import (
    BRollCandidate,
    find_broll_for_segment,
)


@dataclass(slots=True, frozen=True)
class BRollSuggestion:
    """Предложение B-roll вставки на конкретный segment арки."""

    segment_index: int
    segment_role: str
    segment_text_preview: str
    candidates: list[BRollCandidate]

    @property
    def has_any(self) -> bool:
        return len(self.candidates) > 0


def suggest_broll_inserts(
    story_script: StoryScript,
    index: VisualEvidenceIndex,
    *,
    per_segment_limit: int = 2,
    min_score: float = 0.3,
) -> list[BRollSuggestion]:
    """Пройти arc, для каждого development segment вернуть B-roll suggestions.

    Noop при пустом индексе или пустом arc.
    """
    if index.is_empty or not story_script.arc:
        return []

    exclude = tuple(seg.source_start_sec for seg in story_script.arc)

    suggestions: list[BRollSuggestion] = []
    for idx, segment in enumerate(story_script.arc):
        if segment.role != "development":
            continue
        if not segment.text_preview:
            continue
        candidates = find_broll_for_segment(
            segment.text_preview,
            index,
            limit=per_segment_limit,
            exclude_timestamps=exclude,
            min_score=min_score,
        )
        if not candidates:
            continue
        suggestions.append(
            BRollSuggestion(
                segment_index=idx,
                segment_role=segment.role,
                segment_text_preview=segment.text_preview[:120],
                candidates=candidates,
            )
        )
    return suggestions
