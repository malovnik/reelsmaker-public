"""Генерация caption + title per (reel × account) через Gemini Flash Lite."""
from __future__ import annotations

from dataclasses import dataclass

from videomaker.core.logging import get_logger
from videomaker.models.reel_plan import ReelPlan
from videomaker.models.scheduler import AccountProfileRow
from videomaker.services.llm_clients import LLMClient, LLMError, parse_json_response
from videomaker.services.prompt_store import get_prompt
from videomaker.services.prompts import PromptKey

log = get_logger(__name__)


@dataclass(frozen=True)
class GeneratedCaption:
    title: str
    caption: str
    hashtags: list[str]


async def generate_caption(
    *,
    reel: ReelPlan,
    profile: AccountProfileRow,
    llm: LLMClient,
) -> GeneratedCaption:
    system = await get_prompt(PromptKey.publer_caption)
    user = _build_user_message(reel=reel, profile=profile)

    response = await llm.complete_json(
        system=system,
        user=user,
        temperature=0.7,
        max_tokens=4096,
    )

    try:
        parsed = parse_json_response(response.text)
    except LLMError as exc:
        log.warning(
            "caption_json_parse_failed",
            reel_id=reel.reel_id,
            error=str(exc),
        )
        raise

    if not isinstance(parsed, dict):
        raise LLMError(
            f"caption_json_invalid_type reel_id={reel.reel_id} type={type(parsed).__name__}"
        )

    title = str(parsed.get("title") or "")
    caption = str(parsed.get("caption") or "")
    hashtags = [h for h in (parsed.get("hashtags") or []) if isinstance(h, str) and h]
    return GeneratedCaption(title=title, caption=caption, hashtags=hashtags)


def _build_user_message(*, reel: ReelPlan, profile: AccountProfileRow) -> str:
    default_hashtags = ", ".join(profile.default_hashtags_json) or "(нет)"
    banned_words = ", ".join(profile.banned_words_json) or "(нет)"
    segments_reasoning = " | ".join(s.reasoning for s in reel.segments[:3])
    return (
        f"АККАУНТ: {profile.display_name} ({profile.network})\n"
        f"LANGUAGE: {profile.language}\n"
        f"AUDIENCE: {profile.audience or '(не задано)'}\n"
        f"TONE: {profile.tone or '(нейтральный)'}\n"
        f"CTA_STYLE: {profile.cta_style or '(без CTA)'}\n"
        f"DEFAULT_HASHTAGS: {default_hashtags}\n"
        f"BANNED_WORDS: {banned_words}\n"
        f"MAX_CAPTION_LENGTH: {profile.max_caption_length}\n"
        f"\n"
        f"РИЛС:\n"
        f"HOOK: {reel.hook}\n"
        f"TARGET_AUDIENCE_ORIG: {reel.target_audience or '(не задано)'}\n"
        f"DURATION_SEC: {reel.predicted_duration_sec:.1f}\n"
        f"SEGMENTS_REASONING: {segments_reasoning}\n"
        f"\n"
        f"Верни строго JSON {{title, caption, hashtags}}."
    )
