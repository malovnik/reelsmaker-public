"""T2.8 slice 3 — word-anchored deictic zoom trigger.

Слова-указатели («вот», «смотри», «здесь») получают zoom-in keyframe
даже если курсор не детектирован. Работает как add-on к cursor zoom
или как самостоятельный layer для не-screencast профилей.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from videomaker.services.spring_zoom_planner import ZoomKeyframe

_DEICTIC_WORDS: frozenset[str] = frozenset(
    {
        "вот",
        "здесь",
        "смотри",
        "тут",
        "сюда",
        "этот",
        "эта",
        "это",
        "here",
        "this",
        "look",
        "see",
        "watch",
    }
)

_STRIP_CHARS = ",.!?;:«»\"' "


def inject_deictic_zoom_triggers(
    words: Sequence[Any],
    existing_keyframes: list[ZoomKeyframe],
    zoom_factor: float = 1.25,
) -> list[ZoomKeyframe]:
    """Добавляет zoom keyframes на deictic words. Возвращает merged список.

    ``words`` — любой iterable объектов с атрибутами ``text``/``word`` и
    ``start_sec``/``start``. Несовпадение формата = graceful skip.
    """
    new_kfs: list[ZoomKeyframe] = []
    for w in words:
        raw = getattr(w, "text", None) or getattr(w, "word", "") or ""
        clean = str(raw).lower().strip(_STRIP_CHARS)
        if clean in _DEICTIC_WORDS:
            t_raw = (
                getattr(w, "start_sec", None)
                or getattr(w, "start", None)
                or 0.0
            )
            try:
                t = float(t_raw)
            except (TypeError, ValueError):
                continue
            new_kfs.append(
                ZoomKeyframe(
                    t_sec=t,
                    zoom_factor=zoom_factor,
                    center_x=0.5,
                    center_y=0.5,
                )
            )
    return sorted(existing_keyframes + new_kfs, key=lambda k: k.t_sec)
