"""Global Context Builder — Phase 8 Stage 3.

Один Gemini Flash Lite call на всё видео. Вход — first 15K + last 5K
chars транскрипта (middle опционально опускается для экономии токенов).
Выход — GlobalContext (central_theme, key_topics, speaker_role, structure,
tone) для инжекции в каждый chunk_scorer call.

Research basis: docs/opusclip-2026-research.md Section 5.1
    Global context нужен чтобы chunk scorers не re-discovered те же "obvious"
    моменты и могли фильтровать candidates по релевантности central_theme.

Graceful degradation:
    - LLM fail → возвращаем GlobalContext с defaults
      (central_theme='', key_topics=[], language='ru')
    - Parse fail → same

Entry: ``build_global_context(transcript, *, settings, llm_client=None,
rate_limiter=None, provider_override=None) -> GlobalContext``
"""

from __future__ import annotations

from typing import Any

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm_for_tier,
    parse_json_response,
)
from videomaker.services.narrative.chunk_scorer import GlobalContext
from videomaker.services.prompts import (
    GLOBAL_CONTEXT_BUILDER_PROMPT,
    build_context_header,
    build_system_prompt,
)
from videomaker.services.rate_limiter import RateLimiter, get_gemini_rate_limiter
from videomaker.services.transcribers.base import TranscriptResult

log = get_logger(__name__)

#: Размер first section для LLM context extraction.
#: 15K chars ≈ 15 минут talking-head контента. Достаточно для понимания
#: opening thesis + speaker setup.
_FIRST_SECTION_CHARS: int = 15_000

#: Размер last section. 5K chars ≈ 5 минут финала.
#: Финал обычно содержит key takeaways и подтверждение central_theme.
_LAST_SECTION_CHARS: int = 5_000

#: Middle section size threshold. Если транскрипт < этого, передаём
#: целиком без обрезки middle.
_FULL_TRANSCRIPT_THRESHOLD: int = 25_000


async def build_global_context(
    transcript: TranscriptResult,
    *,
    settings: Settings | None = None,
    llm_client: LLMClient | None = None,
    rate_limiter: RateLimiter | None = None,
    provider_override: str | None = None,
) -> GlobalContext:
    """Строит GlobalContext одним LLM call.

    Возвращает GlobalContext (может быть minimal на LLM fail, но никогда не
    падает — downstream chunk_scorer работает и на пустом context'е).
    """

    cfg = settings or get_settings()

    full_text = _render_transcript_text(transcript)
    if not full_text:
        log.warning("global_context_empty_transcript")
        return _empty_context(transcript)

    llm = llm_client or build_llm_for_tier(
        "flash_lite", cfg, provider_override=provider_override
    )
    limiter = rate_limiter or get_gemini_rate_limiter()

    first_section, last_section, middle_omitted = _extract_sections(full_text)

    context_header = build_context_header(
        source_duration_sec=transcript.duration_sec,
        transcriber=transcript.transcriber,
        llm_model=llm.model,
        language=transcript.language or "ru",
    )
    system = (
        f"{build_system_prompt()}\n\n"
        f"{context_header}\n\n{GLOBAL_CONTEXT_BUILDER_PROMPT}"
    )

    user_payload = _build_user_payload(
        first_section=first_section,
        last_section=last_section,
        middle_omitted=middle_omitted,
        duration_sec=transcript.duration_sec,
    )

    response_schema = _build_response_schema()

    try:
        async with limiter.acquire():
            response = await llm.complete_json(
                system=system,
                user=user_payload,
                temperature=0.25,
                max_tokens=2000,
                response_schema=response_schema,
            )
    except Exception as exc:
        log.warning("global_context_llm_failed", error=str(exc))
        return _empty_context(transcript)

    try:
        parsed = parse_json_response(response.text)
    except LLMError as exc:
        log.warning("global_context_parse_failed", error=str(exc))
        return _empty_context(transcript)

    if not isinstance(parsed, dict):
        log.warning(
            "global_context_bad_shape", type=type(parsed).__name__
        )
        return _empty_context(transcript)

    ctx = _parse_context_dict(parsed, transcript)
    log.info(
        "global_context_built",
        central_theme_len=len(ctx.central_theme),
        key_topics_count=len(ctx.key_topics),
        speaker_role_len=len(ctx.speaker_role),
        middle_omitted=middle_omitted,
    )
    return ctx


