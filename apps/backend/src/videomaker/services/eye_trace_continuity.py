"""T10.8 — Eye trace continuity через MediaPipe Face Mesh iris landmarks.

Проверяет направление взгляда субъекта на границах между сегментами рилса
(особенно важно для cross-scene composer). Если subject смотрит вправо в
конце сегмента A, зритель ожидает пространство для взгляда слева в начале
сегмента B. Нарушение → jump → ощущение непрофессиональности.

MediaPipe Face Mesh c `refine_landmarks=True` даёт iris center через
landmarks 468 (left iris) и 473 (right iris). Упрощённый gaze vector:
horizontal offset от центра лица.

Возвращает penalty score 0..1 для composer scoring (T9 balanced mode),
не hard block. Composer взвесит penalty вместе с другими факторами.

Интерфейс:
    from videomaker.services.eye_trace_continuity import estimate_gaze_penalty
    penalty = await estimate_gaze_penalty(
        frame_a_end_path=..., frame_b_start_path=...
    )
    # → float 0..1 (0 = continuity OK, 1 = сильный eye-trace break)

Graceful: MediaPipe отсутствует → 0.0 (нейтральный penalty).
Нет лица на кадре → 0.0 (не можем оценить).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from videomaker.core.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class GazeEstimate:
    """Оценка направления взгляда на одном кадре."""

    gaze_x: float
    """Horizontal offset iris-center от face-center. Range ~[-0.15, 0.15].
    Положительный = смотрит вправо, отрицательный = влево."""

    confidence: float
    """0..1 насколько надёжно (нет лица → 0, хорошее detection → 1)."""

    has_face: bool


async def estimate_gaze(image_path: Path) -> GazeEstimate:
    """Async wrapper для MediaPipe iris detection."""
    return await asyncio.to_thread(_estimate_gaze_sync, image_path)


def _estimate_gaze_sync(image_path: Path) -> GazeEstimate:
    if not image_path.exists():
        return GazeEstimate(gaze_x=0.0, confidence=0.0, has_face=False)

    try:
        import cv2
        import mediapipe as mp
    except ImportError:
        log.debug("eye_trace_mediapipe_missing")
        return GazeEstimate(gaze_x=0.0, confidence=0.0, has_face=False)

    try:
        frame = cv2.imread(str(image_path))
        if frame is None:
            return GazeEstimate(gaze_x=0.0, confidence=0.0, has_face=False)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        with mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
        ) as face_mesh:
            results = face_mesh.process(rgb)

        if not results.multi_face_landmarks:
            return GazeEstimate(gaze_x=0.0, confidence=0.0, has_face=False)

        landmarks = results.multi_face_landmarks[0].landmark

        # Face center: nose tip landmark 1
        nose = landmarks[1]
        # Iris centers: landmarks 468 (left), 473 (right)
        left_iris = landmarks[468]
        right_iris = landmarks[473]

        iris_center_x = (left_iris.x + right_iris.x) / 2.0
        gaze_x = iris_center_x - nose.x

        return GazeEstimate(
            gaze_x=float(gaze_x),
            confidence=1.0,
            has_face=True,
        )
    except Exception as exc:
        log.debug("eye_trace_estimation_failed", error=str(exc))
        return GazeEstimate(gaze_x=0.0, confidence=0.0, has_face=False)


async def estimate_gaze_penalty(
    frame_a_end_path: Path,
    frame_b_start_path: Path,
    *,
    penalty_threshold: float = 0.08,
) -> float:
    """Возвращает penalty score 0..1 для eye-trace discontinuity.

    ``penalty_threshold`` — разница gaze_x выше которой добавляется penalty.
    Research: > 0.3 = сильное нарушение (composer должен учесть).

    Если MediaPipe недоступен или лица не найдены — возвращает 0.0
    (graceful, не ломает composer scoring).
    """
    gaze_a, gaze_b = await asyncio.gather(
        estimate_gaze(frame_a_end_path),
        estimate_gaze(frame_b_start_path),
    )

    if not gaze_a.has_face or not gaze_b.has_face:
        return 0.0

    # gaze_a > 0 (смотрит вправо) + gaze_b > 0 (начинает справа) =
    # BAD (зритель ожидал что subject смотрит влево → пространство справа)
    # gaze_a > 0 + gaze_b < 0 = GOOD (subject перешёл на левую сторону)
    same_side = (gaze_a.gaze_x * gaze_b.gaze_x) > 0
    if not same_side:
        return 0.0

    delta = abs(gaze_a.gaze_x - gaze_b.gaze_x)
    if delta <= penalty_threshold:
        return 0.0

    # Normalize to 0..1, saturates at delta=0.3
    penalty = min(1.0, (delta - penalty_threshold) / 0.22)
    return round(penalty, 3)


__all__ = [
    "GazeEstimate",
    "estimate_gaze",
    "estimate_gaze_penalty",
]
