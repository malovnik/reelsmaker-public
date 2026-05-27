"""ObjectTracker — arbitrary-object tracking через Moondream 2 detect.

Параллельно `face_tracker.py` (mediapipe face detection), этот модуль отслеживает
произвольный объект по label через VLM detect. Геометрия bbox нормализована
(XYWH в [0, 1]), формат идентичен `FaceBBox` — zoom_planner может использовать
оба источника anchor-ов через ZoomAnchor dispatch.

Стратегия:
* Sampling — 1 кадр каждые `sample_interval_sec` (default 1.5s как у face_tracker).
* Frame extraction через `FrameExtractor` из vision/frame_cache.py.
* Detect через `VisionClient.detect(frame_path, label)` — возвращает normalized bbox.
* Interpolation между sampled frames — linear weighted average (как в face_tracker).

Caching: результаты per-(video_hash, label, interval) в том же vision_cache директории,
что используется для frame cache + VisionResultCache. Повторный call по тому же
label не дёргает LLM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from videomaker.core.logging import get_logger
from videomaker.services.vision import (
    FrameExtractor,
    VisionClient,
    VisionRateLimiter,
)

log = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class ObjectBBox:
    """Нормализованные координаты произвольного объекта в кадре (0..1).

    Совместим по геометрии с `face_tracker.FaceBBox` — x/y/w/h + confidence.
    Дополнительно несёт `label` (человек / объект / UI элемент) для отладки.
    """

    x: float
    y: float
    w: float
    h: float
    confidence: float
    label: str

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def area(self) -> float:
        return self.w * self.h


@dataclass(slots=True)
class ObjectDetection:
    """Одно sampled-наблюдение — timestamp + найденный bbox (или None)."""

    timestamp_sec: float
    bbox: ObjectBBox | None = None


@dataclass(slots=True)
class ObjectTrack:
    """Timeline детекций одного label по одному видео.

    API `best_bbox_at(t_sec)` повторяет форму `FaceTrackResult.best_face_at()`:
    weighted interpolation между двумя соседними sampled frames, с fallback
    на расширенный поиск ±2 sample, и None если объект вообще не встречался.
    """

    video_hash: str
    label: str
    sample_interval_sec: float
    detections: list[ObjectDetection] = field(default_factory=list)

    def best_bbox_at(self, t_sec: float) -> ObjectBBox | None:
        if not self.detections:
            return None

        left_idx = -1
        right_idx = -1
        for i, det in enumerate(self.detections):
            if det.timestamp_sec <= t_sec:
                left_idx = i
            else:
                right_idx = i
                break

        left = self.detections[left_idx] if left_idx >= 0 else None
        right = self.detections[right_idx] if right_idx >= 0 else None
        left_bbox = left.bbox if left else None
        right_bbox = right.bbox if right else None

        if left_bbox is not None and right_bbox is not None and left and right:
            span = right.timestamp_sec - left.timestamp_sec
            if span <= 0:
                return left_bbox
            w_right = (t_sec - left.timestamp_sec) / span
            w_left = 1.0 - w_right
            return ObjectBBox(
                x=left_bbox.x * w_left + right_bbox.x * w_right,
                y=left_bbox.y * w_left + right_bbox.y * w_right,
                w=left_bbox.w * w_left + right_bbox.w * w_right,
                h=left_bbox.h * w_left + right_bbox.h * w_right,
                confidence=min(left_bbox.confidence, right_bbox.confidence),
                label=self.label,
            )

        if left_bbox is not None:
            return left_bbox
        if right_bbox is not None:
            return right_bbox

        anchor_idx = left_idx if left_idx >= 0 else right_idx
        if anchor_idx < 0:
            return None
        for offset in range(1, 3):
            for direction in (-1, 1):
                idx = anchor_idx + direction * offset
                if 0 <= idx < len(self.detections):
                    candidate = self.detections[idx].bbox
                    if candidate is not None:
                        return candidate
        return None

    @property
    def present_ratio(self) -> float:
        """Доля detection, где объект был найден (0.0-1.0)."""
        if not self.detections:
            return 0.0
        present = sum(1 for d in self.detections if d.bbox is not None)
        return present / len(self.detections)


async def track_object(
    video_path: Path,
    video_hash: str,
    source_duration_sec: float,
    label: str,
    *,
    client: VisionClient | None,
    extractor: FrameExtractor,
    limiter: VisionRateLimiter,
    cache_dir: Path,
    sample_interval_sec: float = 1.5,
) -> ObjectTrack:
    """Семплирует кадры с шагом interval, запускает detect по label, собирает track.

    Noop при client=None (возвращает ObjectTrack с пустыми detections).
    Cache — JSON в `cache_dir/<video_hash>/tracks/<label>__<interval>s.json`.
    Повторный вызов для того же (label, interval) читает из кэша.
    """
    if client is None or source_duration_sec <= 0 or sample_interval_sec <= 0:
        return ObjectTrack(
            video_hash=video_hash,
            label=label,
            sample_interval_sec=sample_interval_sec,
        )

    cache_path = (
        cache_dir / video_hash / "tracks" /
        f"{_safe_label(label)}__{sample_interval_sec:.2f}s.json"
    )
    if cache_path.exists() and cache_path.stat().st_size > 0:
        cached = _load_from_cache(cache_path, label)
        if cached is not None:
            log.debug("object_track_cache_hit", label=label, detections=len(cached.detections))
            return cached

    timestamps: list[float] = []
    t = sample_interval_sec / 2.0
    while t < source_duration_sec:
        timestamps.append(round(t, 3))
        t += sample_interval_sec

    detections: list[ObjectDetection] = []
    for ts in timestamps:
        try:
            frame = await extractor.extract(video_path, video_hash, ts)
            async with limiter.acquire():
                result = await client.detect(frame.frame_path, label)
        except Exception as exc:
            log.warning("object_track_frame_failed", label=label, ts=ts, error=str(exc))
            detections.append(ObjectDetection(timestamp_sec=ts, bbox=None))
            continue
        if result.detections:
            det = result.detections[0]
            bbox = ObjectBBox(
                x=det.bbox_xywh_norm[0],
                y=det.bbox_xywh_norm[1],
                w=det.bbox_xywh_norm[2],
                h=det.bbox_xywh_norm[3],
                confidence=det.confidence,
                label=label,
            )
            detections.append(ObjectDetection(timestamp_sec=ts, bbox=bbox))
        else:
            detections.append(ObjectDetection(timestamp_sec=ts, bbox=None))

    track = ObjectTrack(
        video_hash=video_hash,
        label=label,
        sample_interval_sec=sample_interval_sec,
        detections=detections,
    )
    _save_to_cache(track, cache_path)
    log.info(
        "object_track_done",
        label=label,
        sampled=len(timestamps),
        present_ratio=round(track.present_ratio, 3),
    )
    return track


def _safe_label(label: str) -> str:
    """Нормализация label для filename: lower + underscores вместо пробелов."""
    safe = "".join(c if c.isalnum() else "_" for c in label.lower())
    return safe[:48] or "object"


def _save_to_cache(track: ObjectTrack, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "video_hash": track.video_hash,
        "label": track.label,
        "sample_interval_sec": track.sample_interval_sec,
        "detections": [
            {
                "timestamp_sec": d.timestamp_sec,
                "bbox": (
                    {
                        "x": d.bbox.x, "y": d.bbox.y,
                        "w": d.bbox.w, "h": d.bbox.h,
                        "confidence": d.bbox.confidence,
                    }
                    if d.bbox else None
                ),
            }
            for d in track.detections
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _load_from_cache(path: Path, label: str) -> ObjectTrack | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    detections: list[ObjectDetection] = []
    for raw in data.get("detections") or []:
        if not isinstance(raw, dict):
            continue
        ts = float(raw.get("timestamp_sec", 0.0))
        bbox_raw = raw.get("bbox")
        bbox: ObjectBBox | None = None
        if isinstance(bbox_raw, dict):
            try:
                bbox = ObjectBBox(
                    x=float(bbox_raw["x"]),
                    y=float(bbox_raw["y"]),
                    w=float(bbox_raw["w"]),
                    h=float(bbox_raw["h"]),
                    confidence=float(bbox_raw["confidence"]),
                    label=label,
                )
            except (KeyError, TypeError, ValueError):
                bbox = None
        detections.append(ObjectDetection(timestamp_sec=ts, bbox=bbox))
    return ObjectTrack(
        video_hash=str(data.get("video_hash", "")),
        label=label,
        sample_interval_sec=float(data.get("sample_interval_sec", 1.5)),
        detections=detections,
    )
