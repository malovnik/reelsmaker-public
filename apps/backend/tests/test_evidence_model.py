"""Unit-тесты Evidence pydantic-моделей (Stage 5.3-5.4 types)."""

from __future__ import annotations

from videomaker.models.evidence import (
    EvidenceItem,
    RankedEvidence,
    RankedEvidenceItem,
)


def _evidence(
    *, agent: str = "hook_hunter", start: float = 10.0, end: float = 25.0,
    strength: float = 0.7, extra: dict | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        source_agent=agent,  # type: ignore[arg-type]
        chunk_index=0,
        start=start,
        end=end,
        text="Хук про парадокс",
        strength=strength,
        extra=extra or {},
    )


def test_duration_sec_positive() -> None:
    assert _evidence(start=10, end=25).duration_sec == 15.0


def test_duration_sec_never_negative() -> None:
    item = EvidenceItem(
        source_agent="hook_hunter", chunk_index=0,
        start=20.0, end=20.0, text="x",
    )
    assert item.duration_sec == 0.0


def test_agent_specific_type_reads_hook_type() -> None:
    item = _evidence(extra={"hook_type": "paradox"})
    assert item.agent_specific_type == "paradox"


def test_agent_specific_type_reads_emotion() -> None:
    item = _evidence(agent="emotional_peak_finder", extra={"emotion": "joy"})
    assert item.agent_specific_type == "joy"


def test_agent_specific_type_none_when_no_match() -> None:
    item = _evidence(extra={"unrelated": "value"})
    assert item.agent_specific_type is None


def test_strength_clamped_by_field_constraint() -> None:
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        EvidenceItem(
            source_agent="hook_hunter", chunk_index=0, start=0.0, end=1.0,
            text="x", strength=1.5,
        )


def _ranked(
    *, id_: str = "r0", category: str = "hook_candidate",
    score: float = 0.8,
) -> RankedEvidenceItem:
    return RankedEvidenceItem(
        id=id_,
        source_agent="hook_hunter",
        start=0.0,
        end=5.0,
        text="sample",
        category=category,  # type: ignore[arg-type]
        composite_score=score,
    )


def test_ranked_evidence_by_category_filters() -> None:
    ranked = RankedEvidence(
        items=[
            _ranked(id_="r0", category="hook_candidate", score=0.9),
            _ranked(id_="r1", category="peak_candidate", score=0.85),
            _ranked(id_="r2", category="hook_candidate", score=0.7),
        ]
    )
    hooks = ranked.by_category("hook_candidate")
    assert [r.id for r in hooks] == ["r0", "r2"]


def test_ranked_evidence_defaults() -> None:
    re = RankedEvidence()
    assert re.items == []
    assert re.deduped_count == 0
    assert re.merged_scene_count == 0
