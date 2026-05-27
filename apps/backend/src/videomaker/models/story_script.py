"""Pydantic модели story-script (Stage 5.5-5.6 outputs) и Variants (Stage 5.8).

- `StoryScript` — 3-act arc с book-end symmetry (Story Doctor).
- `RhythmReport` — middle-sag detection + recommendations (Rhythm Check).
- `StoryVariants` — 4 формата нарезки (long_philosophical / package_of_shorts /
  punchy_summary / deep_dive) для Variants Generator.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SegmentRole = Literal["hook", "setup", "development", "peak", "payoff"]
EmotionalBeat = Literal["strain", "relief", "reveal", "triumph", "neutral"]

VisualFlag = Literal[
    "face_off_screen",
    "poor_framing",
    "low_energy",
    "occluded",
    "off_center",
    "visual_ok",
]


class StorySegment(BaseModel):
    role: SegmentRole
    evidence_id: str
    source_start_sec: float = Field(ge=0.0)
    source_end_sec: float = Field(ge=0.0)
    speaker: str | None = None
    reasoning: str = ""
    emotional_beat: EmotionalBeat = "neutral"
    text_preview: str = ""
    payoff_conclusion: str | None = None
    """Для role=payoff: фраза, фактически закрывающая open loop HOOK'а.
    Story Doctor обязан заполнять для payoff-сегментов; None для остальных
    ролей. Используется для OpusClip-style semantic closure validation."""

    visual_score: float = Field(default=1.0, ge=0.0, le=1.0)
    """Средневзвешенный vision-score сегмента в [0, 1]. 1.0 = idle default
    (vision disabled ИЛИ не оценивалось). < 0.4 считается проблемным и
    уменьшает composite score при ранжировании в reels_composer."""

    visual_flags: list[VisualFlag] = Field(default_factory=list)
    """Флаги проблем визуала (пустой список при disabled / idle). Story Doctor
    использует для re-rank; UI показывает в отладочной информации."""

    face_centering_score: float = Field(default=1.0, ge=0.0, le=1.0)
    """Геометрический face centering score [0, 1] — детерминированная
    метрика расстояния лица до центра кадра. 1.0 = idle default (vision
    disabled или не вычислялось). Заполняется Stage 5.5.5 visual_validator
    для talking_head профиля через composition_scorer. Story Doctor
    применяет penalty когда < 0.60 (см. composition_scorer.is_off_center)."""

    visual_reasoning: str = ""
    """Human-readable обоснование vision-оценки (опциональное). Заполняется
    visual_validator; при disabled остаётся пустым."""

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.source_end_sec - self.source_start_sec)


class AlternateSegment(BaseModel):
    role_substitute: SegmentRole
    evidence_id: str
    reason: str = ""


class StoryScript(BaseModel):
    """Финальный story-script с 3-act arc + alternates."""

    central_theme: str
    bookend_motif_id: str | None = None
    bookend_reasoning: str = ""
    visual_bookend_motif: str | None = None
    """Короткий визуальный дескриптор (main_object / person_position / caption keyword),
    общий между HOOK и PAYOFF сегментами. None если visual_evidence недоступно или
    общего якоря не найдено. Заполняется story_doctor.md при наличии visual_tags
    в RankedEvidence (Phase 3 multimodal dramaturgy)."""

    arc: list[StorySegment] = Field(default_factory=list)
    alternates: list[AlternateSegment] = Field(default_factory=list)
    predicted_duration_sec: float = 0.0

    def segments_by_role(self, role: SegmentRole) -> list[StorySegment]:
        return [s for s in self.arc if s.role == role]


class RhythmIssue(BaseModel):
    region: str
    severity: Literal["low", "medium", "high"]
    reason: str
    recommendation_action: Literal[
        "insert_cutaway", "swap_segment", "shorten", "none",
    ] = "none"
    target_position_in_arc: int | None = None
    alternate_evidence_id: str | None = None
    recommendation_reasoning: str = ""


class RhythmReport(BaseModel):
    middle_sag_detected: bool = False
    issues: list[RhythmIssue] = Field(default_factory=list)
    overall_rhythm_score: float = Field(default=1.0, ge=0.0, le=1.0)
    pacing_summary: Literal["рваный", "ровный", "монотонный"] = "ровный"


VariantKind = Literal[
    "long_philosophical",
    "package_of_shorts",
    "punchy_summary",
    "deep_dive",
]


class StoryVariant(BaseModel):
    id: str
    kind: VariantKind
    label: str
    target_duration_sec: float = Field(ge=0.0)
    predicted_duration_sec: float = Field(ge=0.0)
    central_theme: str
    arc: list[StorySegment] = Field(default_factory=list)


class StoryVariants(BaseModel):
    variants: list[StoryVariant] = Field(default_factory=list)

    def by_kind(self, kind: VariantKind) -> StoryVariant | None:
        for v in self.variants:
            if v.kind == kind:
                return v
        return None
