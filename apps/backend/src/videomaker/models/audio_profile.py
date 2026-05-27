"""T11.1 — AudioProfile: agregated audio features для Automatic Mode.

Собирается через `services/audio_analyzer.extract_audio_profile(...)`.
Feeds Automatic Config Advisor (T11.2) rule tree, который решает какие
параметры pipeline включать для этого конкретного видео.

Все поля — базовые numeric, сериализуются как JSON (через pydantic model
ниже). NaN/None для feature которые не удалось посчитать (graceful
degrade) — advisor учитывает это в confidence score.

Источники feature:
- SNR — scikit-maad temporal_snr() (BSD-3)
- WPS — из Whisper transcript segments (уже в pipeline)
- Pitch std — Parselmouth pitch.to_pitch() F0 (GPL-3)
- LRA — pyloudnorm EBU R128 (MIT)
- Spectral centroid/flatness — librosa (ISC)
- Gap statistics — silero-vad timestamps (MIT)
- Rhythm CV — librosa onset_detect coefficient of variation
- Whisper confidence — segment.avg_logprob из stable-ts
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AudioProfile(BaseModel):
    """Агрегированные audio features для принятия решений Auto Mode."""

    model_config = ConfigDict(frozen=True)

    # === Качество записи ===
    snr_db: float = Field(description="Signal-to-noise ratio в dB")
    spectral_flatness: float = Field(
        description="0..1, >0.3 = noise-dominated, <0.05 = tonal"
    )
    spectral_centroid_hz: float = Field(
        description="Средний spectral centroid; <2000 = 'бубнящий' mic, >4500 = яркий"
    )
    spectral_centroid_std_hz: float = Field(
        description="Stability спектра; >2000 — возможны plosives/sibilants"
    )

    # === Темп речи ===
    wps: float = Field(
        description="Words per second (по VAD-времени, не total duration)"
    )
    pitch_std_hz: float = Field(
        description="F0 standard deviation; <15=монотонная, >40=эмоциональная"
    )
    pitch_mean_hz: float = Field(description="F0 mean для voiced frames")
    hnr_db: float = Field(
        description="Harmonics-to-noise ratio (Parselmouth)"
    )

    # === Loudness ===
    integrated_lufs: float = Field(description="EBU R128 integrated loudness")
    lra_lu: float = Field(
        description="Loudness range; <6=компрессирован, >12=широкий"
    )

    # === Ритм и паузы ===
    mean_gap_sec: float = Field(description="Средняя длительность пауз между speech")
    gap_std_sec: float = Field(description="Std пауз")
    gap_kurtosis: float = Field(
        description="Kurtosis пауз; >3 = много коротких + редкие длинные"
    )
    max_gap_sec: float = Field(description="Максимальная пауза")
    rhythm_cv: float = Field(
        description="Coefficient of variation inter-onset intervals; <0.3=ритмичная"
    )

    # === Транскрипция ===
    whisper_avg_confidence: float = Field(
        description="Mean exp(avg_logprob) по whisper segments"
    )

    # === Контекст ===
    total_duration_sec: float = Field(description="Длительность audio файла")
    speech_duration_sec: float = Field(description="Длительность речи (VAD)")
    num_words: int = Field(description="Общее число слов из transcript")
    content_type: str = Field(
        default="unknown",
        description="talking_head | screencast | interview | mixed | unknown",
    )

    # === Maintenance ===
    extraction_ms: int = Field(
        default=0, description="Wall-clock ms на извлечение всех features"
    )
    failures: list[str] = Field(
        default_factory=list,
        description="Список features которые не удалось посчитать (для debug)",
    )


__all__ = ["AudioProfile"]
