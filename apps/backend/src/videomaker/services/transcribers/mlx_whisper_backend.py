"""mlx-whisper backend (Apple Silicon MPS)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from videomaker.core.logging import get_logger
from videomaker.services.transcribers.base import (
    TranscribedSegment,
    TranscribedWord,
    TranscriberError,
    TranscriptResult,
    is_lexical_filler,
)

log = get_logger(__name__)


class MlxWhisperBackend:
    """Локальная транскрибация через mlx-whisper (Apple MLX).

    Работает синхронно под капотом — выносим в `asyncio.to_thread`, чтобы
    FastAPI-event loop не блокировался на тяжёлой Metal-инференции.
    """

    name = "mlx_whisper"

    def __init__(self, model: str, *, verbose: bool = False) -> None:
        self.model = model
        self.verbose = verbose

    async def transcribe(
        self,
        audio_path: Path,
        *,
        language: str | None = None,
    ) -> TranscriptResult:
        if not audio_path.exists():
            raise TranscriberError(f"audio file not found: {audio_path}")
        log.info(
            "mlx_whisper_start",
            path=str(audio_path),
            language=language or "auto",
            model=self.model,
        )
        try:
            raw = await asyncio.to_thread(self._run_sync, audio_path, language)
        except Exception as exc:
            log.error("mlx_whisper_failed", error=str(exc))
            raise TranscriberError(f"mlx-whisper failed: {exc}") from exc
        return self._to_result(raw, fallback_language=language or "und")

    def _run_sync(self, audio_path: Path, language: str | None) -> dict[str, Any]:
        import mlx_whisper  # type: ignore[import-untyped]

        kwargs: dict[str, Any] = {
            "path_or_hf_repo": self.model,
            "word_timestamps": True,
            "verbose": self.verbose,
            "condition_on_previous_text": False,
            "temperature": 0.0,
        }
        if language:
            kwargs["language"] = language
        result: dict[str, Any] = mlx_whisper.transcribe(str(audio_path), **kwargs)
        return result

    def _to_result(self, raw: dict[str, Any], *, fallback_language: str) -> TranscriptResult:
        raw_segments = raw.get("segments") or []
        segments: list[TranscribedSegment] = []
        words: list[TranscribedWord] = []

        for seg in raw_segments:
            seg_words: list[TranscribedWord] = []
            for w in seg.get("words") or []:
                text = str(w.get("word", "")).strip()
                if not text:
                    continue
                start = float(w.get("start", seg.get("start", 0.0)))
                end = float(w.get("end", seg.get("end", start)))
                confidence = w.get("probability")
                tw = TranscribedWord(
                    word=text,
                    start=max(0.0, start),
                    end=max(start, end),
                    confidence=float(confidence) if confidence is not None else None,
                    is_filler=is_lexical_filler(text),
                )
                seg_words.append(tw)
                words.append(tw)
            segments.append(
                TranscribedSegment(
                    text=str(seg.get("text", "")).strip(),
                    start=float(seg.get("start", 0.0)),
                    end=float(seg.get("end", seg.get("start", 0.0))),
                    words=seg_words,
                )
            )

        duration = float(raw.get("duration") or (segments[-1].end if segments else 0.0))

        return TranscriptResult(
            transcriber=self.name,
            model=self.model,
            language=str(raw.get("language") or fallback_language),
            duration_sec=duration,
            segments=segments,
            words=words,
            raw_metadata={
                "avg_logprob": _avg(raw_segments, "avg_logprob"),
                "no_speech_prob": _avg(raw_segments, "no_speech_prob"),
                "compression_ratio": _avg(raw_segments, "compression_ratio"),
            },
        )


def _avg(segments: list[dict[str, Any]], key: str) -> float | None:
    values = [float(s[key]) for s in segments if isinstance(s.get(key), (int, float))]
    if not values:
        return None
    return sum(values) / len(values)
