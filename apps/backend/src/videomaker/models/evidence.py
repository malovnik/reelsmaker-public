"""Pydantic модели Evidence — output 6 extraction-агентов Stage 5.3.

Каждый агент возвращает свой набор полей (hook_type, emotion, humor_type и т.д.),
но они сливаются в общий EvidenceItem через агент-специфичный `extra` dict.

На Stage 5.4 (Reduce) весь pool дедуплицируется по Jaccard + близости таймштампов
и ранжируется LLM'ом по composite_score. На Stage 5.7 (Reels Composer) ranked pool
превращается в итоговые ReelPlan[] с контролируемой uniqueness.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AgentName = Literal[
    "hook_hunter",
    "emotional_peak_finder",
    "humor_specialist",
    "dramatic_irony_scanner",
    "thesis_extractor",
    "motif_tracker",
]


class EvidenceItem(BaseModel):
    """Unified evidence от любого из 6 агентов extraction.

    Общие поля наверху. Агент-специфичные детали (hook_type, humor_type, emotion,
    irony_type, thesis_type, role) уходят в `extra` dict.
    """

    source_agent: AgentName
    chunk_index: int
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    text: str
    speaker: str | None = None
    theme_id: str | None = None
    motif_id: str | None = None
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    reasoning: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = Field(default=None)
    """Semantic embedding текста (gemini-embedding-001, 256-dim).
    Заполняется в Reducer ПЕРЕД dedup. Используется для hybrid-dedup
    (cosine-sim >= 0.80 катит как дубликат в пределах time-window).
    None при fallback API — dedup откатывается на чистый Jaccard."""

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def agent_specific_type(self) -> str | None:
        """Достаёт ключевой тип из extra (hook_type/humor_type/emotion и т.п.)."""
        for key in (
            "hook_type", "emotion", "humor_type", "irony_type",
            "thesis_type", "role",
        ):
            if key in self.extra:
                return str(self.extra[key])
        return None


EvidenceCategory = Literal[
    "hook_candidate",
    "peak_candidate",
    "payoff_candidate",
    "development_material",
    "cutaway_material",
]


class RankedEvidenceItem(BaseModel):
    """Результат Stage 5.4 Reduce — evidence после dedup + ranking."""

    id: str
    source_agent: AgentName
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    text: str
    speaker: str | None = None
    theme_id: str | None = None
    motif_id: str | None = None
    category: EvidenceCategory
    composite_score: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""

    visual_caption: str = ""
    """Caption ближайшего визуального кадра (если vision_enabled). Используется
    dramatic_irony_scanner для мультимодального детекта иронии (слово ≠ визуал)."""

    visual_tags: list[str] = Field(default_factory=list)
    """Визуальные теги (has_person, person_position, main_object) — opaque для
    downstream stages, но доступны через user_payload промптов Phase 3."""

    embedding: list[float] | None = Field(default=None)
    """Semantic embedding (gemini-embedding-001, 256-dim). Пробрасывается из
    EvidenceItem.embedding в Reducer (Stage 6). Используется Story Doctor
    (Stage 7) для retrieval альтернативных payoff-кандидатов при слабой
    концовке, Reels Composer — для cross-reel diversity filter."""


class RankedEvidence(BaseModel):
    """Итоговый output Stage 5.4 — отранжированный pool для дальнейших стадий."""

    deduped_count: int = 0
    merged_scene_count: int = 0
    items: list[RankedEvidenceItem] = Field(default_factory=list)

    def by_category(self, category: EvidenceCategory) -> list[RankedEvidenceItem]:
        return [e for e in self.items if e.category == category]
