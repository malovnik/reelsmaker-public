"""T11.1 — Audio feature extraction для Automatic Mode.

Параллельно извлекает ~15 audio features для принятия решений
`auto_config_advisor`. Время на 30-мин видео: ~12-15 сек параллельно
(vs ~34 сек sequential).

Интерфейс:
    from videomaker.services.audio_analyzer import extract_audio_profile
    profile = await extract_audio_profile(
        audio_path, transcript_segments, total_duration_sec
    )
    # → AudioProfile с 15+ fields

Graceful degrade:
- Любой feature extractor может упасть (плохой формат, silent audio, и т.д.)
- При падении — поле получает safe-default (snr_db=20, pitch_std_hz=20, ...)
- Имя feature добавляется в profile.failures[] для debug

Все extractor'ы запускаются через `asyncio.to_thread` — библиотеки
sync, блокируют event loop. Параллелизация даёт ~2.5x speedup.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videomaker.core.logging import get_logger
from videomaker.models.audio_profile import AudioProfile

log = get_logger(__name__)


def _warm_imports() -> None:
    """Eagerly import scientific libraries to avoid race conditions in
    ``asyncio.to_thread`` parallel workers.

    scipy has a known circular-import issue when multiple threads concurrently
    trigger first-time import (scipy._lib._testutils PytestTester race). Same
    applies to librosa/parselmouth which depend on scipy. Pre-importing once
    in main thread resolves it.
    """
    try:
        import librosa  # noqa: F401
        import numpy  # noqa: F401
        import pyloudnorm  # noqa: F401
        import scipy
        import scipy.signal
        import scipy.stats  # noqa: F401
        import soundfile  # noqa: F401
    except Exception as exc:
        log.debug("audio_analyzer_warmup_skipped", error=str(exc))


_warm_imports()


#: Safe defaults когда extractor падает (не None чтобы не ломать rule tree).
#: Цифры выбраны как «нейтральные» — advisor не примет экстремальных решений.
_DEFAULT_SNR_DB = 20.0
_DEFAULT_PITCH_STD_HZ = 25.0
_DEFAULT_PITCH_MEAN_HZ = 150.0
_DEFAULT_HNR_DB = 10.0
_DEFAULT_LUFS = -18.0
_DEFAULT_LRA = 8.0
_DEFAULT_SPECTRAL_FLATNESS = 0.1
_DEFAULT_SPECTRAL_CENTROID_HZ = 2500.0
_DEFAULT_SPECTRAL_CENTROID_STD = 800.0
_DEFAULT_RHYTHM_CV = 0.5
_DEFAULT_MEAN_GAP_SEC = 0.3
_DEFAULT_GAP_KURTOSIS = 1.5


@dataclass(slots=True)
class _TranscriptStats:
    num_words: int
    total_words_duration_sec: float
    avg_log_prob: float | None
    speech_segments: list[tuple[float, float]]


async def extract_audio_profile(
    audio_path: Path,
    transcript_segments: Iterable[Any] | None = None,
    total_duration_sec: float | None = None,
    *,
    content_type_hint: str = "unknown",
) -> AudioProfile:
    """Извлекает AudioProfile из audio файла + (опционально) transcript.

    ``transcript_segments`` — iterable объектов с полями `words`, `text`,
    `avg_logprob` (типа stable-ts segments). Если None — num_words=0,
    whisper_avg_confidence=0.0, wps рассчитывается через VAD-time.

    ``total_duration_sec`` — если None, пробуем ffprobe.
    """
    if not audio_path.exists():
        log.warning("audio_analyzer_missing", path=str(audio_path))
        return _safe_default_profile(
            total_duration_sec or 0.0,
            content_type_hint,
            transcript_segments=transcript_segments,
        )

    started_ms = int(time.monotonic() * 1000)
    failures: list[str] = []

    duration_sec = total_duration_sec or 0.0
    if duration_sec <= 0:
        duration_sec = await asyncio.to_thread(_probe_duration, audio_path) or 0.0

    transcript_stats = _aggregate_transcript_stats(transcript_segments)

    tasks = [
        asyncio.to_thread(_extract_snr, audio_path, failures),
        asyncio.to_thread(_extract_loudness, audio_path, failures),
        asyncio.to_thread(_extract_spectral, audio_path, failures),
        asyncio.to_thread(_extract_pitch, audio_path, failures),
        asyncio.to_thread(_extract_vad_gaps, audio_path, failures),
        asyncio.to_thread(_extract_rhythm_cv, audio_path, failures),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    snr_out, loud_out, spec_out, pitch_out, vad_out, rhythm_out = [
        r if not isinstance(r, BaseException) else {} for r in results
    ]

    snr_db = _get(snr_out, "snr_db", _DEFAULT_SNR_DB)

    integrated_lufs = _get(loud_out, "integrated_lufs", _DEFAULT_LUFS)
    lra_lu = _get(loud_out, "lra_lu", _DEFAULT_LRA)

    spectral_flatness = _get(spec_out, "flatness", _DEFAULT_SPECTRAL_FLATNESS)
    spectral_centroid_hz = _get(
        spec_out, "centroid_hz", _DEFAULT_SPECTRAL_CENTROID_HZ
    )
    spectral_centroid_std = _get(
        spec_out, "centroid_std", _DEFAULT_SPECTRAL_CENTROID_STD
    )

    pitch_mean_hz = _get(pitch_out, "pitch_mean_hz", _DEFAULT_PITCH_MEAN_HZ)
    pitch_std_hz = _get(pitch_out, "pitch_std_hz", _DEFAULT_PITCH_STD_HZ)
    hnr_db = _get(pitch_out, "hnr_db", _DEFAULT_HNR_DB)

    mean_gap_sec = _get(vad_out, "mean_gap", _DEFAULT_MEAN_GAP_SEC)
    gap_std_sec = _get(vad_out, "gap_std", 0.25)
    gap_kurtosis = _get(vad_out, "gap_kurtosis", _DEFAULT_GAP_KURTOSIS)
    max_gap_sec = _get(vad_out, "max_gap", mean_gap_sec * 3)
    speech_duration_sec = _get(vad_out, "speech_duration", duration_sec * 0.8)

    rhythm_cv = _get(rhythm_out, "rhythm_cv", _DEFAULT_RHYTHM_CV)

    if transcript_stats.num_words > 0 and speech_duration_sec > 0:
        wps = transcript_stats.num_words / speech_duration_sec
    elif transcript_stats.num_words > 0 and transcript_stats.total_words_duration_sec > 0:
        # Fallback #1: когда VAD упал (speech_duration_sec=0), считаем
        # через сумму длительностей слов из word-timestamps.
        wps = transcript_stats.num_words / transcript_stats.total_words_duration_sec
    elif transcript_stats.num_words > 0 and duration_sec > 0:
        # Fallback #2: слов на секунду видео (грубый, но даёт сигнал
        # для Automatic Mode pacing rules).
        wps = transcript_stats.num_words / duration_sec
    else:
        wps = 0.0

    whisper_avg_confidence = 0.0
    if transcript_stats.avg_log_prob is not None:
        import math

        whisper_avg_confidence = max(
            0.0, min(1.0, math.exp(transcript_stats.avg_log_prob))
        )

    extraction_ms = int(time.monotonic() * 1000) - started_ms
    log.info(
        "audio_analyzer_done",
        duration_sec=duration_sec,
        extraction_ms=extraction_ms,
        snr_db=round(snr_db, 1),
        wps=round(wps, 2),
        pitch_std=round(pitch_std_hz, 1),
        lra=round(lra_lu, 1),
        failures=failures,
    )

    return AudioProfile(
        snr_db=snr_db,
        spectral_flatness=spectral_flatness,
        spectral_centroid_hz=spectral_centroid_hz,
        spectral_centroid_std_hz=spectral_centroid_std,
        wps=wps,
        pitch_std_hz=pitch_std_hz,
        pitch_mean_hz=pitch_mean_hz,
        hnr_db=hnr_db,
        integrated_lufs=integrated_lufs,
        lra_lu=lra_lu,
        mean_gap_sec=mean_gap_sec,
        gap_std_sec=gap_std_sec,
        gap_kurtosis=gap_kurtosis,
        max_gap_sec=max_gap_sec,
        rhythm_cv=rhythm_cv,
        whisper_avg_confidence=whisper_avg_confidence,
        total_duration_sec=duration_sec,
        speech_duration_sec=speech_duration_sec,
        num_words=transcript_stats.num_words,
        content_type=content_type_hint,
        extraction_ms=extraction_ms,
        failures=failures,
    )


def _safe_default_profile(
    duration_sec: float,
    content_type: str,
    *,
    transcript_segments: Iterable[Any] | None = None,
) -> AudioProfile:
    """Безопасный AudioProfile при отсутствии audio-файла.

    Audio-based метрики (SNR, pitch, loudness, VAD, rhythm) уходят в
    дефолты с флагом ``missing_audio_file`` в ``failures``. Но если
    ``transcript_segments`` переданы — transcript-based поля (num_words,
    wps, whisper_avg_confidence, speech_duration) заполняем из транскрипта.
    Это позволяет Automatic Mode принимать решения по темпу речи даже
    когда wav ещё не извлечён (auto-analyze до запуска pipeline).
    """
    stats = _aggregate_transcript_stats(transcript_segments)
    speech_duration = stats.total_words_duration_sec
    if stats.num_words > 0 and speech_duration > 0:
        wps = stats.num_words / speech_duration
    elif stats.num_words > 0 and duration_sec > 0:
        # Fallback: слов на секунду видео (грубее, но даёт сигнал).
        wps = stats.num_words / duration_sec
    else:
        wps = 0.0
    whisper_confidence = 0.0
    if stats.avg_log_prob is not None:
        import math

        whisper_confidence = max(0.0, min(1.0, math.exp(stats.avg_log_prob)))
    failures = ["missing_audio_file"]
    return AudioProfile(
        snr_db=_DEFAULT_SNR_DB,
        spectral_flatness=_DEFAULT_SPECTRAL_FLATNESS,
        spectral_centroid_hz=_DEFAULT_SPECTRAL_CENTROID_HZ,
        spectral_centroid_std_hz=_DEFAULT_SPECTRAL_CENTROID_STD,
        wps=round(wps, 2),
        pitch_std_hz=_DEFAULT_PITCH_STD_HZ,
        pitch_mean_hz=_DEFAULT_PITCH_MEAN_HZ,
        hnr_db=_DEFAULT_HNR_DB,
        integrated_lufs=_DEFAULT_LUFS,
        lra_lu=_DEFAULT_LRA,
        mean_gap_sec=_DEFAULT_MEAN_GAP_SEC,
        gap_std_sec=0.25,
        gap_kurtosis=_DEFAULT_GAP_KURTOSIS,
        max_gap_sec=_DEFAULT_MEAN_GAP_SEC * 3,
        rhythm_cv=_DEFAULT_RHYTHM_CV,
        whisper_avg_confidence=whisper_confidence,
        total_duration_sec=duration_sec,
        speech_duration_sec=speech_duration,
        num_words=stats.num_words,
        content_type=content_type,
        failures=failures,
    )


def _get(d: dict[str, Any], key: str, default: float) -> float:
    value = d.get(key, default)
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    import math

    if math.isnan(f) or math.isinf(f):
        return default
    return f


def _aggregate_transcript_stats(
    segments: Iterable[Any] | None,
) -> _TranscriptStats:
    if segments is None:
        return _TranscriptStats(0, 0.0, None, [])
    num_words = 0
    total_words_duration = 0.0
    log_probs: list[float] = []
    speech_segments: list[tuple[float, float]] = []
    for seg in segments:
        words = getattr(seg, "words", None) or []
        num_words += len(words)
        for w in words:
            start = getattr(w, "start", None)
            end = getattr(w, "end", None)
            if start is not None and end is not None and end > start:
                total_words_duration += float(end) - float(start)
        seg_start = getattr(seg, "start", None)
        seg_end = getattr(seg, "end", None)
        if seg_start is not None and seg_end is not None:
            speech_segments.append((float(seg_start), float(seg_end)))
        lp = getattr(seg, "avg_logprob", None)
        if isinstance(lp, int | float):
            log_probs.append(float(lp))
    avg_lp = sum(log_probs) / len(log_probs) if log_probs else None
    return _TranscriptStats(num_words, total_words_duration, avg_lp, speech_segments)


def _probe_duration(audio_path: Path) -> float | None:
    try:
        import soundfile as sf

        info = sf.info(str(audio_path))
        return float(info.frames) / float(info.samplerate)
    except Exception as exc:
        log.warning(
            "audio_probe_failed",
            reason="soundfile.info raised; duration will fall back to 0",
            path=str(audio_path),
            error=str(exc)[:200],
        )
        return None


def _extract_snr(audio_path: Path, failures: list[str]) -> dict[str, float]:
    """SNR через scikit-maad temporal_snr()."""
    try:
        from maad import sound

        s, fs = sound.load(str(audio_path))
        # temporal_snr возвращает (ENRt, BGNt, SNRt) — energy, background noise, SNR
        # API maad может варьироваться — используем через util
        try:
            from maad.features import temporal_snr

            _enrt, _bgnt, snrt = temporal_snr(s)
        except Exception:
            # Fallback через power ratio
            import numpy as np

            energy = np.mean(s**2)
            # noise floor = 10th percentile power frame
            frame_len = int(fs * 0.1)
            if len(s) < frame_len:
                failures.append("snr")
                log.warning(
                    "snr_extract_too_short",
                    reason="audio shorter than 100ms frame; SNR fallback disabled",
                    samples=len(s),
                    frame_len=frame_len,
                    path=str(audio_path),
                )
                return {}
            frames = s[: len(s) - len(s) % frame_len].reshape(-1, frame_len)
            frame_power = np.mean(frames**2, axis=1)
            noise = float(np.percentile(frame_power, 10))
            if noise <= 0:
                failures.append("snr")
                log.warning(
                    "snr_extract_degenerate",
                    reason="noise floor is zero or negative; likely all-silence audio",
                    path=str(audio_path),
                )
                return {}
            snrt = 10 * np.log10(max(energy, 1e-12) / max(noise, 1e-12))
        return {"snr_db": float(snrt)}
    except Exception as exc:
        failures.append("snr")
        log.warning(
            "snr_extract_failed",
            reason="maad/fallback SNR extraction raised",
            path=str(audio_path),
            error=str(exc)[:200],
        )
        return {}


def _extract_loudness(
    audio_path: Path, failures: list[str]
) -> dict[str, float]:
    """EBU R128 integrated loudness + LRA через pyloudnorm."""
    try:
        import pyloudnorm as pyln
        import soundfile as sf

        data, sr = sf.read(str(audio_path))
        if data.ndim > 1:
            import numpy as np

            data = np.mean(data, axis=1)
        if len(data) < sr:  # < 1s
            failures.append("loudness")
            log.warning(
                "loudness_extract_too_short",
                reason="audio shorter than 1s; EBU R128 requires >=1s",
                samples=len(data),
                sr=sr,
                path=str(audio_path),
            )
            return {}
        meter = pyln.Meter(sr)
        integrated = meter.integrated_loudness(data)
        lra = meter.loudness_range(data)
        return {"integrated_lufs": float(integrated), "lra_lu": float(lra)}
    except Exception as exc:
        failures.append("loudness")
        log.warning(
            "loudness_extract_failed",
            reason="pyloudnorm raised on integrated_loudness/loudness_range",
            path=str(audio_path),
            error=str(exc)[:200],
        )
        return {}


def _extract_spectral(
    audio_path: Path, failures: list[str]
) -> dict[str, float]:
    """Spectral flatness + centroid через librosa."""
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
        if len(y) < sr:
            failures.append("spectral")
            log.warning(
                "spectral_extract_too_short",
                reason="audio shorter than 1s; spectral features skipped",
                samples=len(y),
                sr=sr,
                path=str(audio_path),
            )
            return {}
        flatness = librosa.feature.spectral_flatness(y=y)
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
        return {
            "flatness": float(np.mean(flatness)),
            "centroid_hz": float(np.mean(centroid)),
            "centroid_std": float(np.std(centroid)),
        }
    except Exception as exc:
        failures.append("spectral")
        log.warning(
            "spectral_extract_failed",
            reason="librosa raised on spectral_flatness/spectral_centroid",
            path=str(audio_path),
            error=str(exc)[:200],
        )
        return {}


def _extract_pitch(
    audio_path: Path, failures: list[str]
) -> dict[str, float]:
    """F0 mean/std + HNR через Parselmouth (Praat wrapper)."""
    try:
        import numpy as np
        import parselmouth
        from parselmouth.praat import call

        sound = parselmouth.Sound(str(audio_path))
        pitch = call(sound, "To Pitch", 0.0, 75, 600)
        f0_values = pitch.selected_array["frequency"]
        voiced = f0_values[f0_values > 0]
        if len(voiced) < 5:
            # Легитимный path: unvoiced audio (музыка без голоса, длинная
            # пауза, слишком тихо). Не спамим warning — это ожидаемый случай
            # для non-speech аудио; advisor получит безопасный дефолт.
            log.debug(
                "pitch_extract_insufficient_voiced",
                voiced_frames=len(voiced),
                path=str(audio_path),
            )
            return {}
        pitch_mean = float(np.mean(voiced))
        pitch_std = float(np.std(voiced))

        try:
            harmonicity = call(sound, "To Harmonicity (cc)", 0.01, 75, 0.1, 1.0)
            hnr = call(harmonicity, "Get mean", 0, 0)
            hnr_val = float(hnr) if isinstance(hnr, int | float) else 10.0
        except Exception:
            hnr_val = 10.0
        return {
            "pitch_mean_hz": pitch_mean,
            "pitch_std_hz": pitch_std,
            "hnr_db": hnr_val,
        }
    except Exception as exc:
        failures.append("pitch")
        log.warning(
            "pitch_extract_failed",
            reason="parselmouth Pitch extraction raised",
            path=str(audio_path),
            error=str(exc)[:200],
        )
        return {}


def _extract_vad_gaps(
    audio_path: Path, failures: list[str]
) -> dict[str, float]:
    """Pause distribution stats через silero-vad.

    ``silero_vad.read_audio`` требует torchcodec (torchaudio 2.11+). Читаем
    через soundfile + scipy.resample чтобы обойти зависимость.
    """
    try:
        import numpy as np
        import soundfile as sf
        import torch
        from silero_vad import get_speech_timestamps, load_silero_vad

        data, sr = sf.read(str(audio_path))
        if data.ndim > 1:
            data = np.mean(data, axis=1)
        data = data.astype(np.float32)
        if sr != 16000:
            from scipy.signal import resample_poly

            data = resample_poly(data, 16000, sr).astype(np.float32)

        wav = torch.from_numpy(data)
        model = load_silero_vad()
        speech = get_speech_timestamps(
            wav,
            model,
            sampling_rate=16000,
            threshold=0.5,
            min_silence_duration_ms=150,
        )
        if len(speech) < 2:
            failures.append("vad_gaps")
            log.warning(
                "vad_extract_insufficient_segments",
                reason="silero-vad found <2 speech segments; gap stats impossible",
                speech_segments=len(speech),
                path=str(audio_path),
            )
            return {}

        gaps = []
        total_speech = 0.0
        for i in range(1, len(speech)):
            gap = (speech[i]["start"] - speech[i - 1]["end"]) / 16000.0
            if gap > 0:
                gaps.append(gap)
        for seg in speech:
            total_speech += (seg["end"] - seg["start"]) / 16000.0

        if not gaps:
            return {"speech_duration": float(total_speech)}

        gaps_arr = np.array(gaps)
        mean_gap = float(np.mean(gaps_arr))
        std_gap = float(np.std(gaps_arr))
        max_gap = float(np.max(gaps_arr))

        # Kurtosis (Fisher's definition, >0 = heavier tails than normal)
        if len(gaps) >= 4 and std_gap > 0:
            try:
                from scipy.stats import kurtosis

                kurt = float(kurtosis(gaps_arr, fisher=True, bias=False))
            except Exception:
                # Manual compute (Fisher)
                centered = gaps_arr - mean_gap
                m4 = float(np.mean(centered**4))
                kurt = m4 / (std_gap**4) - 3.0
        else:
            kurt = 0.0

        return {
            "mean_gap": mean_gap,
            "gap_std": std_gap,
            "gap_kurtosis": kurt,
            "max_gap": max_gap,
            "speech_duration": total_speech,
        }
    except Exception as exc:
        failures.append("vad_gaps")
        log.warning(
            "vad_extract_failed",
            reason="silero-vad or soundfile raised during VAD gap extraction",
            path=str(audio_path),
            error=str(exc)[:200],
        )
        return {}


def _extract_rhythm_cv(
    audio_path: Path, failures: list[str]
) -> dict[str, float]:
    """Coefficient of variation inter-onset intervals через librosa."""
    try:
        import librosa
        import numpy as np

        y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
        if len(y) < sr * 2:  # < 2s
            failures.append("rhythm_cv")
            log.warning(
                "rhythm_cv_extract_too_short",
                reason="audio shorter than 2s; IOI analysis skipped",
                samples=len(y),
                sr=sr,
                path=str(audio_path),
            )
            return {}
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
        onsets = librosa.onset.onset_detect(
            onset_envelope=onset_env, sr=sr, units="time"
        )
        if len(onsets) < 3:
            failures.append("rhythm_cv")
            log.warning(
                "rhythm_cv_extract_insufficient_onsets",
                reason="fewer than 3 onsets detected; IOI stats impossible",
                onsets=len(onsets),
                path=str(audio_path),
            )
            return {}
        ioi = np.diff(onsets)
        mean_ioi = float(np.mean(ioi))
        std_ioi = float(np.std(ioi))
        if mean_ioi <= 0:
            failures.append("rhythm_cv")
            log.warning(
                "rhythm_cv_extract_degenerate",
                reason="mean IOI is zero or negative; degenerate onset pattern",
                path=str(audio_path),
            )
            return {}
        cv = std_ioi / mean_ioi
        return {"rhythm_cv": float(cv)}
    except Exception as exc:
        failures.append("rhythm_cv")
        log.warning(
            "rhythm_cv_extract_failed",
            reason="librosa raised during onset/IOI analysis",
            path=str(audio_path),
            error=str(exc)[:200],
        )
        return {}


__all__ = [
    "AudioProfile",
    "extract_audio_profile",
]
