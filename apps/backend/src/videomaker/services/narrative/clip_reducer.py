"""Clip Reducer — Phase 8 Stage 4 (REDUCE phase).

Принимает raw candidates от chunk_scorer (MAP phase), применяет:
1. Deterministic dedup (temporal overlap + Jaccard lemmatized)
2. Single Gemini Pro LLM call для качественной curation (diversity,
   completeness, narrative balance)
3. Ranking финального пакета

Research basis: docs/opusclip-2026-research.md Section 5.4 + 2.4
    Collapse-before-reduce pattern (LLM×MapReduce ACL 2025) критичен:
    не передавать 180 candidates в reducer, сперва top-K per chunk.
    Temporal + Jaccard dedup до LLM — economy + precision.

Target count определяется через density × duration (1 clip / ~2 min),
конфигурируется runtime_settings (narrative_clips_per_chunk_target × chunks).

Entry: ``reduce_and_rank(candidates, global_context, transcript, *,
target_count, settings=None, llm_client=None, rate_limiter=None,
provider_override=None) -> list[RawClipCandidate]``

Graceful degradation:
    - LLM fail → fallback score-based sorting (deterministic)
    - Parse fail → same
"""

from __future__ import annotations

import json
import re
from typing import Any

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.narrative.chunk_scorer import GlobalContext, RawClipCandidate
from videomaker.services.prompts import (
    CLIP_REDUCER_PROMPT,
    build_context_header,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter
from videomaker.services.transcribers.base import TranscriptResult

log = get_logger(__name__)

#: Temporal overlap threshold — если два clips пересекаются >40% short'а,
#: считаем дубликатом (одна из overlap zones между chunks).
_TEMPORAL_OVERLAP_THRESHOLD: float = 0.4

#: Jaccard similarity threshold на word tokens (без lemmatization, lowercase).
#: Research recommended 0.85 — только near-duplicate, не topic similarity.
_JACCARD_THRESHOLD: float = 0.85

#: Максимум candidates передаваемых в LLM reducer. Cost/quality trade-off.
#: OpusClip research: top-5 per chunk × 12 chunks = 60 candidates — sweet spot.
_MAX_LLM_CANDIDATES: int = 80

#: Top-K per chunk при collapse-before-reduce.
_TOP_K_PER_CHUNK: int = 7


async def reduce_and_rank(
    candidates: list[RawClipCandidate],
    global_context: GlobalContext,
    transcript: TranscriptResult,
    *,
    target_count: int,
    settings: Settings | None = None,
    llm_client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    provider_override: str | None = None,
) -> list[RawClipCandidate]:
    """REDUCE phase entry.

    Returns финальный ranked список RawClipCandidate (reorder'енный и
    отфильтрованный). Длина ≤ target_count.
    """

    if not candidates:
        log.info("clip_reducer_empty_input")
        return []

    cfg = settings or get_settings()

    # Step 1: Deterministic temporal dedup (fast, cheap, precise).
    after_temporal = _temporal_dedup(candidates)
    temporal_dropped = len(candidates) - len(after_temporal)

    # Step 2: Jaccard dedup (catches semantically near-identical).
    after_jaccard = _jaccard_dedup(after_temporal)
    jaccard_dropped = len(after_temporal) - len(after_jaccard)

    # Step 3: Collapse — keep top-K per chunk for LLM economy.
    after_collapse = _collapse_top_k(after_jaccard, top_k=_TOP_K_PER_CHUNK)

    # Step 4: Hard cap — если даже после collapse > _MAX_LLM_CANDIDATES,
    # берём top по score globally.
    if len(after_collapse) > _MAX_LLM_CANDIDATES:
        after_collapse = sorted(after_collapse, key=lambda c: c.score, reverse=True)[
            :_MAX_LLM_CANDIDATES
        ]

    log.info(
        "clip_reducer_preprocessed",
        input=len(candidates),
        after_temporal=len(after_temporal),
        after_jaccard=len(after_jaccard),
        after_collapse=len(after_collapse),
        temporal_dropped=temporal_dropped,
        jaccard_dropped=jaccard_dropped,
        target_count=target_count,
    )

    # Step 5: LLM-based curation. Fallback на deterministic если LLM fails.
    try:
        ranked = await _llm_curate(
            after_collapse,
            global_context,
            transcript,
            target_count=target_count,
            settings=cfg,
            llm_client=llm_client,
            rate_limiter=rate_limiter,
            provider_override=provider_override,
        )
    except Exception as exc:
        log.warning(
            "clip_reducer_llm_failed_fallback_deterministic",
            error=str(exc),
        )
        ranked = _deterministic_rank(after_collapse, target_count=target_count)

    log.info(
        "clip_reducer_done",
        final_count=len(ranked),
        target_count=target_count,
    )
    return ranked


# ─── Step 1: Temporal dedup ───────────────────────────────────────────────


def _temporal_dedup(candidates: list[RawClipCandidate]) -> list[RawClipCandidate]:
    """Удаляет clips с >40% временным пересечением, keep higher score."""

    if len(candidates) <= 1:
        return list(candidates)

    sorted_by_score = sorted(candidates, key=lambda c: c.score, reverse=True)
    kept: list[RawClipCandidate] = []

    for cand in sorted_by_score:
        dup = False
        for accepted in kept:
            overlap = _temporal_overlap_ratio(cand, accepted)
            if overlap > _TEMPORAL_OVERLAP_THRESHOLD:
                dup = True
                break
        if not dup:
            kept.append(cand)

    return sorted(kept, key=lambda c: c.start_sec)


def _temporal_overlap_ratio(
    a: RawClipCandidate,
    b: RawClipCandidate,
) -> float:
    """Overlap / shorter_duration. 0-1."""

    overlap_start = max(a.start_sec, b.start_sec)
    overlap_end = min(a.end_sec, b.end_sec)
    overlap = max(0.0, overlap_end - overlap_start)
    if overlap <= 0:
        return 0.0
    shorter = min(a.duration_sec(), b.duration_sec())
    if shorter <= 0:
        return 0.0
    return overlap / shorter


# ─── Step 2: Jaccard dedup ────────────────────────────────────────────────


_WORD_RE = re.compile(r"[a-zа-яёА-ЯЁ0-9]+", re.IGNORECASE)


def _jaccard_dedup(candidates: list[RawClipCandidate]) -> list[RawClipCandidate]:
    """Удаляет semantically near-identical clips by token Jaccard."""

    if len(candidates) <= 1:
        return list(candidates)

    sorted_by_score = sorted(candidates, key=lambda c: c.score, reverse=True)
    kept: list[tuple[RawClipCandidate, set[str]]] = []

    for cand in sorted_by_score:
        tokens = _tokenize_clip(cand)
        if not tokens:
            kept.append((cand, tokens))
            continue
        dup = False
        for _accepted, accepted_tokens in kept:
            if not accepted_tokens:
                continue
            sim = _jaccard(tokens, accepted_tokens)
            if sim > _JACCARD_THRESHOLD:
                dup = True
                break
        if not dup:
            kept.append((cand, tokens))

    return sorted([c for c, _ in kept], key=lambda c: c.start_sec)


def _tokenize_clip(cand: RawClipCandidate) -> set[str]:
    """Lowercase tokens из hook+payoff, минимальная длина 3."""

    text = f"{cand.hook} {cand.payoff}".lower()
    return {w for w in _WORD_RE.findall(text) if len(w) >= 3}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    return intersection / union


# ─── Step 3: Collapse top-K per chunk ─────────────────────────────────────


def _collapse_top_k(
    candidates: list[RawClipCandidate],
    *,
    top_k: int,
) -> list[RawClipCandidate]:
    """Keeps top-K candidates per chunk_index by score."""

    if top_k <= 0:
        return list(candidates)

    by_chunk: dict[int, list[RawClipCandidate]] = {}
    for c in candidates:
        by_chunk.setdefault(c.chunk_index, []).append(c)

    collapsed: list[RawClipCandidate] = []
    for chunk_idx, chunk_cands in by_chunk.items():
        del chunk_idx
        sorted_chunk = sorted(chunk_cands, key=lambda c: c.score, reverse=True)
        collapsed.extend(sorted_chunk[:top_k])

    return sorted(collapsed, key=lambda c: c.start_sec)


# ─── Step 4: LLM curation ─────────────────────────────────────────────────


async def _llm_curate(
    candidates: list[RawClipCandidate],
    global_context: GlobalContext,
    transcript: TranscriptResult,
    *,
    target_count: int,
    settings: Settings,
    llm_client: LLMClient | None,
    rate_limiter: RateLimiter | None,
    provider_override: str | None,
) -> list[RawClipCandidate]:
    """Single LLM call → selected + ranked list.

    Использует Pro tier (не Lite) — reducer делает качественные judgments
    diversity + completeness + narrative balance. Одна call на видео, не
    bottleneck по cost.
    """

    # Используем Pro для качественного reducer'а (один вызов на видео).
    llm = llm_client or build_llm_for_tier(
        "pro", settings, provider_override=provider_override
    )
    limiter = rate_limiter or get_gemini_rate_limiter()

    # Присваиваем stable clip_id для LLM attribution.
    indexed = list(enumerate(candidates))
    clip_id_map: dict[str, RawClipCandidate] = {}
    for idx, cand in indexed:
        clip_id = f"c_{idx + 1:03d}"
        clip_id_map[clip_id] = cand

    context_header = build_context_header(
        source_duration_sec=transcript.duration_sec,
        transcriber=transcript.transcriber,
        llm_model=llm.model,
        language=global_context.language,
    )
    system = f"{build_system_prompt()}\n\n{context_header}\n\n{CLIP_REDUCER_PROMPT}"

    user_payload = _build_reducer_payload(
        indexed_candidates=[
            (clip_id, cand)
            for clip_id, cand in zip(clip_id_map.keys(), candidates, strict=True)
        ],
        global_context=global_context,
        target_count=target_count,
    )

    response_schema = _build_reducer_schema()

    async with limiter.acquire():
        response = await llm.complete_json(
            system=system,
            user=user_payload,
            temperature=0.2,
            max_tokens=6000,
            response_schema=response_schema,
        )

    parsed = parse_json_response(response.text)
    if not isinstance(parsed, dict):
        raise LLMError(
            f"clip_reducer LLM returned {type(parsed).__name__}, expected dict"
        )

    raw_selected = parsed.get("selected")
    if not isinstance(raw_selected, list):
        raise LLMError("clip_reducer LLM 'selected' is not a list")

    ranked_with_rank: list[tuple[int, RawClipCandidate]] = []
    for item in raw_selected:
        if not isinstance(item, dict):
            continue
        clip_id = str(item.get("clip_id") or "").strip()
        if clip_id not in clip_id_map:
            log.debug("clip_reducer_unknown_clip_id", clip_id=clip_id)
            continue
        rank_raw = item.get("rank")
        rank = int(rank_raw) if isinstance(rank_raw, (int, float)) else len(ranked_with_rank) + 1
        ranked_with_rank.append((rank, clip_id_map[clip_id]))
        if len(ranked_with_rank) >= target_count:
            break

    ranked_with_rank.sort(key=lambda t: t[0])
    return [cand for _, cand in ranked_with_rank]


def _build_reducer_payload(
    *,
    indexed_candidates: list[tuple[str, RawClipCandidate]],
    global_context: GlobalContext,
    target_count: int,
) -> str:
    """Собирает user prompt для reducer'а."""

    candidates_json = []
    for clip_id, cand in indexed_candidates:
        candidates_json.append(
            {
                "clip_id": clip_id,
                "start_sec": round(cand.start_sec, 1),
                "end_sec": round(cand.end_sec, 1),
                "duration_sec": round(cand.duration_sec(), 1),
                "hook": cand.hook,
                "payoff": cand.payoff,
                "topic": cand.topic,
                "score": cand.score,
                "hook_kind": cand.hook_kind,
                "closure_type": cand.closure_type,
            }
        )

    parts = [
        global_context.to_context_block(),
        "",
        "=== TARGET ===",
        f"Нужно отобрать до {target_count} финальных clips из {len(indexed_candidates)} candidates.",
        "",
        "=== CANDIDATES (JSON) ===",
        json.dumps(candidates_json, ensure_ascii=False, indent=2),
        "",
        (
            "Верни {selected: [...]} по OUTPUT SCHEMA. Помни: score ≥ 7 hard "
            "floor (second pass ≥ 6 если нужно дозаполнить до TARGET). "
            "Diversity: ≤ 2 clips per topic. Ranking: 1 = top."
        ),
    ]
    return "\n".join(parts)


def _build_reducer_schema() -> dict[str, Any]:
    """JSON schema for reducer response."""

    return {
        "type": "OBJECT",
        "properties": {
            "selected": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "clip_id": {"type": "STRING"},
                        "rank": {"type": "INTEGER"},
                        "selection_reason": {"type": "STRING"},
                    },
                    "required": ["clip_id", "rank"],
                },
            }
        },
        "required": ["selected"],
    }


