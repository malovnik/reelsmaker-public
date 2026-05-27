"""Kartoziya Stage 5.6 — Rhythm Check (middle-sag detection).

Вход: готовый StoryScript (3-act arc с segments + emotional beats).
Выход: RhythmReport — issues + рекомендации (insert_cutaway / swap / shorten).

Двухуровневая логика:
1. **LLM (Flash)** — умный анализ с учётом beats, speakers, темпа.
2. **Heuristic fallback** — если LLM упал, детектим 3+ подряд длинных
   segment'ов одного speaker'а как "монотонность".
"""

from __future__ import annotations

from contextlib import suppress

from videomaker.core.config import get_settings
from videomaker.core.logging import get_logger
from videomaker.models.story_script import (
    RhythmIssue,
    RhythmReport,
    StoryScript,
)
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.prompts import (
    RHYTHM_CHECK_PROMPT,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter

log = get_logger(__name__)

VALID_SEVERITIES = {"low", "medium", "high"}
VALID_ACTIONS = {"insert_cutaway", "swap_segment", "shorten", "none"}
VALID_PACING = {"рваный", "ровный", "монотонный"}


async def check_rhythm(
    script: StoryScript,
    *,
    client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    pipeline_provider: str | None = None,
) -> RhythmReport:
    """LLM + fallback на heuristic при ошибке."""
    if not script.arc:
        return RhythmReport(overall_rhythm_score=1.0, pacing_summary="ровный")

    cfg = get_settings()
    llm = client or build_llm_for_tier("flash", cfg, provider_override=pipeline_provider)
    limiter = rate_limiter or get_gemini_rate_limiter()

    user_payload = _render_script_for_llm(script)
    system = f"{build_system_prompt()}\n\n{RHYTHM_CHECK_PROMPT}"

    async with limiter.acquire():
        try:
            response = await llm.complete_json(
                system=system,
                user=user_payload,
                temperature=0.2,
                max_tokens=6000,
            )
            parsed = parse_json_response(response.text)
        except LLMError as exc:
            log.warning("rhythm_check_failed", error=str(exc))
            return _heuristic_rhythm_report(script)

    if not isinstance(parsed, dict):
        return _heuristic_rhythm_report(script)

    return _parse_rhythm_report(parsed)


def _render_script_for_llm(script: StoryScript) -> str:
    lines = [f"Central theme: {script.central_theme}", "", "=== ARC ==="]
    for i, seg in enumerate(script.arc):
        speaker = f" speaker={seg.speaker}" if seg.speaker else ""
        beat = f" beat={seg.emotional_beat}" if seg.emotional_beat != "neutral" else ""
        lines.append(
            f"[{i}] role={seg.role} duration={seg.duration_sec:.1f}s"
            f"{speaker}{beat}\n"
            f"  evidence_id={seg.evidence_id}\n"
            f"  reasoning: {seg.reasoning[:150]}"
        )
    return "\n".join(lines)


def _parse_rhythm_report(data: dict) -> RhythmReport:
    issues: list[RhythmIssue] = []
    for raw in data.get("issues") or []:
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get("severity", "low")).lower()
        if severity not in VALID_SEVERITIES:
            severity = "low"

        rec = raw.get("recommendation") or {}
        action = "none"
        if isinstance(rec, dict):
            raw_action = str(rec.get("action", "none")).lower()
            if raw_action in VALID_ACTIONS:
                action = raw_action

        target_pos = None
        if isinstance(rec, dict) and "target_position_in_arc" in rec:
            with suppress(TypeError, ValueError):
                target_pos = int(rec["target_position_in_arc"])

        issues.append(
            RhythmIssue(
                region=str(raw.get("region", "")).strip(),
                severity=severity,  # type: ignore[arg-type]
                reason=str(raw.get("reason", "")).strip(),
                recommendation_action=action,  # type: ignore[arg-type]
                target_position_in_arc=target_pos,
                alternate_evidence_id=(
                    str(rec.get("alternate_evidence_id"))
                    if isinstance(rec, dict) and rec.get("alternate_evidence_id")
                    else None
                ),
                recommendation_reasoning=(
                    str(rec.get("reasoning", "")).strip() if isinstance(rec, dict) else ""
                ),
            )
        )

    try:
        score = max(0.0, min(1.0, float(data.get("overall_rhythm_score", 0.8))))
    except (TypeError, ValueError):
        score = 0.8

    pacing = str(data.get("pacing_summary", "ровный"))
    if pacing not in VALID_PACING:
        pacing = "ровный"

    return RhythmReport(
        middle_sag_detected=bool(data.get("middle_sag_detected", False)),
        issues=issues,
        overall_rhythm_score=score,
        pacing_summary=pacing,  # type: ignore[arg-type]
    )


def _heuristic_rhythm_report(script: StoryScript) -> RhythmReport:
    """Без LLM: 3+ подряд segments >30s одного speaker'а = монотонность."""
    issues: list[RhythmIssue] = []
    arc = script.arc
    consecutive_long = 0
    prev_speaker = None
    run_start = 0

    for i, seg in enumerate(arc):
        same_speaker = bool(seg.speaker and seg.speaker == prev_speaker)
        is_long = seg.duration_sec > 30.0

        if same_speaker and is_long:
            consecutive_long += 1
        else:
            if consecutive_long >= 3:
                issues.append(
                    RhythmIssue(
                        region=f"segments {run_start}-{i - 1}",
                        severity="medium",
                        reason=(
                            f"{consecutive_long + 1} подряд длинных segments "
                            f"одного speaker'а — монотонность"
                        ),
                        recommendation_action="insert_cutaway",
                        target_position_in_arc=run_start + 1,
                    )
                )
            consecutive_long = 0
            run_start = i
        prev_speaker = seg.speaker

    if consecutive_long >= 3:
        issues.append(
            RhythmIssue(
                region=f"segments {run_start}-{len(arc) - 1}",
                severity="medium",
                reason=(
                    f"{consecutive_long + 1} подряд длинных segments "
                    f"одного speaker'а — монотонность"
                ),
                recommendation_action="insert_cutaway",
                target_position_in_arc=run_start + 1,
            )
        )

    score = 1.0 - (len(issues) * 0.15)
    return RhythmReport(
        middle_sag_detected=bool(issues),
        issues=issues,
        overall_rhythm_score=max(0.0, score),
        pacing_summary="монотонный" if issues else "ровный",
    )
