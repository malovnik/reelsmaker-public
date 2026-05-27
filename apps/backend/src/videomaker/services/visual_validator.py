"""Visual Validator — Stage 5.5.5 между rhythm_check и variants_generator.

Цель: для каждого сегмента arc выставить `visual_score` и `visual_flags`
на основе 3 yes/no VQA-запросов к Moondream 2:

* face_visible (вес 0.4) — «is a person's face clearly visible in this image?»
* well_framed  (вес 0.3) — «is the main subject well-framed and centered?»
* energetic    (вес 0.3) — «does the person look engaged or expressive?»

Формула: `visual_score = 0.4*face_ok + 0.3*framed_ok + 0.3*energy_ok`.
Unknown-ответ считается как 0.5 (не штрафуем за неуверенность модели).

Flags:
* no face_visible → `face_off_screen`
* no well_framed  → `poor_framing`
* no energetic    → `low_energy`
* any unknown     → `occluded`
* all positive    → `visual_ok`

Fallback: если `client is None` (vision disabled) → script возвращается
без изменений. Это главный инвариант — пайплайн работает как раньше когда
vision выключен.

Concurrency: сегменты валидируются параллельно через VisionRateLimiter
(max_concurrent=2 по умолчанию). GPU serialization обеспечивает клиент.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from videomaker.core.logging import get_logger
from videomaker.models.story_script import StoryScript, StorySegment, VisualFlag
from videomaker.services.composition_scorer import (
    compute_face_centering_score,
    is_off_center,
)
from videomaker.services.face_tracker import FaceTrackResult
from videomaker.services.vision import (
    FrameExtractor,
    VisionClient,
    VisionQueryResult,
    VisionRateLimiter,
    VisionResultCache,
)

log = get_logger(__name__)


_QUESTIONS: dict[str, str] = {
    "face_visible": "Is a person's face clearly visible in this image?",
    "well_framed": "Is the main subject well-framed and centered in this image?",
    "energetic": "Does the person look engaged, energetic, or emotionally expressive?",
}

_WEIGHTS: dict[str, float] = {
    "face_visible": 0.4,
    "well_framed": 0.3,
    "energetic": 0.3,
}

_FLAG_ON_NO: dict[str, VisualFlag] = {
    "face_visible": "face_off_screen",
    "well_framed": "poor_framing",
    "energetic": "low_energy",
}


def _answer_to_fraction(answer: str) -> float:
    """yes→1.0, no→0.0, unknown→0.5 (нейтрально)."""
    if answer == "yes":
        return 1.0
    if answer == "no":
        return 0.0
    return 0.5


def _midpoint_timestamp(segment: StorySegment) -> float:
    return (segment.source_start_sec + segment.source_end_sec) / 2.0


async def validate_arc(
    script: StoryScript,
    video_path: Path,
    video_hash: str,
    *,
    client: VisionClient | None,
    extractor: FrameExtractor,
    cache: VisionResultCache,
    limiter: VisionRateLimiter,
    face_track: FaceTrackResult | None = None,
    apply_centering_penalty: bool = False,
) -> StoryScript:
    """Обогащает arc vision-метриками. Noop при client=None.

    Идемпотентно: повторный вызов читает результаты из VisionResultCache.
    Ошибка на отдельном сегменте не ломает весь arc — затронутый сегмент
    получает `visual_score=1.0` (neutral, не штрафуем за flaky).

    Args:
        face_track: если передан, каждый segment получает geometric
            `face_centering_score` через composition_scorer. Иначе идет
            baseline 1.0.
        apply_centering_penalty: если True (обычно только для
            talking_head профиля + vision_enabled) — off-center сегменты
            получают flag `off_center` и penalty на visual_score.
    """
    if client is None:
        log.debug("visual_validator_disabled")
        return script
    if not script.arc:
        return script

    async def _validate_one(segment: StorySegment) -> StorySegment:
        try:
            scored = await _score_segment(
                segment,
                video_path=video_path,
                video_hash=video_hash,
                client=client,
                extractor=extractor,
                cache=cache,
                limiter=limiter,
            )
        except Exception as exc:
            log.warning(
                "visual_validator_segment_failed",
                evidence_id=segment.evidence_id,
                role=segment.role,
                error=str(exc),
            )
            return segment
        # Geometric face centering (только если есть face_track)
        centering_score = compute_face_centering_score(
            face_track, _midpoint_timestamp(scored)
        )
        updated_flags = list(scored.visual_flags)
        updated_visual_score = scored.visual_score
        if apply_centering_penalty and is_off_center(centering_score):
            if "off_center" not in updated_flags:
                updated_flags.append("off_center")
            # Penalty: умножаем visual_score на centering_score
            # (худший centering → больший штраф). Инвариант: score ∈ [0, 1].
            updated_visual_score = scored.visual_score * centering_score
        return scored.model_copy(
            update={
                "face_centering_score": centering_score,
                "visual_flags": updated_flags,
                "visual_score": updated_visual_score,
            }
        )

    validated = await asyncio.gather(*(_validate_one(s) for s in script.arc))
    flagged = sum(1 for s in validated if s.visual_score < 0.4)
    log.info(
        "visual_validator_done",
        segments=len(validated),
        flagged=flagged,
        avg_score=round(
            sum(s.visual_score for s in validated) / max(len(validated), 1), 3
        ),
    )
    return script.model_copy(update={"arc": list(validated)})


async def _score_segment(
    segment: StorySegment,
    *,
    video_path: Path,
    video_hash: str,
    client: VisionClient,
    extractor: FrameExtractor,
    cache: VisionResultCache,
    limiter: VisionRateLimiter,
) -> StorySegment:
    """Обрабатывает один сегмент: кадр → 3 yes/no → score + flags."""
    timestamp = _midpoint_timestamp(segment)
    if timestamp < 0 or segment.duration_sec <= 0.0:
        return segment

    cached_frame = await extractor.extract(video_path, video_hash, timestamp)

    answers: dict[str, VisionQueryResult] = {}
    async with limiter.acquire():
        for key, question in _QUESTIONS.items():
            cached = await cache.get(
                video_hash,
                op="query",
                timestamp_sec=timestamp,
                params={"question": question},
            )
            if cached is not None:
                answers[key] = VisionQueryResult.model_validate(cached)
                continue
            result = await client.query(cached_frame.frame_path, question)
            answers[key] = result
            await cache.put(
                video_hash,
                op="query",
                timestamp_sec=timestamp,
                params={"question": question},
                value=result.model_dump(),
            )

    score = sum(
        _WEIGHTS[key] * _answer_to_fraction(answers[key].answer)
        for key in _WEIGHTS
    )
    score = max(0.0, min(1.0, score))

    flags: list[VisualFlag] = []
    has_unknown = False
    for key, result in answers.items():
        if result.answer == "no" and key in _FLAG_ON_NO:
            flags.append(_FLAG_ON_NO[key])
        elif result.answer == "unknown":
            has_unknown = True
    if has_unknown and not flags:
        flags.append("occluded")
    if not flags and score >= 0.8:
        flags.append("visual_ok")

    reasoning = (
        f"face={answers['face_visible'].answer} "
        f"framed={answers['well_framed'].answer} "
        f"energy={answers['energetic'].answer}"
    )

    return segment.model_copy(
        update={
            "visual_score": score,
            "visual_flags": flags,
            "visual_reasoning": reasoning,
        }
    )
