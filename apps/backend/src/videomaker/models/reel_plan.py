"""Pydantic модели финального плана рилсов.

Жили в `services/analyzers/base.py` в legacy 3-pass архитектуре. После
перехода на Kartoziya-пайплайн (9 stages) перенесены сюда как нейтральные
модели — их читают `services/reels_composer.py` (producer) и
`services/renderer.py` / `services/pipeline.py` (consumers).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReelSegment(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_start: float = Field(ge=0.0)
    source_end: float = Field(ge=0.0)
    reasoning: str
    order_role: Literal["hook", "development", "peak", "payoff"] = "development"


class ReelPlan(BaseModel):
    model_config = ConfigDict(extra="allow")

    reel_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    hook: str
    predicted_duration_sec: float = Field(ge=0.0)
    target_audience: str = ""
    segments: list[ReelSegment]

    cover_timestamp_sec: float | None = None
    """Timestamp (в секундах source-видео) лучшего thumbnail кадра,
    выбранного vision cover_selector. None если vision disabled."""

    cover_path: str | None = None
    """Путь до сохранённого JPEG обложки относительно artifacts root.
    None если vision disabled или cover не выбран."""

    cover_score: float | None = None
    """Score лучшего кадра в [0, 1] от cover_selector. None если не считался."""

    # FEAT-#C: scoring meta для умной визуализации virality score в UI.
    # Заполняется pipeline'ом после rhythm_check + visual_validator + closure.
    rhythm_score: float | None = Field(default=None, ge=0.0, le=1.0)
    """Overall rhythm score рилса (0..1). Берётся из RhythmReport; если не
    считался (короткий рилс, rhythm_check skipped) → None."""

    visual_score: float | None = Field(default=None, ge=0.0, le=1.0)
    """Среднее visual_score по сегментам рилса (0..1). None при vision disabled."""

    narrative_score: float | None = Field(default=None, ge=0.0, le=1.0)
    """Narrative completeness: 1 если closure_complete + bookend, иначе пропорционально."""

    composite_score: float | None = Field(default=None, ge=0.0, le=100.0)
    """Final 0-100 composite score, displayed в UI как virality score."""

    cross_context_risk: float | None = Field(default=None, ge=0.0, le=1.0)
    """T9 — Cross-Context Risk score (0..1). Рилс собран из сегментов
    с большим temporal gap'ом и/или разной тематикой. >0.6 — frontend
    показывает warning badge «Cross-context — проверь перед публикацией».
    None для single-segment рилсов и когда composer cross-context penalty
    disabled."""


class AnalysisResult(BaseModel):
    """Итог analyze-стадии, готовый к передаче в renderer.

    - `reels` — финальный список ReelPlan'ов (после reels_composer дедупа/N-фильтра).
    - `llm_model`/`provider` — справочная инфа какой тяжёлой моделью шёл Canvas+Doctor.
    - `stats` — свободный dict с метриками пайплайна (target_count, uniqueness,
      candidates_total, bookend_motif_id и т.п.). Видно в analysis_summary.json
      и в UI job detail.
    """

    reels: list[ReelPlan]
    llm_model: str
    provider: str
    stats: dict[str, int | float | str | None] = Field(default_factory=dict)
