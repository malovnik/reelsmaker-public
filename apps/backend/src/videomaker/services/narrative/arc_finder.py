"""Narrative Arc Finder — Phase 3 top-down pipeline.

Для каждой (Chapter, HookCandidate) пары находит естественную narrative arc:
hook → development → payoff. Длительность — следствие закрытия мысли,
не цель padding'а.

Research basis: docs/viral-clipper-research-2026-04-21.md
    EMNLP 2025 Industry: Opening/Ending selection — отдельный subtask.
    OpusClip 3.0: "clip_start = hook_start, clip_end = chapter-internal
    payoff" — и длительность есть следствие.

Модель: Gemini Flash (не Lite — narrative reasoning), fallback на Pro
если Flash возвращает null или low-quality arc (coherence < 0.5). Это
компромисс: 90% глав решаются через Flash, 10% тяжёлых требуют Pro.

Anti-confirmation: null — валидный ответ. Если LLM не нашёл сильный arc
в главе, он возвращает null и эта глава не даёт рилса. Ranker пропускает
пустые, использует другие главы. Honest null > жадный fabricated arc.

Entry point: ``find_arcs(chapters, hooks, transcript, *, settings,
llm_client=None, llm_client_pro=None, rate_limiter=None,
provider_override=None) -> list[NarrativeArc]``
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Literal, cast

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.models.narrative import (
    Chapter,
    ClosureType,
    HookCandidate,
    NarrativeArc,
)
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.narrative.constants import (
    ARC_COHERENCE_MIN,
    ARC_DEVELOPMENT_MAX_SENTENCES,
    REEL_MAX_DURATION_SEC,
    REEL_MIN_DURATION_SEC,
)
from videomaker.services.prompts import (
    NARRATIVE_ARC_FINDER_PROMPT,
    build_context_header,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter
from videomaker.services.transcribers.base import TranscriptResult

log = get_logger(__name__)

_ValidClosureType = Literal[
    "conclusion",
    "punchline",
    "revelation",
    "callback",
    "question",
    "emotional",
]
_VALID_CLOSURE_TYPES: frozenset[str] = frozenset(
    (
        "conclusion",
        "punchline",
        "revelation",
        "callback",
        "question",
        "emotional",
    )
)

#: Если coherence < этого порога после Flash — пробуем Pro fallback.
#: Research: Pro стабильнее на narrative reasoning для edge cases.
FLASH_RETRY_WITH_PRO_COHERENCE_THRESHOLD: float = 0.55

#: Если arc от LLM имеет duration вне [MIN, MAX] — reject полностью.
#: В отличие от bottom-up composer, мы не padding'ом исправляем, а ищем
#: другой arc (или null).
ARC_DURATION_MIN: float = REEL_MIN_DURATION_SEC
ARC_DURATION_MAX: float = REEL_MAX_DURATION_SEC


@dataclass(slots=True, frozen=True)
class _ArcRequest:
    """Одна пара (Chapter, HookCandidate) для обработки."""

    chapter: Chapter
    hook: HookCandidate
    transcript_slice_text: str


async def find_arcs(
    chapters: list[Chapter],
    hooks_per_chapter: dict[str, list[HookCandidate]],
    transcript: TranscriptResult,
    *,
    settings: Settings | None = None,
    llm_client: LLMClient | None = None,
    llm_client_pro: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    provider_override: str | None = None,
) -> list[NarrativeArc]:
    """Находит NarrativeArc для каждой пары (Chapter, top-hook).

    Берёт top-1 hook из каждой главы (сильнейший по score). Для глав
    без hook'ов пропускает. Возвращает список NarrativeArc в хронологическом
    порядке; главы без arc'а — не в результате.
    """

    requests = _build_requests(chapters, hooks_per_chapter, transcript)
    if not requests:
        log.info("arc_finder_no_requests")
        return []

    cfg = settings or get_settings()
    llm_flash = llm_client or build_llm_for_tier(
        "flash", cfg, provider_override=provider_override
    )
    llm_pro = llm_client_pro or build_llm_for_tier(
        "pro", cfg, provider_override=provider_override
    )
    limiter = rate_limiter or get_gemini_rate_limiter()

    tasks = [
        _find_arc_for_request(
            req,
            transcript=transcript,
            llm_flash=llm_flash,
            llm_pro=llm_pro,
            limiter=limiter,
        )
        for req in requests
    ]
    per_request_results = await asyncio.gather(*tasks, return_exceptions=True)

    arcs: list[NarrativeArc] = []
    flash_success = 0
    pro_fallback = 0
    null_returns = 0
    errors = 0

    for req, res in zip(requests, per_request_results, strict=True):
        if isinstance(res, BaseException):
            errors += 1
            log.warning(
                "arc_finder_request_failed",
                chapter_id=req.chapter.id,
                error=str(res),
            )
            continue
        arc, tier_used = res
        if arc is None:
            null_returns += 1
            continue
        if tier_used == "pro":
            pro_fallback += 1
        else:
            flash_success += 1
        arcs.append(arc)

    arcs.sort(key=lambda a: a.clip_start_sec)

    log.info(
        "arc_finder_done",
        requests=len(requests),
        arcs=len(arcs),
        flash_ok=flash_success,
        pro_fallback=pro_fallback,
        null_returns=null_returns,
        errors=errors,
    )
    return arcs


def _build_requests(
    chapters: list[Chapter],
    hooks_per_chapter: dict[str, list[HookCandidate]],
    transcript: TranscriptResult,
) -> list[_ArcRequest]:
    """Для каждой главы берёт top-1 hook (highest score). Пустые главы — skip."""

    by_id = {ch.id: ch for ch in chapters}
    requests: list[_ArcRequest] = []
    for ch_id, hooks in hooks_per_chapter.items():
        chapter = by_id.get(ch_id)
        if chapter is None:
            continue
        if not hooks:
            continue
        top_hook = max(hooks, key=lambda h: h.score)
        requests.append(
            _ArcRequest(
                chapter=chapter,
                hook=top_hook,
                transcript_slice_text=_slice_text(transcript, chapter),
            )
        )
    # Сортируем по положению в видео.
    requests.sort(key=lambda r: r.chapter.start_sec)
    return requests


async def _find_arc_for_request(
    req: _ArcRequest,
    *,
    transcript: TranscriptResult,
    llm_flash: LLMClient,
    llm_pro: LLMClient,
    limiter: RateLimiter,
) -> tuple[NarrativeArc | None, Literal["flash", "pro"]]:
    """Flash attempt; если null или coherence < порога — Pro retry.

    Возвращает ``(NarrativeArc | None, tier_used)``. Tier_used нужен
    для логирования и observability.
    """

    # Первый attempt через Flash.
    arc = await _invoke_llm_arc(
        req,
        transcript=transcript,
        llm=llm_flash,
        limiter=limiter,
        tier_name="flash",
    )

    if arc is not None and arc.coherence_score >= FLASH_RETRY_WITH_PRO_COHERENCE_THRESHOLD:
        return arc, "flash"

    # Flash не нашёл или низкий coherence — Pro retry.
    log.info(
        "arc_finder_pro_fallback",
        chapter_id=req.chapter.id,
        flash_arc_found=arc is not None,
        flash_coherence=round(arc.coherence_score, 2) if arc else None,
    )

    arc_pro = await _invoke_llm_arc(
        req,
        transcript=transcript,
        llm=llm_pro,
        limiter=limiter,
        tier_name="pro",
    )

    # Pro decisions приоритет. Если Pro тоже null — берём flash результат
    # (даже с низким coherence, если он прошёл duration sanity) или null.
    if arc_pro is not None:
        return arc_pro, "pro"
    return arc, "flash"


async def _invoke_llm_arc(
    req: _ArcRequest,
    *,
    transcript: TranscriptResult,
    llm: LLMClient,
    limiter: RateLimiter,
    tier_name: str,
) -> NarrativeArc | None:
    """Один LLM call. Возвращает NarrativeArc или None."""

    context_header = build_context_header(
        source_duration_sec=transcript.duration_sec,
        transcriber=transcript.transcriber,
        llm_model=llm.model,
        language=transcript.language,
    )
    system = f"{build_system_prompt()}\n\n{context_header}\n\n{NARRATIVE_ARC_FINDER_PROMPT}"
    user_payload = _build_user_payload(req)

    async with limiter.acquire():
        response = await llm.complete_json(
            system=system,
            user=user_payload,
            temperature=0.3,
            max_tokens=2000,
        )

    try:
        parsed = parse_json_response(response.text)
    except LLMError as exc:
        log.warning(
            "arc_finder_parse_failed",
            chapter_id=req.chapter.id,
            tier=tier_name,
            error=str(exc),
        )
        return None

    if not isinstance(parsed, dict):
        return None

    raw_arc = parsed.get("arc")
    if raw_arc is None:
        return None
    if not isinstance(raw_arc, dict):
        log.warning(
            "arc_finder_arc_not_dict",
            chapter_id=req.chapter.id,
            tier=tier_name,
            type=type(raw_arc).__name__,
        )
        return None

    return _parse_arc_dict(raw_arc, req)


def _build_user_payload(req: _ArcRequest) -> str:
    """Prompt с chapter meta + hook + transcript slice."""

    chapter = req.chapter
    hook = req.hook

    meta = {
        "chapter": {
            "chapter_id": chapter.id,
            "start_sec": round(chapter.start_sec, 2),
            "end_sec": round(chapter.end_sec, 2),
            "topic_label": chapter.topic_label,
            "key_claims": chapter.key_claims,
        },
        "hook": {
            "hook_start_sec": round(hook.hook_start_sec, 2),
            "hook_end_sec": round(hook.hook_end_sec, 2),
            "hook_text": hook.text,
            "hook_kind": hook.hook_kind,
            "hook_score": round(hook.score, 2),
        },
        "reel_duration_target_sec": {
            "min": ARC_DURATION_MIN,
            "max": ARC_DURATION_MAX,
        },
    }

    parts = [
        "Контекст (JSON):",
        json.dumps(meta, ensure_ascii=False, indent=2),
        "",
        "Транскрипт главы с timestamp'ами:",
        req.transcript_slice_text or "(пусто)",
        "",
        (
            "Найди narrative arc: hook → development → payoff. "
            f"Duration arc должна быть в [{ARC_DURATION_MIN}, {ARC_DURATION_MAX}]s. "
            "Если payoff не в главе — return {\"arc\": null}. "
            "Development 1-3 sentences цитаты из транскрипта. "
            "Payoff_text — полный sentence закрытия мысли."
        ),
    ]
    return "\n".join(parts)


def _slice_text(transcript: TranscriptResult, chapter: Chapter) -> str:
    """Текст транскрипта с timestamp'ами в диапазоне главы."""

    start, end = chapter.start_sec, chapter.end_sec
    if transcript.segments:
        parts: list[str] = []
        for seg in transcript.segments:
            if seg.end < start:
                continue
            if seg.start >= end:
                break
            text = (seg.text or "").strip()
            if not text:
                continue
            parts.append(f"[{_fmt_ts(seg.start)}] {text}")
        return "\n".join(parts)

    if transcript.words:
        tokens: list[str] = []
        for w in transcript.words:
            if w.end < start:
                continue
            if w.start >= end:
                break
            token = (w.word or "").strip()
            if token:
                tokens.append(token)
        return " ".join(tokens)

    return ""


