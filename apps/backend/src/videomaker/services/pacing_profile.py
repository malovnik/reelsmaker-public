"""T10.4 + T10.5 — Pacing Profile templates + Variable Shot Duration.

Шаблоны почерка монтажёра (PacingProfile) — группы связанных параметров
которые обычно идут вместе: shot_duration_mode, punch_in_rate, transition_ratio,
punchline_hold. Гарантирует консистентность между рилсами одного job
(все имеют похожий ритм).

Research (editing-craft-2026.md §B top-5):
- dynamic — для high-energy content (короткие шоты, частый punch-in)
- documentary — для обучающего/медленного (длинные шоты, Ken Burns)
- mkbhd_clean — clean tech review (средний темп, минимум transitions)
- balanced — default middle ground

T10.4 Variable Shot Duration — маппинг energy range → target duration:
    energy 0.0-0.3 → 3.5 сек
    energy 0.3-0.6 → 2.5 сек
    energy 0.6-0.8 → 1.8 сек
    energy 0.8-1.0 → 1.2 сек

Интерфейс:
    from videomaker.services.pacing_profile import (
        PACING_PROFILES, target_shot_duration_by_energy
    )
    template = PACING_PROFILES["dynamic"]
    target = target_shot_duration_by_energy(energy=0.75, template=template)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PacingProfileName = Literal["dynamic", "documentary", "mkbhd_clean", "balanced"]


@dataclass(slots=True, frozen=True)
class PacingProfileTemplate:
    """Коллекция параметров характеризующих почерк монтажёра."""

    name: PacingProfileName
    display_label: str

    # Shot duration distribution (T10.4)
    shot_duration_min: float
    shot_duration_mode: float
    shot_duration_max: float

    # T10.3 punch-in zoom params
    punch_in_rate: float  # 0..1 probability на emphasis moment
    punch_in_scale: float  # 1.04..1.15

    # T10.1 punchline params
    punchline_hold_sec: float

    # T10.6 transition weights — относительные веса разных типов cut'ов
    transition_hard_cut: float
    transition_j_cut: float
    transition_l_cut: float
    transition_dissolve: float

    # T10.7 Ken Burns
    ken_burns_enabled_default: bool
    ken_burns_scale_per_sec: float


PACING_PROFILES: dict[PacingProfileName, PacingProfileTemplate] = {
    "dynamic": PacingProfileTemplate(
        name="dynamic",
        display_label="Динамичный",
        shot_duration_min=1.2,
        shot_duration_mode=1.8,
        shot_duration_max=4.0,
        punch_in_rate=0.4,
        punch_in_scale=1.08,
        punchline_hold_sec=0.30,
        transition_hard_cut=0.85,
        transition_j_cut=0.10,
        transition_l_cut=0.04,
        transition_dissolve=0.01,
        ken_burns_enabled_default=False,
        ken_burns_scale_per_sec=0.003,
    ),
    "balanced": PacingProfileTemplate(
        name="balanced",
        display_label="Сбалансированный",
        shot_duration_min=1.5,
        shot_duration_mode=2.5,
        shot_duration_max=5.0,
        punch_in_rate=0.3,
        punch_in_scale=1.06,
        punchline_hold_sec=0.45,
        transition_hard_cut=0.80,
        transition_j_cut=0.12,
        transition_l_cut=0.06,
        transition_dissolve=0.02,
        ken_burns_enabled_default=False,
        ken_burns_scale_per_sec=0.003,
    ),
    "mkbhd_clean": PacingProfileTemplate(
        name="mkbhd_clean",
        display_label="MKBHD clean",
        shot_duration_min=1.8,
        shot_duration_mode=2.8,
        shot_duration_max=5.5,
        punch_in_rate=0.2,
        punch_in_scale=1.05,
        punchline_hold_sec=0.40,
        transition_hard_cut=0.95,
        transition_j_cut=0.03,
        transition_l_cut=0.02,
        transition_dissolve=0.0,
        ken_burns_enabled_default=False,
        ken_burns_scale_per_sec=0.003,
    ),
    "documentary": PacingProfileTemplate(
        name="documentary",
        display_label="Документальный",
        shot_duration_min=2.5,
        shot_duration_mode=3.5,
        shot_duration_max=8.0,
        punch_in_rate=0.15,
        punch_in_scale=1.04,
        punchline_hold_sec=0.55,
        transition_hard_cut=0.70,
        transition_j_cut=0.13,
        transition_l_cut=0.10,
        transition_dissolve=0.07,
        ken_burns_enabled_default=True,
        ken_burns_scale_per_sec=0.004,
    ),
}


def target_shot_duration_by_energy(
    energy: float,
    template: PacingProfileTemplate,
) -> float:
    """T10.4 — Variable Shot Duration от energy score.

    energy 0.0-0.3 (low) → mode * 1.4 (clamped to max)
    energy 0.3-0.6 (medium) → mode
    energy 0.6-0.8 (high) → mode * 0.72
    energy 0.8-1.0 (peak) → min + 0.1

    Все значения clamped в [min, max] template'а чтобы сохранить почерк.
    """
    energy = max(0.0, min(1.0, energy))
    if energy < 0.3:
        target = template.shot_duration_mode * 1.4
    elif energy < 0.6:
        target = template.shot_duration_mode
    elif energy < 0.8:
        target = template.shot_duration_mode * 0.72
    else:
        target = template.shot_duration_min + 0.1

    return max(
        template.shot_duration_min,
        min(template.shot_duration_max, round(target, 2)),
    )


def get_template(name: str) -> PacingProfileTemplate:
    """Lookup template by name with fallback to balanced."""
    if name in PACING_PROFILES:
        return PACING_PROFILES[name]  # type: ignore[index]
    return PACING_PROFILES["balanced"]


__all__ = [
    "PACING_PROFILES",
    "PacingProfileName",
    "PacingProfileTemplate",
    "get_template",
    "target_shot_duration_by_energy",
]
