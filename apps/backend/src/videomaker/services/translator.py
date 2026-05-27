"""Адаптивный перевод транскрипта через LLM.

Работает над сегментами — для каждого вызывает LLM, получает русский
перевод, затем равномерно распределяет слова перевода в диапазоне
[segment.start, segment.end], сохраняя длительность сегмента.

Используется в pipeline между transcribe и silence_cut, если
`detected_language != target_language`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from videomaker.core.config import Settings, get_settings
from videomaker.core.logging import get_logger
from videomaker.services.llm_client import (
    LLMClient,
    LLMError,
    build_llm,
    parse_json_response,
)
from videomaker.services.transcribers.base import (
    TranscribedSegment,
    TranscribedWord,
    TranscriptResult,
)

log = get_logger(__name__)

BATCH_SIZE = 15
DEFAULT_PROMPT_KEY = "translate_adaptive_ru"


@dataclass(slots=True)
class TranslatorConfig:
    llm_provider: str
    llm_model: str
    source_language: str
    target_language: str = "ru"
    max_tokens_per_call: int = 16000


class Translator:
    """Переводит сегменты транскрипта через LLM с адаптацией под язык цели."""

    def __init__(
        self,
        config: TranslatorConfig,
        *,
        system_prompt: str,
        llm: LLMClient | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.config = config
        self.settings = settings or get_settings()
        self.system_prompt = system_prompt
        self._semaphore = asyncio.Semaphore(self.settings.llm_max_concurrency)
        self._llm: LLMClient = llm or build_llm(
            config.llm_provider, config.llm_model, self.settings
        )

    async def translate(self, transcript: TranscriptResult) -> TranscriptResult:
        if not transcript.segments:
            return transcript

        # Skip only if user explicitly указал моноязычный target (source_language=ru)
        # и detected совпадает. При source="auto"/"mixed" — всегда прогоняем через
        # LLM, потому что Deepgram's majority vote может скрывать иноязычные
        # фрагменты (переводчик в кадре, гостевые реплики). Промпт умеет
        # no-op'ить уже-русские сегменты (правило 1 в TRANSLATE_ADAPTIVE_RU).
        detected = (transcript.language or "").lower()
        user_hint = (self.config.source_language or "").lower()
        target = self.config.target_language.lower()
        user_explicit_target = (
            user_hint not in {"", "auto", "mixed"}
            and user_hint.startswith(target)
        )
        if user_explicit_target and detected.startswith(target):
            log.info(
                "translate_skip_same_language",
                source=transcript.language,
                target=target,
                user_hint=user_hint,
            )
            return transcript

        batches = _chunk_segments(transcript.segments, BATCH_SIZE)
        log.info(
            "translate_start",
            source=transcript.language,
            target=self.config.target_language,
            batches=len(batches),
            segments=len(transcript.segments),
        )

        tasks = [self._translate_batch(batch) for batch in batches]
        translated_batches = await asyncio.gather(*tasks)
        translated_segments: list[TranscribedSegment] = []
        for batch in translated_batches:
            translated_segments.extend(batch)

        flat_words: list[TranscribedWord] = []
        for seg in translated_segments:
            flat_words.extend(seg.words)

        log.info(
            "translate_done",
            output_segments=len(translated_segments),
            output_words=len(flat_words),
        )

        return TranscriptResult(
            transcriber=transcript.transcriber,
            model=transcript.model,
            language=self.config.target_language,
            duration_sec=transcript.duration_sec,
            segments=translated_segments,
            words=flat_words,
            raw_metadata={
                **transcript.raw_metadata,
                "translated_from": transcript.language,
                "translator_model": self._llm.model,
                "translator_provider": self._llm.provider,
            },
        )

    async def _translate_batch(
        self, batch: list[TranscribedSegment]
    ) -> list[TranscribedSegment]:
        payload = [
            {"id": i, "start": seg.start, "end": seg.end, "text": seg.text}
            for i, seg in enumerate(batch)
        ]
        user_content = (
            f"source_language: {self.config.source_language}\n"
            f"target_language: {self.config.target_language}\n"
            f"segments: {_json_dumps(payload)}"
        )

        async with self._semaphore:
            response = await self._llm.complete_json(
                system=self.system_prompt,
                user=user_content,
                temperature=0.35,
                max_tokens=self.config.max_tokens_per_call,
            )

        try:
            parsed = parse_json_response(response.text)
        except LLMError as exc:
            log.error("translate_parse_failed", error=str(exc))
            return batch  # fallback: оригинал лучше, чем ошибка

        translated_items = _extract_items(parsed)
        by_id = {int(item.get("id", -1)): str(item.get("text") or "") for item in translated_items}

        result: list[TranscribedSegment] = []
        for i, seg in enumerate(batch):
            translated_text = by_id.get(i)
            if not translated_text:
                log.warning("translate_missing_segment", index=i, original=seg.text[:40])
                result.append(seg)
                continue
            result.append(_rebuild_segment_with_text(seg, translated_text))
        return result


def _chunk_segments(
    segments: list[TranscribedSegment], batch_size: int
) -> list[list[TranscribedSegment]]:
    return [segments[i : i + batch_size] for i in range(0, len(segments), batch_size)]


def _extract_items(parsed: Any) -> list[dict[str, Any]]:
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    if isinstance(parsed, dict):
        for key in ("segments", "items", "translated"):
            if key in parsed and isinstance(parsed[key], list):
                return [x for x in parsed[key] if isinstance(x, dict)]
        return [parsed]
    return []


def _rebuild_segment_with_text(
    original: TranscribedSegment, translated_text: str
) -> TranscribedSegment:
    text = translated_text.strip()
    words = [w for w in text.split() if w]
    if not words:
        return original

    # Распределяем переведённые слова по реальному speech-окну
    # [first_word.start, last_word.end], а НЕ по segment.start/end.
    # STT-бэкенды (Deepgram paragraphs, Whisper utterances) возвращают
    # segment-границы, которые могут включать leading/trailing silence
    # padding — если распределить на весь такой span, синтетические
    # русские слова получат timings, заходящие в тишину, и ASS-субтитры
    # уедут относительно реального звука. Word-level span сохраняет
    # синхронизацию с актуальным голосом в исходной дорожке.
    if original.words:
        speech_start = original.words[0].start
        speech_end = original.words[-1].end
    else:
        speech_start = original.start
        speech_end = original.end
    # Защита от вырожденных/перевёрнутых диапазонов: клипаем в пределы
    # segment'а и гарантируем положительную длительность.
    speech_start = max(original.start, min(speech_start, original.end))
    speech_end = max(original.start, min(speech_end, original.end))
    if speech_end <= speech_start:
        speech_start = original.start
        speech_end = original.end

    duration = max(0.001, speech_end - speech_start)
    per_word = duration / len(words)
    new_words: list[TranscribedWord] = []
    for idx, word in enumerate(words):
        start = speech_start + idx * per_word
        end = speech_start + (idx + 1) * per_word
        new_words.append(TranscribedWord(word=word, start=round(start, 3), end=round(end, 3)))

    return TranscribedSegment(
        text=text,
        start=original.start,
        end=original.end,
        words=new_words,
    )


def _json_dumps(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


__all__ = [
    "Translator",
    "TranslatorConfig",
]
