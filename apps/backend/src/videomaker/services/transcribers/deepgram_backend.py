"""Deepgram nova-3 backend (deepgram-sdk v6, Fern-generated async client)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from videomaker.core.logging import get_logger
from videomaker.services.transcribers.base import (
    TranscribedSegment,
    TranscribedWord,
    TranscriberError,
    TranscriptResult,
    is_lexical_filler,
    merge_words_into_segments,
)

log = get_logger(__name__)


class DeepgramBackend:
    """Облачная транскрибация через Deepgram nova-3.

    Использует `AsyncDeepgramClient.listen.v1.media.transcribe_file` с байтами файла.
    SDK v6 retry не делает — оборачиваем tenacity с exponential backoff.
    """

    name = "deepgram"

    def __init__(self, api_key: str, model: str = "nova-3") -> None:
        if not api_key:
            raise ValueError("Deepgram api_key is required")
        self.model = model
        self._api_key = api_key

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
    ) -> TranscriptResult:
        if not audio_path.exists():
            raise TranscriberError(f"audio file not found: {audio_path}")

        from deepgram import AsyncDeepgramClient

        client = AsyncDeepgramClient(api_key=self._api_key)

        log.info(
            "deepgram_start",
            path=str(audio_path),
            language=language or "auto",
            model=self.model,
            size_bytes=audio_path.stat().st_size,
        )

        payload = audio_path.read_bytes()
        call_kwargs: dict[str, Any] = {
            "request": payload,
            "model": self.model,
            "punctuate": True,
            "smart_format": True,
            "utterances": True,
            "filler_words": True,
            "paragraphs": True,
        }
        if language:
            call_kwargs["language"] = language
        else:
            call_kwargs["detect_language"] = True

        response: Any = None
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                response = await client.listen.v1.media.transcribe_file(**call_kwargs)

        return self._to_result(response, fallback_language=language or "und")

    def _to_result(self, response: Any, *, fallback_language: str) -> TranscriptResult:
        data = _dump(response)

        metadata = data.get("metadata", {}) or {}
        duration = float(metadata.get("duration") or 0.0)
        detected_lang = str(
            metadata.get("language")
            or data.get("results", {}).get("channels", [{}])[0].get("detected_language")
            or fallback_language
        )

        results = data.get("results") or {}
        channels = results.get("channels") or []
        if not channels:
            raise TranscriberError("deepgram response contains no channels")

        alternatives = channels[0].get("alternatives") or []
        if not alternatives:
            raise TranscriberError("deepgram response contains no alternatives")

        alt = alternatives[0]
        words = _extract_words(alt)
        segments = _extract_segments(alt, words)

        if not segments and words:
            segments = merge_words_into_segments(words)

        return TranscriptResult(
            transcriber=self.name,
            model=self.model,
            language=detected_lang,
            duration_sec=duration,
            segments=segments,
            words=words,
            raw_metadata={
                "request_id": metadata.get("request_id"),
                "models": metadata.get("models"),
                "confidence": alt.get("confidence"),
            },
        )


def _dump(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return response
    if hasattr(response, "model_dump"):
        return cast(dict[str, Any], response.model_dump(mode="python"))
    if hasattr(response, "dict"):
        return cast(dict[str, Any], response.dict())
    raise TranscriberError(
        f"cannot serialise deepgram response: {type(response).__name__}"
    )


def _extract_words(alternative: dict[str, Any]) -> list[TranscribedWord]:
    raw_words = alternative.get("words") or []
    words: list[TranscribedWord] = []
    for w in raw_words:
        text = str(w.get("punctuated_word") or w.get("word") or "").strip()
        if not text:
            continue
        start = float(w.get("start", 0.0))
        end = float(w.get("end", start))
        confidence = w.get("confidence")
        words.append(
            TranscribedWord(
                word=text,
                start=max(0.0, start),
                end=max(start, end),
                confidence=float(confidence) if confidence is not None else None,
                is_filler=is_lexical_filler(text),
            )
        )
    return words


def _extract_segments(
    alternative: dict[str, Any], words: list[TranscribedWord]
) -> list[TranscribedSegment]:
    paragraphs = (alternative.get("paragraphs") or {}).get("paragraphs") or []
    if paragraphs:
        return _segments_from_paragraphs(paragraphs, words)

    utterances = alternative.get("utterances") or []
    if utterances:
        return _segments_from_utterances(utterances, words)
    return []


def _segments_from_paragraphs(
    paragraphs: list[dict[str, Any]], words: list[TranscribedWord]
) -> list[TranscribedSegment]:
    segments: list[TranscribedSegment] = []
    for p in paragraphs:
        sentences = p.get("sentences") or []
        for s in sentences:
            start = float(s.get("start", 0.0))
            end = float(s.get("end", start))
            segments.append(
                TranscribedSegment(
                    text=str(s.get("text", "")).strip(),
                    start=start,
                    end=end,
                    words=[w for w in words if start <= w.start < end],
                )
            )
    return segments


def _segments_from_utterances(
    utterances: list[dict[str, Any]], words: list[TranscribedWord]
) -> list[TranscribedSegment]:
    segments: list[TranscribedSegment] = []
    for utt in utterances:
        start = float(utt.get("start", 0.0))
        end = float(utt.get("end", start))
        segments.append(
            TranscribedSegment(
                text=str(utt.get("transcript") or utt.get("text") or "").strip(),
                start=start,
                end=end,
                words=[w for w in words if start <= w.start < end],
            )
        )
    return segments
