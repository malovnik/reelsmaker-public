"""Auto-detect VisionProfile по транскрипту + опционально vision-кэшу.

Эвристика запускается после Stage 2 (transcribe) — транскрипт уже есть в
памяти, vision-кэш может быть пустым если прогон впервые. Детектор НЕ меняет
выбранный профиль, только предлагает альтернативу фронту (UI suggestion chip).

Метрики:

* **WPM** — слов в минуту. Берём из `TranscriptCacheMeta.wpm` либо считаем
  через `transcripts.cache.compute_wpm()`.
* **silence_ratio** — доля времени без речи. `1 - sum(word_duration) / total`.
  Считается по word-level timestamps. Безопасно для сегментов без word-breakdown
  (fallback на среднюю длительность слова).
* **face_coverage** — доля кадров (из vision cache) где query 'person visible?'
  = yes. Когда vision cache пуст — None, правило `face_coverage > X` пропускается.

Правила (первое совпавшее):

1. `wpm < 40` AND `silence > 0.7` →
   - если `face_coverage is not None AND face_coverage > 0.5` → **fashion**
   - иначе → **travel**
2. `wpm > 120` AND (`face_coverage is None` OR `face_coverage > 0.5`) →
   **talking_head**
3. default → **talking_head** (безопасный fallback)

Confidence вычисляется как взвешенная сумма расстояний от метрик до порогов.
Normalized 0.0 — 1.0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field

from videomaker.core.logging import get_logger
from videomaker.models.job import VisionProfile
from videomaker.services.transcribers.base import TranscriptResult
from videomaker.services.transcribers.cache import compute_wpm

log = get_logger(__name__)


# Пороги — вынесены в константы для будущей тюнинг-конфигурации.
WPM_LOW = 40.0
WPM_HIGH = 120.0
SILENCE_HIGH = 0.70
FACE_COVERAGE_MID = 0.50


class ProfileMetrics(BaseModel):
    """Сырые метрики, использованные детектором. Возвращаются для UI."""

    wpm: float = Field(ge=0.0)
    silence_ratio: float = Field(ge=0.0, le=1.0)
    face_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    duration_sec: float = Field(ge=0.0)
    word_count: int = Field(ge=0)
    vision_frames_sampled: int = Field(default=0, ge=0)


class ProfileSuggestion(BaseModel):
    """Рекомендация детектора. Используется фронтом как suggestion chip."""

    profile: VisionProfile
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    metrics: ProfileMetrics


@dataclass(slots=True, frozen=True)
class FaceCoverageEstimate:
    """Результат чтения vision cache results.jsonl для face coverage."""

    coverage: float | None
    frames_sampled: int


def compute_silence_ratio(transcript: TranscriptResult) -> float:
    """Доля тишины. `1 - sum(word_duration) / total_duration`.

    Когда word-level timestamps отсутствуют — считаем по сегментам (менее точно).
    Безопасно: duration_sec == 0 → silence 0 (нет смысла оценивать пустой транскрипт).
    """
    if transcript.duration_sec <= 0:
        return 0.0

    speech_time = 0.0
    if transcript.words:
        for w in transcript.words:
            speech_time += max(0.0, w.end - w.start)
    else:
        for seg in transcript.segments:
            speech_time += max(0.0, seg.end - seg.start)

    silence = 1.0 - (speech_time / transcript.duration_sec)
    return max(0.0, min(1.0, silence))


def estimate_face_coverage(
    vision_cache_dir: Path, video_hash: str
) -> FaceCoverageEstimate:
    """Оценка face coverage через чтение `results.jsonl` vision-кэша.

    Ищет записи op='query' с params.prompt, содержащим 'person'/'face'/'visible',
    суммирует yes/no-ответы. Если файла нет или нет релевантных записей →
    coverage=None (правила c face_coverage пропускаются детектором).
    """
    results_path = vision_cache_dir / video_hash / "results.jsonl"
    if not results_path.exists():
        return FaceCoverageEstimate(coverage=None, frames_sampled=0)

    yes_count = 0
    total_count = 0
    try:
        with results_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    row = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                key = row.get("key", "")
                value = row.get("value", {})
                if not isinstance(key, str) or not key.startswith("query:"):
                    continue
                # value.answer — 'yes'/'no'/etc (Moondream 2-step VQA)
                answer = str(value.get("answer", "")).strip().lower()
                prompt = str(value.get("prompt", "")).lower()
                if not any(k in prompt for k in ("person", "face", "visible")):
                    continue
                total_count += 1
                if answer.startswith("yes"):
                    yes_count += 1
    except OSError as exc:
        log.warning(
            "profile_detector.vision_cache_read_failed",
            extra={"video_hash": video_hash, "error": str(exc)},
        )
        return FaceCoverageEstimate(coverage=None, frames_sampled=0)

    if total_count == 0:
        return FaceCoverageEstimate(coverage=None, frames_sampled=0)
    return FaceCoverageEstimate(
        coverage=yes_count / total_count, frames_sampled=total_count
    )


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def detect_profile(
    transcript: TranscriptResult,
    *,
    face_coverage: float | None = None,
    vision_frames_sampled: int = 0,
) -> ProfileSuggestion:
    """Подсказать профиль по transcript + опционально face_coverage.

    Не читает файлы — чистая функция над данными в памяти. Side-effects
    (чтение vision cache) делаются caller-ом через ``estimate_face_coverage``.
    """
    wpm = compute_wpm(transcript)
    silence = compute_silence_ratio(transcript)
    word_count = (
        len(transcript.words)
        if transcript.words
        else sum(len(s.words) if s.words else len(s.text.split()) for s in transcript.segments)
    )

    metrics = ProfileMetrics(
        wpm=wpm,
        silence_ratio=silence,
        face_coverage=face_coverage,
        duration_sec=transcript.duration_sec,
        word_count=word_count,
        vision_frames_sampled=vision_frames_sampled,
    )

    reasons: list[str] = []

    # Rule 1: мало слов + много тишины → визуальный контент
    if wpm < WPM_LOW and silence > SILENCE_HIGH:
        if face_coverage is not None and face_coverage > FACE_COVERAGE_MID:
            # Много лиц + мало слов → fashion (показ человека без речи)
            reasons.append(f"низкий WPM {wpm:.1f} (< {WPM_LOW})")
            reasons.append(f"высокая тишина {silence:.0%} (> {SILENCE_HIGH:.0%})")
            reasons.append(f"лица в кадре {face_coverage:.0%}")
            # Confidence: насколько сильно метрики проходят пороги
            conf_wpm = _clip01((WPM_LOW - wpm) / WPM_LOW)
            conf_sil = _clip01((silence - SILENCE_HIGH) / (1.0 - SILENCE_HIGH))
            conf_face = _clip01((face_coverage - FACE_COVERAGE_MID) / FACE_COVERAGE_MID)
            confidence = (conf_wpm + conf_sil + conf_face) / 3.0
            return ProfileSuggestion(
                profile=VisionProfile.fashion,
                confidence=confidence,
                reasons=reasons,
                metrics=metrics,
            )
        # Без лиц (или vision-данных нет) → travel
        reasons.append(f"низкий WPM {wpm:.1f} (< {WPM_LOW})")
        reasons.append(f"высокая тишина {silence:.0%} (> {SILENCE_HIGH:.0%})")
        if face_coverage is None:
            reasons.append("vision-данных нет — travel по умолчанию для минимума слов")
        else:
            reasons.append(f"лиц мало {face_coverage:.0%}")
        conf_wpm = _clip01((WPM_LOW - wpm) / WPM_LOW)
        conf_sil = _clip01((silence - SILENCE_HIGH) / (1.0 - SILENCE_HIGH))
        confidence = (conf_wpm + conf_sil) / 2.0
        return ProfileSuggestion(
            profile=VisionProfile.travel,
            confidence=confidence,
            reasons=reasons,
            metrics=metrics,
        )

    # Rule 2: много слов + лица в кадре → подкаст/говорящая голова
    if wpm > WPM_HIGH and (face_coverage is None or face_coverage > FACE_COVERAGE_MID):
        reasons.append(f"высокий WPM {wpm:.1f} (> {WPM_HIGH})")
        if face_coverage is not None:
            reasons.append(f"лица в кадре {face_coverage:.0%}")
        else:
            reasons.append("vision-данных нет — talking_head по умолчанию")
        conf_wpm = _clip01((wpm - WPM_HIGH) / WPM_HIGH)
        conf_face = (
            _clip01((face_coverage - FACE_COVERAGE_MID) / FACE_COVERAGE_MID)
            if face_coverage is not None
            else 0.5
        )
        confidence = (conf_wpm + conf_face) / 2.0
        return ProfileSuggestion(
            profile=VisionProfile.talking_head,
            confidence=confidence,
            reasons=reasons,
            metrics=metrics,
        )

    # Default fallback — talking_head как safe default
    reasons.append(
        f"метрики в средней зоне (WPM={wpm:.1f}, silence={silence:.0%}) — default"
    )
    return ProfileSuggestion(
        profile=VisionProfile.talking_head,
        confidence=0.3,
        reasons=reasons,
        metrics=metrics,
    )
