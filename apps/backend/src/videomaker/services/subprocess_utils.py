"""Утилиты для безопасного ожидания ffmpeg/ffprobe-подпроцессов.

Любой `proc.communicate()` / `proc.wait()` без таймаута подвешивает pipeline
навсегда, если ffmpeg зацикливается на патологическом инпуте. Эти хелперы
оборачивают ожидание в таймаут с эскалацией terminate→kill и гарантированным
cleanup, по образцу `face_tracker`/`audio_normalizer`.
"""

from __future__ import annotations

import asyncio
import contextlib

#: Дефолтный потолок ожидания одного ffmpeg/ffprobe-вызова. Probe/thumbnail
#: укладываются в секунды; рендер многочасового видео — в десятки минут. Берём
#: с большим запасом, чтобы резать только реально зависшие процессы.
DEFAULT_SUBPROCESS_TIMEOUT_SEC = 3600.0

#: Короткий таймаут для лёгких вызовов (probe, thumbnail, единичный кадр).
PROBE_SUBPROCESS_TIMEOUT_SEC = 300.0


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    """terminate→(grace)→kill, не падает если процесс уже завершился."""

    if proc.returncode is not None:
        return
    try:
        proc.terminate()
    except ProcessLookupError:
        return
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(proc.wait(), timeout=5.0)
        return
    try:
        proc.kill()
    except ProcessLookupError:
        return
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(proc.wait(), timeout=5.0)


async def communicate_with_timeout(
    proc: asyncio.subprocess.Process,
    *,
    timeout_sec: float = DEFAULT_SUBPROCESS_TIMEOUT_SEC,
) -> tuple[bytes, bytes]:
    """`proc.communicate()` с таймаутом и kill-эскалацией.

    На таймаут или отмену ожидания (`CancelledError`) дочерний процесс
    принудительно завершается, чтобы не утёк осиротевший ffmpeg.
    """

    try:
        return await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except TimeoutError:
        await _terminate_process(proc)
        raise
    except asyncio.CancelledError:
        await _terminate_process(proc)
        raise


async def wait_with_timeout(
    proc: asyncio.subprocess.Process,
    *,
    timeout_sec: float = DEFAULT_SUBPROCESS_TIMEOUT_SEC,
) -> int:
    """`proc.wait()` с таймаутом и kill-эскалацией. Возвращает returncode."""

    try:
        return await asyncio.wait_for(proc.wait(), timeout=timeout_sec)
    except TimeoutError:
        await _terminate_process(proc)
        raise
    except asyncio.CancelledError:
        await _terminate_process(proc)
        raise


__all__ = [
    "DEFAULT_SUBPROCESS_TIMEOUT_SEC",
    "PROBE_SUBPROCESS_TIMEOUT_SEC",
    "communicate_with_timeout",
    "wait_with_timeout",
]
