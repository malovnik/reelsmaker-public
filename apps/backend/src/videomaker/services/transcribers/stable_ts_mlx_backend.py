"""stable-ts MLX backend: word-timestamps ±20-30ms на Apple Silicon.

TIER1-#7: замена `mlx_whisper` default-бэкенда на stable-ts с MLX.
stable-ts — высокоуровневая обёртка OpenAI Whisper с улучшенной
post-processing логикой word-level timestamps (регрузка wavelet-
derived voice activity + token-to-time alignment correction).
На M-chip даёт ±20-30ms точности вместо ±50-80ms у raw mlx-whisper.

Разблокирует downstream:
* filler-removal (TIER 2 #13) — нужны word-boundaries чётко
* J/L cuts (TIER 2 #15) — audio_lead/tail ±400-600ms sensitive
* subtitle sync — точность <50ms заметна в кадре
"""

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


class StableTsMlxBackend:
    """stable-ts с MLX-бэкендом. Совместимый с `Transcriber` Protocol.

    API identical to ``MlxWhisperBackend`` — возвращает тот же
    ``TranscriptResult``. Вызывается из ``build_transcriber("stable_ts_mlx")``.
    """

    name = "stable_ts_mlx"

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
            "stable_ts_mlx_start",
            path=str(audio_path),
            language=language or "auto",
            model=self.model,
        )
        try:
            raw = await asyncio.to_thread(self._run_sync, audio_path, language)
        except Exception as exc:
            log.error("stable_ts_mlx_failed", error=str(exc))
            raise TranscriberError(f"stable-ts mlx failed: {exc}") from exc
        return self._to_result(raw, fallback_language=language or "und")

    def _run_sync(self, audio_path: Path, language: str | None) -> dict[str, Any]:
        import stable_whisper  # type: ignore[import-untyped]

        model: Any = stable_whisper.load_mlx_whisper(self.model)

        kwargs: dict[str, Any] = {
            "verbose": self.verbose,
            "word_timestamps": True,
            "temperature": 0.0,
            "condition_on_previous_text": False,
            # TIER1-FIX (rec из Context7/stable-ts README):
            # `vad=True` — внутренняя voice activity detection корректирует
            #    silence границы сегментов (поверх raw whisper).
            # `regroup=True` — регрупирует слова в естественные фразы по
            #    punctuation/паузам — лучше для субтитров и J/L-cuts.
            "vad": True,
            "regroup": True,
        }
        if language:
            kwargs["language"] = language
        result: Any = model.transcribe(str(audio_path), **kwargs)
        # stable-ts WhisperResult поддерживает to_dict() — унифицируем в
        # такой же формат, что уже парсится в `_to_result`.
        if hasattr(result, "to_dict"):
            return result.to_dict()
        return dict(result)

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
                if confidence is None:
                    confidence = w.get("score")
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
                "backend": "stable_ts_mlx",
            },
        )


def _avg(segments: list[dict[str, Any]], key: str) -> float | None:
    values = [float(s[key]) for s in segments if isinstance(s.get(key), (int, float))]
    if not values:
        return None
    return sum(values) / len(values)
