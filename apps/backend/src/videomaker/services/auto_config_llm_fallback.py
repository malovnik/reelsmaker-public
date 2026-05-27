"""T11.5 — LLM fallback для Automatic Mode (Gemini 2.5 Flash Lite).

Когда `auto_config_advisor.advise_config()` вернул meta_confidence < 0.4
(низкая уверенность rule tree), этот модуль делает второй проход через
Gemini Flash Lite — передаёт audio features + transcript summary и
просит LLM принять narrative-level решения которые hard rules не умеют.

Используем **gemini-2.5-flash-lite** — строгое требование пользователя
(feedback_videomaker_gemini_only). Не Pro, не Opus, не anthropic — только
2.5 Flash Lite, она даёт идеальный structured output.

Graceful degrade:
- Если Gemini API недоступен → возвращаем rule-tree AutoConfig без изменений
- Если LLM вернул невалидный JSON → игнорируем, возвращаем rule-tree config
- Если время ответа > 5 сек → timeout, rule-tree config

Интерфейс:
    from videomaker.services.auto_config_llm_fallback import llm_narrative_advise
    config = await llm_narrative_advise(
        rule_config=cfg_from_rule_tree,
        audio_profile=profile,
        transcript_summary="Первые 500 слов...",
    )
    # → AutoConfig с narrative-refined decisions
"""

from __future__ import annotations

import json
from typing import Any, cast

from videomaker.core.logging import get_logger
from videomaker.models.audio_profile import AudioProfile
from videomaker.services.auto_config_advisor import (
    AutoConfig,
    ComposerStrategyDecision,
    DecisionEvidence,
    PacingProfile,
)

log = get_logger(__name__)


#: Модель для fallback (user strict rule — только Gemini 2.5 Flash Lite).
_LLM_MODEL = "gemini-2.5-flash-lite"
_LLM_PROVIDER = "gemini"


_SYSTEM_PROMPT = """Ты — AI video editor, решающий narrative parameters \
для нарезки видео на рилсы. Получаешь:
1. Audio features (SNR, pitch, speech rate, loudness, pauses)
2. Краткую суммаризацию transcript (первые ~500 слов)
3. Текущие решения rule tree (которые можно корректировать)

Твоя задача — уточнить решения которые rule tree принял с низкой \
уверенностью. Фокус на narrative-level параметры, где простые правила \
не справляются:
- composer_strategy (tight_context / balanced / thematic_free) — \
насколько свободно composer может собирать рилс из разных частей видео
- coherence_threshold (0.3-0.7) — насколько строго проверять связность рилса
- pacing_profile (dynamic/balanced/mkbhd_clean/documentary) — общий темп

ВАЖНО:
- Верни ТОЛЬКО JSON с ключами ниже, без комментариев или объяснений
- Если rule tree выбор корректен — оставь значения как есть
- Все значения должны быть в рекомендованных диапазонах
- Если не уверен — не меняй"""


_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "composer_strategy": {
            "type": "string",
            "enum": ["tight_context", "balanced", "thematic_free"],
        },
        "coherence_threshold": {"type": "number"},
        "pacing_profile": {
            "type": "string",
            "enum": ["dynamic", "balanced", "mkbhd_clean", "documentary"],
        },
        "narrative_notes": {
            "type": "string",
            "description": "1-2 sentences — обоснование решения",
        },
    },
    "required": ["composer_strategy", "coherence_threshold", "pacing_profile"],
    "additionalProperties": False,
}


async def llm_narrative_advise(
    *,
    rule_config: AutoConfig,
    audio_profile: AudioProfile,
    transcript_summary: str = "",
    timeout_sec: float = 5.0,
) -> AutoConfig:
    """Уточнение narrative-params через Gemini 2.5 Flash Lite.

    Применяется только если ``rule_config.requires_llm_fallback == True``.
    Возвращает исходный config без изменений если LLM недоступен/упал/timeout.
    """
    if not rule_config.requires_llm_fallback:
        return rule_config

    try:
        import asyncio

        from videomaker.services.llm_client import build_llm

        client = build_llm(_LLM_PROVIDER, _LLM_MODEL)

        user_payload = _build_user_payload(
            rule_config, audio_profile, transcript_summary
        )

        response = await asyncio.wait_for(
            client.complete_json(
                system=_SYSTEM_PROMPT,
                user=user_payload,
                temperature=0.3,
                max_tokens=512,
                response_schema=_RESPONSE_SCHEMA,
            ),
            timeout=timeout_sec,
        )

        data = json.loads(response.text)

    except TimeoutError:
        log.warning("llm_fallback_timeout", timeout_sec=timeout_sec)
        return rule_config
    except Exception as exc:
        log.warning("llm_fallback_failed_graceful", error=str(exc))
        return rule_config

    if not isinstance(data, dict):
        log.warning("llm_fallback_invalid_response_type", got=type(data).__name__)
        return rule_config

    return _apply_llm_overrides(rule_config, data)


