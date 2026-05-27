"""Unit-тесты plugin registry video effects + BW."""

from __future__ import annotations

from videomaker.models.post_production import PostProductionConfig
from videomaker.services.video_effects import (
    EFFECTS_REGISTRY,
    BWEffect,
    VideoEffect,
    VideoEffectContext,
    find_effect,
)


def _config(**overrides: object) -> PostProductionConfig:
    defaults: dict[str, object] = {
        "audio_normalize_enabled": False,
        "zoom_enabled": False,
        "bw_enabled": False,
    }
    defaults.update(overrides)
    return PostProductionConfig(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------


def test_registry_contains_bw() -> None:
    assert any(isinstance(e, BWEffect) for e in EFFECTS_REGISTRY)


def test_find_effect_returns_instance() -> None:
    effect = find_effect("bw")
    assert effect is not None
    assert effect.effect_id == "bw"


def test_find_effect_unknown_returns_none() -> None:
    assert find_effect("nonexistent") is None


def test_all_effects_follow_protocol() -> None:
    for effect in EFFECTS_REGISTRY:
        assert isinstance(effect, VideoEffect)
        assert effect.effect_id
        assert effect.label


# ---------------------------------------------------------------------------
# BWEffect
# ---------------------------------------------------------------------------


def test_bw_disabled_returns_none() -> None:
    ctx = VideoEffectContext(post_production_config=_config(bw_enabled=False))
    assert BWEffect().build_filter_expr(ctx) is None


def test_bw_enabled_returns_hue_filter() -> None:
    ctx = VideoEffectContext(post_production_config=_config(bw_enabled=True))
    expr = BWEffect().build_filter_expr(ctx)
    assert expr == "hue=s=0"


def test_bw_effect_id_stable() -> None:
    assert BWEffect.effect_id == "bw"