def _parse_arc_dict(
    raw: dict[str, object],
    req: _ArcRequest,
) -> NarrativeArc | None:
    """Строит NarrativeArc из LLM output. None если не проходит валидацию."""

    clip_start_raw = raw.get("clip_start_sec")
    clip_end_raw = raw.get("clip_end_sec")
    if not isinstance(clip_start_raw, (int, float)):
        return None
    if not isinstance(clip_end_raw, (int, float)):
        return None

    clip_start = float(clip_start_raw)
    clip_end = float(clip_end_raw)

    # Clamp к границам главы.
    ch = req.chapter
    clip_start = max(ch.start_sec, clip_start)
    clip_end = min(ch.end_sec, clip_end)

    if clip_end <= clip_start:
        return None

    duration = clip_end - clip_start
    if duration < ARC_DURATION_MIN or duration > ARC_DURATION_MAX:
        log.debug(
            "arc_finder_duration_out_of_range",
            chapter_id=ch.id,
            duration=round(duration, 1),
            min_dur=ARC_DURATION_MIN,
            max_dur=ARC_DURATION_MAX,
        )
        return None

    closure_type_raw = str(raw.get("closure_type") or "").strip().lower()
    if closure_type_raw not in _VALID_CLOSURE_TYPES:
        log.debug(
            "arc_finder_invalid_closure_type",
            chapter_id=ch.id,
            got=closure_type_raw,
        )
        return None
    closure_type = cast(ClosureType, _coerce_closure_type(closure_type_raw))

    coherence_score = _clamp_float(
        raw.get("coherence_score"), 0.0, 1.0, default=0.5
    )
    if coherence_score < ARC_COHERENCE_MIN:
        log.debug(
            "arc_finder_low_coherence",
            chapter_id=ch.id,
            coherence=round(coherence_score, 2),
        )
        return None

    arc_score = _clamp_float(raw.get("arc_score"), 0.0, 1.0, default=0.5)

    payoff_text = str(raw.get("payoff_text") or "").strip()
    if not payoff_text:
        return None
    payoff_text = payoff_text[:250]

    raw_development = raw.get("development_sentences")
    development: list[str] = []
    if isinstance(raw_development, list):
        for item in raw_development:
            if not isinstance(item, str):
                continue
            cleaned = item.strip()
            if cleaned:
                development.append(cleaned[:300])
            if len(development) >= ARC_DEVELOPMENT_MAX_SENTENCES:
                break

    # Hook может иметь updated_start от LLM (breath prepend). Если
    # clip_start отличается от hook.hook_start_sec — обновляем hook внутри
    # arc (но не меняем исходный HookCandidate).
    hook_for_arc = req.hook
    if abs(clip_start - hook_for_arc.hook_start_sec) > 0.1:
        # Сдвиг не больше 3s назад (prompt constraint).
        new_hook_start = max(ch.start_sec, min(hook_for_arc.hook_start_sec, clip_start))
        new_hook_end = min(ch.end_sec, max(new_hook_start + 0.5, hook_for_arc.hook_end_sec))
        hook_for_arc = HookCandidate(
            chapter_id=hook_for_arc.chapter_id,
            hook_start_sec=new_hook_start,
            hook_end_sec=new_hook_end,
            text=hook_for_arc.text,
            score=hook_for_arc.score,
            why=hook_for_arc.why,
            hook_kind=hook_for_arc.hook_kind,
        )

    return NarrativeArc(
        chapter_id=ch.id,
        hook=hook_for_arc,
        clip_start_sec=clip_start,
        clip_end_sec=clip_end,
        closure_type=closure_type,
        development_sentences=development,
        payoff_text=payoff_text,
        coherence_score=coherence_score,
        arc_score=arc_score,
    )


# ─── Utilities ────────────────────────────────────────────────────────────


def _coerce_closure_type(value: str) -> _ValidClosureType:
    if value == "conclusion":
        return "conclusion"
    if value == "punchline":
        return "punchline"
    if value == "revelation":
        return "revelation"
    if value == "callback":
        return "callback"
    if value == "question":
        return "question"
    if value == "emotional":
        return "emotional"
    return "conclusion"


def _clamp_float(
    value: object,
    lo: float,
    hi: float,
    *,
    default: float,
) -> float:
    if isinstance(value, (int, float)):
        return max(lo, min(hi, float(value)))
    return default


def _fmt_ts(sec: float) -> str:
    total = max(0, int(sec))
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"


__all__ = ["find_arcs"]
