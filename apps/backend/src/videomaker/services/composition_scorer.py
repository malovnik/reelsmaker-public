"""Geometric composition scoring для talking_head профиля.

Детерминированная метрика face centering на основе FaceTrackResult bbox.
В отличие от Moondream ``well_framed`` query (семантическая, LLM-based),
эта метрика чисто геометрическая: считает расстояние от центра лица до
центра кадра в нормализованных координатах (0..1).

## Метрика

```
score = 1 - min(1, euclidean(face_center, frame_center) / MAX_DEVIATION)
```

где `MAX_DEVIATION = 0.5` — половина диагонали кадра. Пороги:

* `score >= 0.85` — лицо близко к центру (tight composition).
* `0.60 <= score < 0.85` — слегка off-center (acceptable).
* `score < 0.60` — заметно off-center → Story Doctor penalty.

## Когда не штрафуем (идемпотентный default)

* `face_track` is None → score=1.0 (нейтрально, baseline для без-vision)
* Нет primary_face в окрестности timestamp → score=1.0
* Vision disabled → валидатор не вызывается вообще
"""

from __future__ import annotations

import math

from videomaker.core.logging import get_logger
from videomaker.services.face_tracker import FaceTrackResult

log = get_logger(__name__)

# Полная диагональ нормализованного кадра: sqrt(0.5^2 + 0.5^2) ≈ 0.707.
# Используем 0.5 как "разумный" максимум смещения: дальше лицо уже вне
# центрального 50% × 50% квадрата, что гарантированно off-center.
MAX_DEVIATION = 0.5

# Порог для `off_center` flag — ниже этого значения считаем composition
# проблемным и добавляем флаг.
OFF_CENTER_THRESHOLD = 0.60


def compute_face_centering_score(
    face_track: FaceTrackResult | None,
    timestamp_sec: float,
) -> float:
    """Возвращает face centering score [0, 1] на момент ``timestamp_sec``.

    1.0 = лицо точно в центре кадра. 0.0 = лицо на краю или нет face_track.

    Args:
        face_track: результат face_tracker или None (no-op → 1.0).
        timestamp_sec: момент в исходном видео (секунды).

    Returns:
        Нормализованный score [0, 1]. 1.0 если нет данных (baseline).
    """
    if face_track is None:
        return 1.0

    face = face_track.best_face_at(timestamp_sec)
    if face is None:
        return 1.0

    cx = face.cx
    cy = face.cy
    # Расстояние от центра лица до центра кадра (0.5, 0.5)
    dx = cx - 0.5
    dy = cy - 0.5
    deviation = math.sqrt(dx * dx + dy * dy)

    score = 1.0 - min(1.0, deviation / MAX_DEVIATION)
    return max(0.0, min(1.0, score))


def is_off_center(score: float) -> bool:
    """True если score ниже ``OFF_CENTER_THRESHOLD``."""
    return score < OFF_CENTER_THRESHOLD


__all__ = [
    "MAX_DEVIATION",
    "OFF_CENTER_THRESHOLD",
    "compute_face_centering_score",
    "is_off_center",
]