# ─── Fallback: deterministic rank ─────────────────────────────────────────


def _deterministic_rank(
    candidates: list[RawClipCandidate],
    *,
    target_count: int,
) -> list[RawClipCandidate]:
    """Fallback когда LLM недоступен.

    Sort by score desc, apply topic diversity (max 2 per topic),
    return top target_count. Deterministic, cheap.
    """

    if not candidates:
        return []

    sorted_by_score = sorted(candidates, key=lambda c: c.score, reverse=True)

    topic_count: dict[str, int] = {}
    selected: list[RawClipCandidate] = []

    # First pass: strict max 2 per topic, score ≥ 7.
    for cand in sorted_by_score:
        if len(selected) >= target_count:
            break
        if cand.score < 7:
            continue
        topic_key = cand.topic.lower().strip()[:50]
        if topic_count.get(topic_key, 0) >= 2:
            continue
        selected.append(cand)
        topic_count[topic_key] = topic_count.get(topic_key, 0) + 1

    # Second pass: fill to target если есть место.
    if len(selected) < target_count:
        selected_ids = {id(c) for c in selected}
        for cand in sorted_by_score:
            if len(selected) >= target_count:
                break
            if id(cand) in selected_ids:
                continue
            if cand.score < 6:
                continue
            topic_key = cand.topic.lower().strip()[:50]
            if topic_count.get(topic_key, 0) >= 3:
                continue
            selected.append(cand)
            topic_count[topic_key] = topic_count.get(topic_key, 0) + 1

    return selected


__all__ = ["reduce_and_rank"]
