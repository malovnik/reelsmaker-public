"""Pydantic модели для Vision Layer результатов.

Все результаты включают `latency_ms` для observability — видим где GGUF тормозит
(обычно первый inference ~1.5s на прогрев, далее 200-700ms на caption).

Нормализация bbox: все координаты в **[0, 1]** относительно кадра, формат XYWH
(x — левый, y — верх, w — ширина, h — высота). Это совместимо с `face_tracker.FaceBBox`
и позволяет zoom_planner переиспользовать существующий интерполятор.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VisionQueryResult(BaseModel):
    """Результат yes/no VQA-запроса."""

    model_config = ConfigDict(frozen=True)

    answer: Literal["yes", "no", "unknown"]
    raw_response: str = Field(default="", description="Сырой ответ модели до парсинга")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    latency_ms: float = Field(default=0.0, ge=0.0)


class VisionCaptionResult(BaseModel):
    """Результат captioning (описание кадра)."""

    model_config = ConfigDict(frozen=True)

    caption: str
    length: Literal["short", "normal", "long"] = "short"
    latency_ms: float = Field(default=0.0, ge=0.0)


class VisionDetection(BaseModel):
    """Единичная детекция объекта в кадре (normalized bbox)."""

    model_config = ConfigDict(frozen=True)

    label: str
    bbox_xywh_norm: tuple[float, float, float, float] = Field(
        description="(x, y, w, h) в диапазоне [0, 1] относительно кадра"
    )
    confidence: float = Field(ge=0.0, le=1.0)

    @property
    def center_norm(self) -> tuple[float, float]:
        x, y, w, h = self.bbox_xywh_norm
        return (x + w / 2.0, y + h / 2.0)


class VisionDetectResult(BaseModel):
    """Результат detect-запроса: список детекций + latency."""

    model_config = ConfigDict(frozen=True)

    detections: list[VisionDetection] = Field(default_factory=list)
    latency_ms: float = Field(default=0.0, ge=0.0)

    @property
    def has_any(self) -> bool:
        return len(self.detections) > 0


class VisionHealthStatus(BaseModel):
    """Health check результат — для /settings/vision API и warmup-логов."""

    model_config = ConfigDict(frozen=True)

    available: bool
    model_loaded: bool
    backend: Literal["metal", "cpu", "unavailable"]
    latency_ms: float = Field(default=0.0, ge=0.0)
    model_path: str | None = None
    error: str | None = None
