"""Visual Evidence Agent — 7-й параллельный агент Stage 5.

В отличие от 6 text-агентов (hook_hunter, emotional_peak_finder и т.д.),
этот агент работает с видео напрямую через Moondream 2 (не с транскриптом).
Семплирует кадры каждые `frame_sample_rate_sec` и для каждого собирает:

* caption (short) — «what's in the frame»
* people detection — есть ли человек и где он расположен (center/left/right)
* main object detection — главный не-человеческий объект (если есть)

Результат — `VisualEvidenceResult` с timeline of `VisualEvidenceItem`.
Используется в Phase 3 для:
1. Multimodal dramatic_irony_scanner — находит дисонанс слова vs визуал.
2. Book-end visual symmetry в story_doctor.md.
3. B-roll retrieval в Phase 6.

Параллелизм: frames sampled через asyncio.gather + VisionRateLimiter. При
ошибке на одном кадре — этот timestamp просто пропускается, остальной timeline
продолжает строиться (error isolation как в visual_validator).

Fallback: если `client is None` → пустой timeline. Не ломает пайплайн.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from videomaker.core.logging import get_logger
from videomaker.services.vision import (
    FrameExtractor,
    VisionClient,
    VisionRateLimiter,
    VisionResultCache,
)

log = get_logger(__name__)


class VisualEvidenceItem(BaseModel):
    """Одно визуальное наблюдение — кадр на конкретном timestamp."""

    model_config = ConfigDict(frozen=True)

    timestamp_sec: float = Field(ge=0.0)
    caption: str = ""
    has_person: bool = False
    person_position: str | None = None
    """top-left..bottom-right из 9-region эвристики или None если нет человека."""

    main_object: str | None = None
    """Главный не-человеческий объект (текст из caption или detect), если есть."""

    latency_ms: float = Field(default=0.0, ge=0.0)


@dataclass(slots=True)
class VisualEvidenceResult:
    """Timeline визуальных наблюдений + агрегаты."""

    items: list[VisualEvidenceItem] = field(default_factory=list)
    sample_rate_sec: float = 0.0
    total_frames_requested: int = 0
    failed_frames: int = 0

    @property
    def success_rate(self) -> float:
        if self.total_frames_requested == 0:
            return 1.0
        return 1.0 - self.failed_frames / self.total_frames_requested

    def at(self, timestamp_sec: float, tolerance: float = 2.0) -> VisualEvidenceItem | None:
        """Ищет ближайший item к timestamp в пределах tolerance секунд."""
        best: VisualEvidenceItem | None = None
        best_delta = tolerance
        for item in self.items:
            delta = abs(item.timestamp_sec - timestamp_sec)
            if delta <= best_delta:
                best = item
                best_delta = delta
        return best


async def run_visual_evidence_agent(
    video_path: Path,
    source_duration_sec: float,
    video_hash: str,
    *,
    client: VisionClient | None,
    extractor: FrameExtractor,
    cache: VisionResultCache,
    limiter: VisionRateLimiter,
    sample_rate_sec: float,
) -> VisualEvidenceResult:
    """Семплирует кадры через равные интервалы, собирает VisualEvidenceItem.

    Noop при client=None. При ошибке на кадре — пропускается, timeline
    продолжает строиться.
    """
    if client is None or source_duration_sec <= 0 or sample_rate_sec <= 0:
        return VisualEvidenceResult()

    timestamps = _sample_timestamps(source_duration_sec, sample_rate_sec)
    if not timestamps:
        return VisualEvidenceResult(sample_rate_sec=sample_rate_sec)

    async def _process(ts: float) -> VisualEvidenceItem | None:
        try:
            return await _observe_frame(
                ts,
                video_path=video_path,
                video_hash=video_hash,
                client=client,
                extractor=extractor,
                cache=cache,
                limiter=limiter,
            )
        except Exception as exc:
            log.warning("visual_evidence_frame_failed", ts=ts, error=str(exc))
            return None

    observations = await asyncio.gather(*(_process(ts) for ts in timestamps))
    items = [o for o in observations if o is not None]
    failed = len(timestamps) - len(items)
    log.info(
        "visual_evidence_done",
        sampled=len(timestamps),
        success=len(items),
        failed=failed,
        sample_rate_sec=sample_rate_sec,
    )
    return VisualEvidenceResult(
        items=items,
        sample_rate_sec=sample_rate_sec,
        total_frames_requested=len(timestamps),
        failed_frames=failed,
    )


def _sample_timestamps(duration_sec: float, step_sec: float) -> list[float]:
    """Ровные timestamps от step/2 до duration с интервалом step."""
    if duration_sec <= 0 or step_sec <= 0:
        return []
    timestamps: list[float] = []
    t = step_sec / 2.0
    while t < duration_sec:
        timestamps.append(round(t, 3))
        t += step_sec
    return timestamps


async def _observe_frame(
    timestamp_sec: float,
    *,
    video_path: Path,
    video_hash: str,
    client: VisionClient,
    extractor: FrameExtractor,
    cache: VisionResultCache,
    limiter: VisionRateLimiter,
) -> VisualEvidenceItem:
    """Процесс одного кадра: caption + person detect → VisualEvidenceItem."""
    cached_frame = await extractor.extract(video_path, video_hash, timestamp_sec)

    async with limiter.acquire():
        caption_params = {"op": "caption", "length": "short"}
        cached_cap = await cache.get(
            video_hash, op="caption", timestamp_sec=timestamp_sec, params=caption_params
        )
        if cached_cap is not None:
            caption_text = str(cached_cap.get("caption", "")).strip()
            caption_latency = float(cached_cap.get("latency_ms", 0.0))
        else:
            caption_result = await client.caption(cached_frame.frame_path, length="short")
            caption_text = caption_result.caption
            caption_latency = caption_result.latency_ms
            await cache.put(
                video_hash,
                op="caption",
                timestamp_sec=timestamp_sec,
                params=caption_params,
                value=caption_result.model_dump(),
            )

        detect_params = {"op": "detect", "label": "person"}
        cached_det = await cache.get(
            video_hash, op="detect", timestamp_sec=timestamp_sec, params=detect_params
        )
        if cached_det is not None:
            has_person = len(cached_det.get("detections") or []) > 0
            person_position = _detection_to_position(cached_det)
            detect_latency = float(cached_det.get("latency_ms", 0.0))
        else:
            detect_result = await client.detect(cached_frame.frame_path, "person")
            has_person = detect_result.has_any
            person_position = (
                _bbox_to_region(detect_result.detections[0].bbox_xywh_norm)
                if detect_result.detections
                else None
            )
            detect_latency = detect_result.latency_ms
            await cache.put(
                video_hash,
                op="detect",
                timestamp_sec=timestamp_sec,
                params=detect_params,
                value=detect_result.model_dump(),
            )

    main_object = _extract_main_object(caption_text, has_person)
    return VisualEvidenceItem(
        timestamp_sec=timestamp_sec,
        caption=caption_text,
        has_person=has_person,
        person_position=person_position,
        main_object=main_object,
        latency_ms=caption_latency + detect_latency,
    )


def _detection_to_position(cached: dict[str, object]) -> str | None:
    """Извлекает position из cached detection dict (для кэш-совместимости)."""
    detections = cached.get("detections")
    if not isinstance(detections, list) or not detections:
        return None
    first = detections[0]
    if not isinstance(first, dict):
        return None
    bbox = first.get("bbox_xywh_norm")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    try:
        return _bbox_to_region(tuple(float(v) for v in bbox))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _bbox_to_region(bbox: tuple[float, float, float, float]) -> str:
    """Конвертирует normalized XYWH bbox → regional label."""
    x, y, w, h = bbox
    cx = x + w / 2.0
    cy = y + h / 2.0
    col = "left" if cx < 0.33 else "right" if cx > 0.66 else "center"
    row = "top" if cy < 0.33 else "bottom" if cy > 0.66 else "center"
    if col == "center" and row == "center":
        return "center"
    return f"{row}-{col}" if row != "center" else col


def _extract_main_object(caption: str, has_person: bool) -> str | None:
    """Эвристика: первый noun из caption кроме 'person/man/woman/people'."""
    if not caption:
        return None
    lowered = caption.lower()
    person_keywords = ("person", "man", "woman", "people", "boy", "girl")
    if has_person:
        for kw in person_keywords:
            lowered = lowered.replace(kw, "")
    words = [w for w in lowered.split() if w.isalpha() and len(w) > 2]
    stopwords = {
        "the", "with", "and", "that", "this", "there", "which",
        "into", "from", "over", "under", "are", "was", "were", "has", "have",
    }
    meaningful = [w for w in words if w not in stopwords]
    return meaningful[0] if meaningful else None