def _build_user_payload(
    rule_config: AutoConfig,
    profile: AudioProfile,
    transcript_summary: str,
) -> str:
    features_str = (
        f"SNR: {profile.snr_db:.1f} dB\n"
        f"Speech rate: {profile.wps:.1f} words/sec\n"
        f"Pitch std: {profile.pitch_std_hz:.0f} Hz "
        f"({'monotone' if profile.pitch_std_hz < 15 else 'emotional' if profile.pitch_std_hz > 40 else 'moderate'})\n"
        f"LRA: {profile.lra_lu:.1f} LU\n"
        f"Mean gap: {profile.mean_gap_sec:.2f} sec, "
        f"kurtosis: {profile.gap_kurtosis:.1f}\n"
        f"Rhythm CV: {profile.rhythm_cv:.2f} "
        f"({'regular' if profile.rhythm_cv < 0.3 else 'chaotic' if profile.rhythm_cv > 0.8 else 'speech'})\n"
        f"Whisper confidence: {profile.whisper_avg_confidence:.2f}\n"
        f"Duration: {profile.total_duration_sec:.0f} sec\n"
        f"Content type hint: {profile.content_type}\n"
    )

    rule_str = (
        f"composer_strategy: {rule_config.composer_strategy}\n"
        f"coherence_threshold: {rule_config.coherence_threshold}\n"
        f"pacing_profile: {rule_config.pacing_profile}\n"
        f"meta_confidence: {rule_config.meta_confidence}\n"
    )

    transcript_block = (
        transcript_summary[:2000]
        if transcript_summary
        else "(transcript summary not provided — work from audio features only)"
    )

    return (
        f"=== AUDIO FEATURES ===\n{features_str}\n"
        f"=== RULE TREE DECISIONS (для коррекции) ===\n{rule_str}\n"
        f"=== TRANSCRIPT SUMMARY ===\n{transcript_block}\n\n"
        f"Верни JSON с финальными значениями для composer_strategy, "
        f"coherence_threshold (0.3-0.7), pacing_profile + narrative_notes."
    )


def _apply_llm_overrides(
    rule_config: AutoConfig, overrides: dict[str, Any]
) -> AutoConfig:
    """Применяет LLM decisions поверх rule_config, добавляет evidence."""
    new_evidence = list(rule_config.evidence)

    composer = overrides.get("composer_strategy")
    if isinstance(composer, str) and composer in {
        "tight_context",
        "balanced",
        "thematic_free",
    } and composer != rule_config.composer_strategy:
        new_evidence.append(
            DecisionEvidence(
                parameter="composer_strategy",
                value=composer,
                confidence=0.6,
                source="llm",
                reasoning=overrides.get("narrative_notes", "LLM narrative advisor"),
            )
        )
        rule_config.composer_strategy = cast(ComposerStrategyDecision, composer)

    coherence = overrides.get("coherence_threshold")
    if isinstance(coherence, int | float):
        clamped = max(0.3, min(0.7, float(coherence)))
        if abs(clamped - rule_config.coherence_threshold) > 0.01:
            new_evidence.append(
                DecisionEvidence(
                    parameter="coherence_threshold",
                    value=round(clamped, 2),
                    confidence=0.6,
                    source="llm",
                    reasoning="LLM narrative refinement",
                )
            )
            rule_config.coherence_threshold = round(clamped, 2)

    pacing = overrides.get("pacing_profile")
    if isinstance(pacing, str) and pacing in {
        "dynamic",
        "balanced",
        "mkbhd_clean",
        "documentary",
    } and pacing != rule_config.pacing_profile:
        new_evidence.append(
            DecisionEvidence(
                parameter="pacing_profile",
                value=pacing,
                confidence=0.6,
                source="llm",
                reasoning=overrides.get("narrative_notes", "LLM narrative advisor"),
            )
        )
        rule_config.pacing_profile = cast(PacingProfile, pacing)

    rule_config.evidence = new_evidence
    rule_config.requires_llm_fallback = False
    rule_config.meta_confidence = max(rule_config.meta_confidence, 0.6)

    log.info(
        "llm_fallback_applied",
        pacing=rule_config.pacing_profile,
        composer=rule_config.composer_strategy,
        coherence=rule_config.coherence_threshold,
    )
    return rule_config


__all__ = ["llm_narrative_advise"]
