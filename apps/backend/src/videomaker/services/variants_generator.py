"""Kartoziya Stage 5.7 — Variants Generator (4 финальных варианта story-script).

Вход: Canvas + RankedEvidence + base StoryScript (после rhythm check).
Выход: StoryVariants с 4 форматами нарезки:
- `long_philosophical` — 7-12 segments, 10-20 мин, глубокое погружение.
- `package_of_shorts` — 3-7 мини-историй, каждая 90-180s (основа для рилсов).
- `punchy_summary` — 3-5 segments, 60-120s, тизер-формат.
- `deep_dive` — 8-15 segments, 20-40 мин, полный эссе-разбор.

При LLM-сбое fallback'ит на единый `long_philosophical` с копией base arc.
Видеомейкер преимущественно использует `package_of_shorts` для нарезки рилсов
— это будет делаться в Reels Composer (STEP 7).
"""

from __future__ import annotations

from videomaker.core.config import get_settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import RankedEvidence
from videomaker.models.story_script import (
    StoryScript,
    StorySegment,
    StoryVariant,
    StoryVariants,
    VariantKind,
)
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.prompts import (
    VARIANTS_GENERATOR_PROMPT,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter

log = get_logger(__name__)

VALID_VARIANT_KINDS = {
    "long_philosophical", "package_of_shorts", "punchy_summary", "deep_dive",
}
VALID_ROLES = {"hook", "setup", "development", "peak", "payoff"}


async def generate_variants(
    canvas: ProjectCanvas,
    ranked: RankedEvidence,
    base_script: StoryScript,
    *,
    client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    pipeline_provider: str | None = None,
) -> StoryVariants:
    """Pro один вызов, парсит до 4 вариантов из output'а."""
    if not ranked.items:
        return StoryVariants()

    cfg = get_settings()
    llm = client or build_llm_for_tier("pro", cfg, provider_override=pipeline_provider)
    limiter = rate_limiter or get_gemini_rate_limiter()

    user_payload = _render_input(ranked, base_script)
    system = (
        f"{build_system_prompt()}\n\n{canvas.to_llm_context()}\n\n"
        f"{VARIANTS_GENERATOR_PROMPT}"
    )

    async with limiter.acquire():
        try:
            response = await llm.complete_json(
                system=system, user=user_payload,
                temperature=0.6, max_tokens=12000,
            )
            parsed = parse_json_response(response.text)
        except LLMError as exc:
            log.warning("variants_generator_failed", error=str(exc))
            return _fallback_variants(base_script)

    if not isinstance(parsed, dict):
        return _fallback_variants(base_script)

    return _parse_variants_output(parsed, ranked)


def _render_input(
    ranked: RankedEvidence,
    base: StoryScript,
) -> str:
    parts: list[str] = [
        "=== BASE STORY SCRIPT ===",
        f"Central theme: {base.central_theme}",
        f"Duration: {base.predicted_duration_sec:.0f}s",
        f"Bookend motif: {base.bookend_motif_id or '-'}",
        "",
        "Arc:",
    ]
    for seg in base.arc:
        parts.append(
            f"  [{seg.role}] "
            f"{seg.source_start_sec:.1f}-{seg.source_end_sec:.1f}s "
            f"speaker={seg.speaker} evidence={seg.evidence_id}"
        )
    parts.append("\n=== RANKED EVIDENCE POOL ===")
    for item in ranked.items:
        parts.append(
            f"[{item.id}] {item.category} score={item.composite_score:.2f} "
            f"{item.start:.1f}-{item.end:.1f}s: {item.text[:150]}"
        )
    return "\n".join(parts)


def _parse_variants_output(
    data: dict, ranked: RankedEvidence,
) -> StoryVariants:
    evidence_map = {e.id: e for e in ranked.items}
    variants: list[StoryVariant] = []

    for raw in data.get("variants") or []:
        if not isinstance(raw, dict):
            continue

        kind = str(raw.get("kind") or raw.get("id") or "").lower()
        # "variant_long_philosophical" → "long_philosophical"
        if kind.startswith("variant_"):
            kind = kind[len("variant_"):]
        if kind not in VALID_VARIANT_KINDS:
            continue

        arc_items: list[StorySegment] = []
        for seg_raw in raw.get("arc") or []:
            if not isinstance(seg_raw, dict):
                continue
            role = str(seg_raw.get("role", "")).lower()
            if role not in VALID_ROLES:
                continue

            evidence_id = seg_raw.get("evidence_id")
            evidence = (
                evidence_map.get(str(evidence_id)) if evidence_id else None
            )
            try:
                start = float(seg_raw.get(
                    "source_start_sec", evidence.start if evidence else 0.0,
                ))
                end = float(seg_raw.get(
                    "source_end_sec",
                    evidence.end if evidence else start + 1.0,
                ))
            except (TypeError, ValueError):
                continue
            if end <= start:
                continue

            arc_items.append(
                StorySegment(
                    role=role,  # type: ignore[arg-type]
                    evidence_id=str(evidence_id or ""),
                    source_start_sec=max(0.0, start),
                    source_end_sec=max(start, end),
                    speaker=(
                        seg_raw.get("speaker")
                        or (evidence.speaker if evidence else None)
                    ),
                    reasoning=str(seg_raw.get("reasoning", "")).strip(),
                    text_preview=(evidence.text[:200] if evidence else ""),
                )
            )

        if not arc_items:
            continue

        try:
            target = float(raw.get("target_duration_sec", 0.0))
            predicted = float(raw.get(
                "predicted_duration_sec",
                sum(s.duration_sec for s in arc_items),
            ))
        except (TypeError, ValueError):
            target = sum(s.duration_sec for s in arc_items)
            predicted = target

        variants.append(
            StoryVariant(
                id=f"variant_{kind}",
                kind=kind,  # type: ignore[arg-type]
                label=str(raw.get("label", kind.replace("_", " "))),
                target_duration_sec=max(0.0, target),
                predicted_duration_sec=max(0.0, predicted),
                central_theme=str(raw.get("central_theme", "")).strip(),
                arc=arc_items,
            )
        )

    return StoryVariants(variants=variants)


def _fallback_variants(base: StoryScript) -> StoryVariants:
    """Если Pro упал — возвращаем один long_philosophical копией base arc."""
    if not base.arc:
        return StoryVariants()
    kind: VariantKind = "long_philosophical"
    return StoryVariants(variants=[
        StoryVariant(
            id=f"variant_{kind}",
            kind=kind,
            label="Длинное философское (fallback)",
            target_duration_sec=base.predicted_duration_sec,
            predicted_duration_sec=base.predicted_duration_sec,
            central_theme=base.central_theme,
            arc=list(base.arc),
        ),
    ])