# ─── Section extraction ──────────────────────────────────────────────────


def _render_transcript_text(transcript: TranscriptResult) -> str:
    """Собирает полный timestamped текст транскрипта."""

    segments = transcript.segments
    if not segments and transcript.words:
        from videomaker.services.transcribers.base import merge_words_into_segments

        segments = merge_words_into_segments(transcript.words)
    if not segments:
        return ""

    parts: list[str] = []
    for seg in segments:
        text = (seg.text or "").strip()
        if text:
            parts.append(f"[{_fmt_ts(seg.start)}] {text}")
    return "\n".join(parts)


def _extract_sections(full_text: str) -> tuple[str, str, bool]:
    """Возвращает (first_section, last_section, middle_omitted).

    Если full_text ≤ _FULL_TRANSCRIPT_THRESHOLD — first = весь, last = пустой,
    middle_omitted = False (экономия LLM call — middle всё-равно в first).
    """

    if len(full_text) <= _FULL_TRANSCRIPT_THRESHOLD:
        return full_text, "", False

    first = full_text[:_FIRST_SECTION_CHARS]
    last = full_text[-_LAST_SECTION_CHARS:]
    return first, last, True


def _build_user_payload(
    *,
    first_section: str,
    last_section: str,
    middle_omitted: bool,
    duration_sec: float,
) -> str:
    """Собирает user prompt с first/last sections."""

    parts = [
        "=== VIDEO META ===",
        f"Total duration: {_fmt_duration_human(duration_sec)}",
        "",
        "=== FIRST SECTION ===",
        first_section,
    ]

    if middle_omitted:
        parts.extend(
            [
                "",
                "[MIDDLE OMITTED — содержит продолжение темы, см. тон начала и конца]",
                "",
                "=== LAST SECTION ===",
                last_section,
            ]
        )

    parts.extend(
        [
            "",
            (
                "Извлеки GlobalContext по OUTPUT SCHEMA. Не пересказывай "
                "содержание, а найди thematic spine видео — то что связывает "
                "first и last секции."
            ),
        ]
    )
    return "\n".join(parts)


# ─── Response parsing ─────────────────────────────────────────────────────


def _parse_context_dict(
    parsed: dict[str, Any],
    transcript: TranscriptResult,
) -> GlobalContext:
    """LLM output dict → GlobalContext. Graceful для missing fields."""

    central_theme = str(parsed.get("central_theme") or "").strip()[:500]
    speaker_role = str(parsed.get("speaker_role") or "").strip()[:120]
    video_structure = str(parsed.get("video_structure") or "").strip()[:160]
    tone = str(parsed.get("tone") or "").strip()[:100]
    language = str(parsed.get("language") or transcript.language or "ru").strip()[:8]

    raw_topics = parsed.get("key_topics")
    key_topics: list[str] = []
    if isinstance(raw_topics, list):
        for item in raw_topics[:8]:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    key_topics.append(cleaned[:100])

    return GlobalContext(
        central_theme=central_theme,
        key_topics=key_topics,
        speaker_role=speaker_role,
        video_structure=video_structure,
        language=language or "ru",
        tone=tone,
    )


def _empty_context(transcript: TranscriptResult) -> GlobalContext:
    """Deg-fallback: minimal context когда LLM недоступен."""

    return GlobalContext(
        central_theme="",
        key_topics=[],
        speaker_role="",
        video_structure="",
        language=transcript.language or "ru",
        tone="",
    )


def _build_response_schema() -> dict[str, Any]:
    """JSON schema for Gemini response_schema enforcement."""

    return {
        "type": "OBJECT",
        "properties": {
            "central_theme": {"type": "STRING"},
            "key_topics": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
            },
            "speaker_role": {"type": "STRING"},
            "video_structure": {"type": "STRING"},
            "language": {"type": "STRING"},
            "tone": {"type": "STRING"},
        },
        "required": [
            "central_theme",
            "key_topics",
            "speaker_role",
            "video_structure",
            "language",
            "tone",
        ],
    }


# ─── Formatting helpers ───────────────────────────────────────────────────


def _fmt_ts(sec: float) -> str:
    total = max(0, int(sec))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _fmt_duration_human(sec: float) -> str:
    total = max(0, int(sec))
    h, rem = divmod(total, 3600)
    m, _ = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


__all__ = ["build_global_context"]
