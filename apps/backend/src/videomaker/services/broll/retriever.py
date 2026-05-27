"""B-roll retriever — finds VisualEvidenceItem кандидатов для segment text.

API:
    candidates = find_broll_for_segment(
        segment_text="он рассказывает про путешествия в Японию",
        index=visual_evidence_index,
        limit=3,
        exclude_timestamps=(45.0, 90.0),  # timestamps которые уже в arc
    )

Каждый кандидат — BRollCandidate с timestamp, caption, score, reason.
Фильтруем кандидатов по минимальному score (default 0.3) — без этого B-roll
становится шумом для коротких captions.
"""

from __future__ import annotations

from dataclasses import dataclass

from videomaker.services.broll.index import VisualEvidenceIndex, tokenize


@dataclass(slots=True, frozen=True)
class BRollCandidate:
    timestamp_sec: float
    caption: str
    score: float
    reason: str


def find_broll_for_segment(
    segment_text: str,
    index: VisualEvidenceIndex,
    *,
    limit: int = 3,
    exclude_timestamps: tuple[float, ...] = (),
    exclude_tolerance_sec: float = 3.0,
    min_score: float = 0.3,
) -> list[BRollCandidate]:
    """Возвращает top-K B-roll кандидатов для сегмента.

    exclude_timestamps — список timestamps уже используемых в arc (чтобы
    B-roll не дублировал основной материал). Tolerance задаёт окно исключения.
    """
    if index.is_empty or not segment_text.strip():
        return []
    query_tokens = tokenize(segment_text)
    if not query_tokens:
        return []

    raw = index.search(query_tokens, limit=limit * 3)  # с запасом для фильтрации
    candidates: list[BRollCandidate] = []
    for idx, score in raw:
        if score < min_score:
            continue
        item = index.items[idx]
        if _is_excluded(item.timestamp_sec, exclude_timestamps, exclude_tolerance_sec):
            continue
        matched = [t for t in query_tokens if t in item.caption.lower() or t == (item.main_object or "")]
        reason = (
            f"matched tokens: {', '.join(matched[:3]) or 'weak'}; "
            f"caption: {item.caption[:80]}"
        )
        candidates.append(
            BRollCandidate(
                timestamp_sec=item.timestamp_sec,
                caption=item.caption,
                score=score,
                reason=reason,
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def _is_excluded(
    timestamp_sec: float,
    exclude_timestamps: tuple[float, ...],
    tolerance_sec: float,
) -> bool:
    return any(
        abs(timestamp_sec - ex) <= tolerance_sec
        for ex in exclude_timestamps
    )
