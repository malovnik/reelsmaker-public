"""Статичный реестр видеоэффектов.

Порядок важен — эффекты применяются в заданной последовательности.
Десатурация (B&W) применяется **последней** поверх любых color-grading
эффектов (LUT, color curves), т.к. после неё цветовая информация теряется
необратимо. При будущем добавлении эффектов не забывать про этот инвариант.
"""

from __future__ import annotations

from videomaker.services.video_effects.base import VideoEffect
from videomaker.services.video_effects.bw import BWEffect

EFFECTS_REGISTRY: tuple[VideoEffect, ...] = (
    BWEffect(),
)


def find_effect(effect_id: str) -> VideoEffect | None:
    for effect in EFFECTS_REGISTRY:
        if effect.effect_id == effect_id:
            return effect
    return None


__all__ = ["EFFECTS_REGISTRY", "find_effect"]
