"""ffmpeg loudnorm wrapper: single- и two-pass EBU R128 нормализация.

**Single-pass**: один прогон с фильтром
`loudnorm=I=...:TP=...:LRA=...:print_format=json`. Точность integrated
LUFS ±2 LU от target.

**Two-pass** (TIER1-#6, платформенный spec -14 LUFS TikTok/Reels):
1. `measure_source_loudness(...)` — отдельный audio-only ffmpeg на
   source_path, парсит input_i/tp/lra/thresh/target_offset.
2. Главный рендер с `linear=true` и measured_* параметрами (см.
   `_build_loudnorm_stage` в filter_graph_builder). Точность ±1 LU.

Measurement делается ОДИН раз на job (на proxy-источнике), результат
шарится между всеми reels — быстро и точно для большинства сценариев.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

from videomaker.core.logging import get_logger

log = get_logger(__name__)

_LOUDNORM_JSON_RE = re.compile(
    r"\{[^{}]*?\"target_offset\"[^{}]*?\}",
    re.DOTALL,
)


@dataclass(slots=True)
class LoudnormResult:
    """Распарсенный summary с фактическими значениями после нормализации."""

    target_lufs: float
    input_integrated_lufs: float
    input_true_peak_dbtp: float
    output_integrated_lufs: float
    output_true_peak_dbtp: float
    output_lra: float
    target_offset_db: float
    normalization_type: str

    @property
    def is_within_tolerance(self) -> bool:
        """`True` если фактический output_i в пределах ±2 LU от target."""
        return abs(self.output_integrated_lufs - self.target_lufs) <= 2.0


def parse_loudnorm_summary(stderr_text: str, *, target_lufs: float) -> LoudnormResult:
    """Извлекает JSON-блок loudnorm из stderr и парсит в LoudnormResult.

    Если блока нет (например ffmpeg не нашёл аудиопоток) - поднимаем
    AudioNormalizerError с поясняющим сообщением.
    """

    match = _LOUDNORM_JSON_RE.search(stderr_text)
    if match is None:
        raise AudioNormalizerError(
            "loudnorm summary not found in ffmpeg stderr - возможно нет "
            f"аудиопотока во входе. Last 400 chars: {stderr_text[-400:]}"
        )
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise AudioNormalizerError(
            f"failed to parse loudnorm JSON: {exc}; raw: {match.group(0)[:200]}"
        ) from exc

    return LoudnormResult(
        target_lufs=target_lufs,
        input_integrated_lufs=float(data["input_i"]),
        input_true_peak_dbtp=float(data["input_tp"]),
        output_integrated_lufs=float(data["output_i"]),
        output_true_peak_dbtp=float(data["output_tp"]),
        output_lra=float(data["output_lra"]),
        target_offset_db=float(data["target_offset"]),
        normalization_type=str(data["normalization_type"]),
    )


class AudioNormalizerError(RuntimeError):
    pass


@dataclass(slots=True, frozen=True)
class MeasuredLoudness:
    """Результат measurement-pass EBU R128 (входные параметры для pass 2)."""

    input_i: float
    input_tp: float
    input_lra: float
    input_thresh: float
    target_offset: float


def parse_measured_loudness(stderr_text: str) -> MeasuredLoudness:
    """Извлекает measurement-блок loudnorm из stderr ffmpeg."""

    match = _LOUDNORM_JSON_RE.search(stderr_text)
    if match is None:
        raise AudioNormalizerError(
            "measurement loudnorm summary not found in ffmpeg stderr. "
            f"Last 400 chars: {stderr_text[-400:]}"
        )
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise AudioNormalizerError(
            f"failed to parse measurement JSON: {exc}; raw: {match.group(0)[:200]}"
        ) from exc
    return MeasuredLoudness(
        input_i=float(data["input_i"]),
        input_tp=float(data["input_tp"]),
        input_lra=float(data["input_lra"]),
        input_thresh=float(data["input_thresh"]),
        target_offset=float(data["target_offset"]),
    )


async def measure_source_loudness(
    source_path: Path,
    *,
    target_lufs: float,
    true_peak_dbtp: float,
    lra: float,
    ffmpeg_path: str = "ffmpeg",
    timeout_sec: float = 180.0,
) -> MeasuredLoudness | None:
    """Measurement-pass: ffmpeg-прогон только на audio-поток source_path.

    Быстрый (×0.1-0.3 длительности аудио на M-чипе без video decode).
    Результат используется для pass 2 с ``linear=true`` в главном рендере.

    Возвращает ``None`` при любой ошибке (ffmpeg nonzero rc, нет audio,
    битый JSON) — вызывающий код должен fallback'нуться на single-pass.
    """

    if not source_path.exists():
        log.warning("measure_source_loudness_missing_source", path=str(source_path))
        return None

    argv = [
        ffmpeg_path,
        "-y",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "info",
        "-i",
        str(source_path),
        "-af",
        (
            f"loudnorm=I={target_lufs}:TP={true_peak_dbtp}:"
            f"LRA={lra}:print_format=json"
        ),
        "-vn",
        "-f",
        "null",
        "-",
    ]
    log.info(
        "measure_source_loudness_start",
        path=str(source_path),
        target_lufs=target_lufs,
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_sec
            )
        except TimeoutError:
            proc.kill()
            await proc.wait()
            log.warning(
                "measure_source_loudness_timeout",
                path=str(source_path),
                timeout_sec=timeout_sec,
            )
            return None
    except FileNotFoundError:
        log.warning("measure_source_loudness_ffmpeg_missing", ffmpeg_path=ffmpeg_path)
        return None

    stderr_text = stderr_bytes.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        log.warning(
            "measure_source_loudness_ffmpeg_failed",
            rc=proc.returncode,
            stderr_tail=stderr_text[-400:],
        )
        return None

    try:
        measured = parse_measured_loudness(stderr_text)
    except AudioNormalizerError as exc:
        log.warning("measure_source_loudness_parse_failed", error=str(exc))
        return None

    log.info(
        "measure_source_loudness_done",
        input_i=measured.input_i,
        input_tp=measured.input_tp,
        input_lra=measured.input_lra,
        target_offset=measured.target_offset,
    )
    return measured


__all__ = [
    "AudioNormalizerError",
    "LoudnormResult",
    "MeasuredLoudness",
    "measure_source_loudness",
    "parse_loudnorm_summary",
    "parse_measured_loudness",
]
