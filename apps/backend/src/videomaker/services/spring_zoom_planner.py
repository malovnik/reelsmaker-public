"""T2.8 slice 2 — spring-based zoom planner.

MIT port из Screen-Studio-Effects: damped harmonic oscillator через
discrete integration step-by-step. Три damping profile:
underdamped / critically_damped / overdamped.

Pipeline: raw cursor events → spring smoothing → clamp zoom ∈
[1.0, max_zoom] + center ∈ [0, 1] → список ZoomKeyframe.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from videomaker.services.cursor_detector import CursorEvent

DampingProfile = Literal["underdamped", "critically_damped", "overdamped"]

_DAMPING_VALUES: dict[DampingProfile, float] = {
    "underdamped": 0.5,
    "critically_damped": 1.0,
    "overdamped": 1.7,
}

# 0.8 Hz natural frequency — плавное движение на масштабе секунды.
_NATURAL_FREQ = 2.0 * math.pi * 0.8


@dataclass(slots=True)
class ZoomKeyframe:
    """Один sample zoom plan: время, zoom-коэффициент, центр в [0, 1]."""

    t_sec: float
    zoom_factor: float
    center_x: float
    center_y: float


def plan_screencast_zoom(
    cursor_events: list[CursorEvent],
    video_width: int,
    video_height: int,
    profile: DampingProfile = "critically_damped",
    max_zoom_factor: float = 2.0,
    active_zoom: float = 1.5,
    idle_zoom: float = 1.0,
    active_displacement_threshold: float = 0.02,
) -> list[ZoomKeyframe]:
    """Spring smoothing для cursor trajectory.

    Логика target:
    - курсор двигается медленно (disp < threshold) → zoom in (active_zoom)
    - курсор двигается быстро → zoom out (idle_zoom)
    После smoothing через damped harmonic oscillator.
    """
    if not cursor_events or video_width <= 0 or video_height <= 0:
        return []

    damping = _DAMPING_VALUES[profile]
    keyframes: list[ZoomKeyframe] = []
    current_zoom = 1.0
    current_cx, current_cy = 0.5, 0.5
    velocity_z = velocity_cx = velocity_cy = 0.0
    prev_t = cursor_events[0].t_sec

    for ev in cursor_events:
        dt = max(1e-3, ev.t_sec - prev_t)
        target_cx = max(0.0, min(1.0, ev.x / video_width))
        target_cy = max(0.0, min(1.0, ev.y / video_height))
        disp = math.hypot(target_cx - current_cx, target_cy - current_cy)
        target_zoom = (
            active_zoom
            if disp < active_displacement_threshold
            else idle_zoom
        )
        target_zoom = min(target_zoom, max_zoom_factor)

        # Damped harmonic oscillator: x'' = -w^2 (x-target) - 2ζw x'
        accel_z = (
            -(_NATURAL_FREQ**2) * (current_zoom - target_zoom)
            - 2 * damping * _NATURAL_FREQ * velocity_z
        )
        velocity_z += accel_z * dt
        current_zoom += velocity_z * dt

        accel_cx = (
            -(_NATURAL_FREQ**2) * (current_cx - target_cx)
            - 2 * damping * _NATURAL_FREQ * velocity_cx
        )
        velocity_cx += accel_cx * dt
        current_cx += velocity_cx * dt

        accel_cy = (
            -(_NATURAL_FREQ**2) * (current_cy - target_cy)
            - 2 * damping * _NATURAL_FREQ * velocity_cy
        )
        velocity_cy += accel_cy * dt
        current_cy += velocity_cy * dt

        keyframes.append(
            ZoomKeyframe(
                t_sec=ev.t_sec,
                zoom_factor=max(1.0, min(max_zoom_factor, current_zoom)),
                center_x=max(0.0, min(1.0, current_cx)),
                center_y=max(0.0, min(1.0, current_cy)),
            )
        )
        prev_t = ev.t_sec
    return keyframes
