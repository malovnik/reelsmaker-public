"""Cover selector — выбор лучшего thumbnail кадра для рилса.

После рендеринга каждого рилса (или из source-видео по start timestamp рилса)
семплим 6 кадров в первых 3 секундах с шагом 0.5s, для каждого считаем
vision_score по 3 yes/no VQA:

* face_visible (weight 0.5)
* well_framed  (weight 0.3)
* engaging     (weight 0.2)

Возвращаем top-1 timestamp + извлечённый JPEG в `data/covers/<reel_id>.jpg`.

Fallback: client=None → CoverResult с timestamp=0.5, score=0.0 и None path
(пусть рендер-пайплайн берёт первый кадр как раньше).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from videomaker.core.logging import get_logger
from videomaker.services.vision import (
    FrameExtractor,
    VisionClient,
    VisionRateLimiter,
)

log = get_logger(__name__)


_COVER_QUESTIONS: dict[str, tuple[str, float]] = {
    "face_visible": (
        "Is a person's face clearly visible and recognizable in this image?",
        0.5,
    ),
    "well_framed": (
        "Is the main subject well-framed and centered in this image?",
        0.3,
    ),
    "engaging": (
        "Does this image look engaging, with a confident or expressive pose?",
        0.2,
    ),
}


@dataclass(slots=True, frozen=True)
class CoverCandidate:
    """Одно sampled-наблюдение кадра для cover selection."""

    timestamp_sec: float
    score: float
    frame_path: Path
    answers: dict[str, str]


@dataclass(slots=True, frozen=True)
class CoverResult:
    """Итоговый выбор cover frame."""

    reel_id: str
    timestamp_sec: float
    score: float
    frame_path: Path | None
    reason: str

    @property
    def is_selected(self) -> bool:
        return self.frame_path is not None and self.score > 0.0


async def select_cover(
    reel_id: str,
    source_video_path: Path,
    video_hash: str,
    reel_start_sec: float,
    *,
    client: VisionClient | None,
    extractor: FrameExtractor,
    limiter: VisionRateLimiter,
    sample_step_sec: float = 0.5,
    sample_window_sec: float = 3.0,
) -> CoverResult:
    """Выбирает лучший кадр из первых N секунд для cover/thumbnail.

    При client=None → CoverResult с frame_path=None (fallback на first frame).
    Ошибка на одном кадре → пропуск, выбор из оставшихся.
    """
    if client is None:
        return CoverResult(
            reel_id=reel_id,
            timestamp_sec=reel_start_sec,
            score=0.0,
            frame_path=None,
            reason="vision disabled",
        )

    # Семпл 6 кадров в первых 3s: 0.25, 0.75, 1.25, 1.75, 2.25, 2.75 от reel_start.
    timestamps: list[float] = []
    t = sample_step_sec / 2.0
    while t < sample_window_sec:
        timestamps.append(round(reel_start_sec + t, 3))
        t += sample_step_sec

    if not timestamps:
        return CoverResult(
            reel_id=reel_id,
            timestamp_sec=reel_start_sec,
            score=0.0,
            frame_path=None,
            reason="empty sample window",
        )

    async def _score(ts: float) -> CoverCandidate | None:
        try:
            frame = await extractor.extract(source_video_path, video_hash, ts)
        except Exception as exc:
            log.warning("cover_frame_extract_failed", reel_id=reel_id, ts=ts, error=str(exc))
            return None

        answers: dict[str, str] = {}
        score = 0.0
        async with limiter.acquire():
            for key, (question, weight) in _COVER_QUESTIONS.items():
                try:
                    result = await client.query(frame.frame_path, question)
                except Exception as exc:
                    log.warning(
                        "cover_query_failed",
                        reel_id=reel_id, ts=ts, key=key, error=str(exc),
                    )
                    answers[key] = "unknown"
                    continue
                answers[key] = result.answer
                if result.answer == "yes":
                    score += weight
                elif result.answer == "unknown":
                    score += weight * 0.5
        return CoverCandidate(
            timestamp_sec=ts, score=score, frame_path=frame.frame_path, answers=answers
        )

    candidates = await asyncio.gather(*(_score(ts) for ts in timestamps))
    valid = [c for c in candidates if c is not None]
    if not valid:
        return CoverResult(
            reel_id=reel_id,
            timestamp_sec=reel_start_sec,
            score=0.0,
            frame_path=None,
            reason="all frames failed",
        )

    best = max(valid, key=lambda c: c.score)
    reason = (
        f"best of {len(valid)} candidates; "
        + " ".join(f"{k}={v}" for k, v in best.answers.items())
    )
    log.info(
        "cover_selected",
        reel_id=reel_id,
        timestamp_sec=best.timestamp_sec,
        score=round(best.score, 3),
        candidates=len(valid),
    )
    return CoverResult(
        reel_id=reel_id,
        timestamp_sec=best.timestamp_sec,
        score=best.score,
        frame_path=best.frame_path,
        reason=reason,
    )
