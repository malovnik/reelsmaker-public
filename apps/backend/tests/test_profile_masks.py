"""Smoke-тесты per-profile agent mask (PHASE 3.1)."""

from __future__ import annotations

import pytest

from videomaker.models.evidence import RankedEvidenceItem
from videomaker.models.job import VisionProfile
from videomaker.services.profile_masks import (
    CompositionTuning,
    ProfileMask,
    apply_profile_weights,
    get_enabled_agents_for_profile,
    get_profile_mask,
)


def test_talking_head_mask_has_all_six_agents() -> None:
    mask = get_profile_mask(VisionProfile.talking_head)
    assert len(mask.enabled_agents) == 6
    assert "humor_specialist" in mask.enabled_agents
    assert "thesis_extractor" in mask.enabled_agents


def test_fashion_mask_removes_text_heavy() -> None:
    mask = get_profile_mask(VisionProfile.fashion)
    assert "humor_specialist" not in mask.enabled_agents
    assert "dramatic_irony_scanner" not in mask.enabled_agents
    assert "thesis_extractor" not in mask.enabled_agents
    assert "hook_hunter" in mask.enabled_agents
    assert "emotional_peak_finder" in mask.enabled_agents
    assert "motif_tracker" in mask.enabled_agents


def test_travel_mask_removes_text_heavy() -> None:
    mask = get_profile_mask(VisionProfile.travel)
    assert "humor_specialist" not in mask.enabled_agents
    assert "thesis_extractor" not in mask.enabled_agents


def test_screencast_mask_keeps_thesis_drops_humor() -> None:
    mask = get_profile_mask(VisionProfile.screencast)
    assert "humor_specialist" not in mask.enabled_agents
    assert "thesis_extractor" in mask.enabled_agents


def test_custom_mask_defaults_to_all_agents() -> None:
    mask = get_profile_mask(VisionProfile.custom)
    assert len(mask.enabled_agents) == 6


def test_vision_disabled_returns_all_agents_regardless_of_profile() -> None:
    """Инвариант: без визуального пути запускаем полный text-анализ."""
    for profile in VisionProfile:
        agents = get_enabled_agents_for_profile(profile, vision_enabled=False)
        assert len(agents) == 6, (
            f"{profile}: vision_disabled must return all 6 agents, got {agents}"
        )


def test_vision_enabled_respects_profile_mask() -> None:
    fashion_agents = get_enabled_agents_for_profile(
        VisionProfile.fashion, vision_enabled=True
    )
    assert len(fashion_agents) < 6
    assert "humor_specialist" not in fashion_agents


def test_mask_weights_sum_to_one_for_all_profiles() -> None:
    for profile in VisionProfile:
        mask = get_profile_mask(profile)
        total = mask.story_weight + mask.visual_weight
        assert total == pytest.approx(1.0), (
            f"{profile}: weights must sum to 1.0, got {total}"
        )


def test_fashion_has_higher_visual_weight_than_talking_head() -> None:
    th = get_profile_mask(VisionProfile.talking_head)
    fashion = get_profile_mask(VisionProfile.fashion)
    assert fashion.visual_weight > th.visual_weight


def test_invalid_weights_raises() -> None:
    with pytest.raises(ValueError):
        ProfileMask(
            profile=VisionProfile.custom,
            enabled_agents=("hook_hunter",),
            story_weight=0.6,
            visual_weight=0.6,  # sum > 1.0
        )


def _mk_item(
    item_id: str,
    source_agent: str = "hook_hunter",
    *,
    composite_score: float = 0.5,
    visual_caption: str = "",
    visual_tags: list[str] | None = None,
) -> RankedEvidenceItem:
    return RankedEvidenceItem(
        id=item_id,
        source_agent=source_agent,  # type: ignore[arg-type]
        start=0.0,
        end=1.0,
        text="t",
        category="hook_candidate",
        composite_score=composite_score,
        visual_caption=visual_caption,
        visual_tags=visual_tags or [],
    )


def test_apply_profile_weights_fashion_boosts_visual() -> None:
    items = [
        _mk_item("text", composite_score=0.6),
        _mk_item("visual", composite_score=0.6, visual_caption="A model walking"),
    ]
    fashion = get_profile_mask(VisionProfile.fashion)
    reweighted = apply_profile_weights(items, fashion)

    visual = next(i for i in reweighted if i.id == "visual")
    text = next(i for i in reweighted if i.id == "text")
    assert visual.composite_score > 0.6  # boosted
    assert text.composite_score < 0.6  # dampened
    # Sorted desc
    assert reweighted[0].id == "visual"


def test_apply_profile_weights_talking_head_boosts_text() -> None:
    items = [
        _mk_item("text", composite_score=0.5),
        _mk_item("visual", composite_score=0.5, visual_caption="A speaker"),
    ]
    th = get_profile_mask(VisionProfile.talking_head)
    reweighted = apply_profile_weights(items, th)

    text = next(i for i in reweighted if i.id == "text")
    visual = next(i for i in reweighted if i.id == "visual")
    assert text.composite_score > 0.5
    assert visual.composite_score < 0.5
    assert reweighted[0].id == "text"


def test_apply_profile_weights_clamps_to_one() -> None:
    items: list[RankedEvidenceItem] = [
        _mk_item("visual", composite_score=0.95, visual_caption="x")
    ]
    fashion = get_profile_mask(VisionProfile.fashion)
    reweighted = apply_profile_weights(items, fashion)
    assert 0.0 <= reweighted[0].composite_score <= 1.0


def test_apply_profile_weights_preserves_order_when_no_visual_enrichment() -> None:
    """Инвариант: без visual enrichment (vision_disabled или не сработало)
    fashion/travel/etc не должны инвертировать порядок — все items получают
    одинаковый multiplier (story_weight), relative ranking сохраняется.
    """
    items = [
        _mk_item("top", composite_score=0.8),
        _mk_item("mid", composite_score=0.5),
        _mk_item("low", composite_score=0.3),
    ]
    fashion = get_profile_mask(VisionProfile.fashion)
    reweighted = apply_profile_weights(items, fashion)
    assert [i.id for i in reweighted] == ["top", "mid", "low"]


def test_composition_tuning_fashion_tighter_than_talking_head() -> None:
    th = get_profile_mask(VisionProfile.talking_head)
    fashion = get_profile_mask(VisionProfile.fashion)
    assert fashion.composition.dead_zone_norm < th.composition.dead_zone_norm
    assert fashion.composition.ema_alpha < th.composition.ema_alpha
    assert (
        fashion.composition.rule_of_thirds_y_shift
        > th.composition.rule_of_thirds_y_shift
    )


def test_composition_tuning_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        CompositionTuning(dead_zone_norm=0.0)
    with pytest.raises(ValueError):
        CompositionTuning(ema_alpha=0.0)
    with pytest.raises(ValueError):
        CompositionTuning(ema_alpha=1.5)
    with pytest.raises(ValueError):
        CompositionTuning(rule_of_thirds_y_shift=-0.1)
