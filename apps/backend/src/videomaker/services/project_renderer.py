"""ProjectRenderer — один ffmpeg subprocess на ProjectGraph + parallel render_many.

Архитектура: для каждого `ProjectGraph` запускаем ОДИН
`asyncio.create_subprocess_exec(*argv)` (без shell, ARG_MAX-safe). Argv
строится `FilterGraphBuilder.build_filter_graph(graph).to_argv()`.

Stdout: парсим `-progress pipe:1` поток (`out_time_us=...`, `frame=...`,
`fps=...`, `progress=continue|end`). Throttle callback'ов до ~500 ms.

Stderr: целиком в буфер. Парсим:
* loudnorm JSON-summary через `parse_loudnorm_summary` (если loudnorm включён)
* regex `Error initializing filter '(\\w+)'` → actionable error с именем
  упавшего фильтра + last 800 chars stderr.

Fallback на `-filter_complex_script <file>` — если итоговый
`filter_complex` > FILTER_COMPLEX_INLINE_LIMIT (защита от ARG_MAX).
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from videomaker.core.logging import get_logger
from videomaker.services.audio_normalizer import (
    AudioNormalizerError,
    LoudnormResult,
    parse_loudnorm_summary,
)
from videomaker.services.filter_graph_builder import (
    CompiledGraph,
    build_filter_graph,
)
from videomaker.services.project_graph import ProjectGraph
from videomaker.services.subprocess_utils import (
    DEFAULT_SUBPROCESS_TIMEOUT_SEC,
    wait_with_timeout,
)

log = get_logger(__name__)

DEFAULT_RENDER_CONCURRENCY = 2
"""Дефолт concurrency. Перекрывается через runtime_settings (Cycle 4.5)."""

FILTER_COMPLEX_INLINE_LIMIT = 100 * 1024
"""Если filter_complex > 100 KB → используем -filter_complex_script (file).

Darwin ARG_MAX = 256 KB. Запас 2.5×.
"""

PROGRESS_THROTTLE_SEC = 0.5
"""Минимальный интервал между вызовами on_progress."""

STDERR_TAIL_CAP = 64 * 1024
"""Потолок кольцевого буфера stderr (используется только хвост[-1200:])."""

_FILTER_INIT_ERROR_RE = re.compile(r"Error initializing filter '([\w_]+)'")
_PROGRESS_KV_RE = re.compile(r"^([a-zA-Z_]+)=([^\n]*)$")


ProgressCallback = Callable[["RenderProgress"], Awaitable[None] | None]


@dataclass(slots=True)
class RenderProgress:
    """Snapshot прогресса одного reel-render."""

    reel_id: str
    out_time_sec: float
    frame: int
    fps: float
    speed: str | None
    bitrate: str | None
    finished: bool


@dataclass(slots=True)
class RenderResult:
    """Результат завершённого render одного reel."""

    reel_id: str
    output_path: Path
    duration_sec: float
    bitrate_bps: int | None
    file_size_bytes: int
    loudnorm: LoudnormResult | None
    wall_time_sec: float


class ProjectRendererError(RuntimeError):
    """Render fault с reel-context для логов и SSE-стрима."""

    def __init__(self, reel_id: str, message: str, *, stderr_tail: str = "") -> None:
        super().__init__(f"reel {reel_id}: {message}")
        self.reel_id = reel_id
        self.message = message
        self.stderr_tail = stderr_tail


class ProjectRenderer:
    """Исполнитель ProjectGraph через одиночный ffmpeg-subprocess.

    Stateless: instance создаётся один раз на job, метод `render_many`
    управляет parallel-исполнением через Semaphore.
    """

    def __init__(
        self,
        *,
        ffmpeg_path: str = "ffmpeg",
        work_dir: Path | None = None,
    ) -> None:
        self._ffmpeg_path = ffmpeg_path
        self._work_dir = work_dir

    async def render(
        self,
        graph: ProjectGraph,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> RenderResult:
        """Один reel: компилирует граф, запускает ffmpeg, возвращает результат."""

        compiled = build_filter_graph(graph)
        argv, script_file = self._build_argv(compiled)
        Path(graph.output_path).parent.mkdir(parents=True, exist_ok=True)

        diag = {k: v for k, v in compiled.diagnostics.items() if k != "reel_id"}
        log.info(
            "project_render_start",
            reel_id=graph.reel_id,
            output=graph.output_path,
            n_inputs=len(compiled.inputs),
            **diag,
        )
        wall_start = time.monotonic()

        stdout_task: asyncio.Task[None] | None = None
        stderr_task: asyncio.Task[str] | None = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_task = asyncio.create_task(
                self._consume_progress(
                    reel_id=graph.reel_id,
                    stream=proc.stdout,
                    on_progress=on_progress,
                ),
                name=f"progress:{graph.reel_id}",
            )
            stderr_task = asyncio.create_task(
                self._consume_stderr(proc.stderr),
                name=f"stderr:{graph.reel_id}",
            )

            try:
                return_code = await wait_with_timeout(
                    proc, timeout_sec=DEFAULT_SUBPROCESS_TIMEOUT_SEC
                )
            except TimeoutError as exc:
                log.error(
                    "project_render_timeout",
                    reel_id=graph.reel_id,
                    timeout_sec=DEFAULT_SUBPROCESS_TIMEOUT_SEC,
                )
                raise ProjectRendererError(
                    graph.reel_id,
                    f"ffmpeg timed out after "
                    f"{DEFAULT_SUBPROCESS_TIMEOUT_SEC:.0f}s, process killed",
                ) from exc
            await stdout_task
            stderr_text = await stderr_task
        finally:
            for task in (stdout_task, stderr_task):
                if task is not None and not task.done():
                    task.cancel()
            if script_file is not None:
                script_file.unlink(missing_ok=True)

        wall_time = round(time.monotonic() - wall_start, 3)
        if return_code != 0:
            tail = stderr_text[-1200:]
            failed_filter = _FILTER_INIT_ERROR_RE.search(stderr_text)
            human = (
                f"ffmpeg failed (rc={return_code})"
                + (f" at filter {failed_filter.group(1)}" if failed_filter else "")
            )
            log.error(
                "project_render_failed",
                reel_id=graph.reel_id,
                rc=return_code,
                wall_time_sec=wall_time,
                stderr_tail=tail,
            )
            raise ProjectRendererError(graph.reel_id, human, stderr_tail=tail)

        loudnorm: LoudnormResult | None = None
        if graph.audio_normalize.enabled:
            try:
                loudnorm = parse_loudnorm_summary(
                    stderr_text, target_lufs=graph.audio_normalize.target_lufs
                )
            except AudioNormalizerError as exc:
                log.warning(
                    "project_render_loudnorm_parse_failed",
                    reel_id=graph.reel_id,
                    error=str(exc),
                )

        output_path = Path(graph.output_path)
        size_bytes = output_path.stat().st_size if output_path.exists() else 0
        duration_sec = sum(c.duration_sec for c in graph.cuts)
        bitrate_bps = (
            int((size_bytes * 8) / duration_sec) if duration_sec > 0 and size_bytes else None
        )

        result = RenderResult(
            reel_id=graph.reel_id,
            output_path=output_path,
            duration_sec=duration_sec,
            bitrate_bps=bitrate_bps,
            file_size_bytes=size_bytes,
            loudnorm=loudnorm,
            wall_time_sec=wall_time,
        )
        log.info(
            "project_render_done",
            reel_id=graph.reel_id,
            wall_time_sec=wall_time,
            file_size_mb=round(size_bytes / (1024 * 1024), 2),
            bitrate_kbps=int(bitrate_bps / 1000) if bitrate_bps else None,
            achieved_lufs=loudnorm.output_integrated_lufs if loudnorm else None,
            within_tolerance=loudnorm.is_within_tolerance if loudnorm else None,
        )
        return result

    async def render_many(
        self,
        graphs: list[ProjectGraph],
        *,
        concurrency: int = DEFAULT_RENDER_CONCURRENCY,
        on_progress: ProgressCallback | None = None,
    ) -> list[RenderResult | BaseException]:
        """Parallel render с `Semaphore(concurrency)` + failure isolation.

        Возвращает результаты в порядке `graphs`. Каждое значение —
        либо `RenderResult`, либо исключение (через `return_exceptions=True`).
        """

        if concurrency < 1:
            raise ValueError(f"concurrency must be >= 1, got {concurrency}")
        sem = asyncio.Semaphore(concurrency)
        wall_start = time.monotonic()

        async def _bounded(g: ProjectGraph) -> RenderResult:
            async with sem:
                return await self.render(g, on_progress=on_progress)

        tasks = [
            asyncio.create_task(_bounded(g), name=f"render:{g.reel_id}") for g in graphs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        wall_total = round(time.monotonic() - wall_start, 2)

        successes = sum(1 for r in results if isinstance(r, RenderResult))
        failures = len(results) - successes
        log.info(
            "project_render_many_done",
            total=len(graphs),
            successes=successes,
            failures=failures,
            concurrency=concurrency,
            wall_total_sec=wall_total,
        )
        return results

    def _build_argv(
        self, compiled: CompiledGraph
    ) -> tuple[list[str], Path | None]:
        """Возвращает argv + опциональный путь к temp filter_complex_script."""

        if len(compiled.filter_complex) <= FILTER_COMPLEX_INLINE_LIMIT:
            return compiled.to_argv(ffmpeg_path=self._ffmpeg_path), None

        # ARG_MAX-safe fallback: filter_complex в файле.
        reel_id_str = str(compiled.diagnostics.get("reel_id", "reel"))
        suffix = f".{reel_id_str}.filter"
        fd, tmp_path = tempfile.mkstemp(
            suffix=suffix, prefix="videomaker_", dir=self._work_dir
        )
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(compiled.filter_complex)
        script_file = Path(tmp_path)

        argv: list[str] = [
            self._ffmpeg_path,
            "-y",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "info",
            "-progress",
            "pipe:1",
        ]
        for inp in compiled.inputs:
            argv.extend(["-i", str(inp)])
        argv.extend(["-filter_complex_script", str(script_file)])
        argv.extend(["-map", compiled.output_video_label])
        argv.extend(["-map", compiled.output_audio_label])
        argv.extend(compiled.extra_args)
        argv.append(str(compiled.output_path))

        log.info(
            "project_render_filter_script_used",
            reel_id=compiled.diagnostics.get("reel_id"),
            script=str(script_file),
            filter_complex_chars=len(compiled.filter_complex),
        )
        return argv, script_file

    async def _consume_progress(
        self,
        *,
        reel_id: str,
        stream: asyncio.StreamReader | None,
        on_progress: ProgressCallback | None,
    ) -> None:
        if stream is None:
            return
        last_emit = 0.0
        state: dict[str, str] = {}
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode(errors="replace").strip()
            if not decoded:
                continue
            match = _PROGRESS_KV_RE.match(decoded)
            if match is None:
                continue
            key, value = match.group(1), match.group(2).strip()
            state[key] = value
            if key != "progress":
                continue
            now = time.monotonic()
            finished = value == "end"
            if not finished and now - last_emit < PROGRESS_THROTTLE_SEC:
                continue
            last_emit = now
            snapshot = _build_render_progress(reel_id=reel_id, state=state, finished=finished)
            if on_progress is not None:
                outcome = on_progress(snapshot)
                if asyncio.iscoroutine(outcome):
                    await outcome
            if finished:
                return

    async def _consume_stderr(
        self, stream: asyncio.StreamReader | None
    ) -> str:
        if stream is None:
            return ""
        # Используется только хвост (stderr_text[-1200:]). Держим кольцевой
        # буфер последних STDERR_TAIL_CAP байт, чтобы патологический инпут,
        # сыплющий ошибки на каждый кадр, не раздул память worker'а.
        buf = bytearray()
        while True:
            chunk = await stream.read(64 * 1024)
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) > STDERR_TAIL_CAP:
                del buf[:-STDERR_TAIL_CAP]
        return bytes(buf).decode("utf-8", errors="replace")


def _build_render_progress(
    *, reel_id: str, state: dict[str, str], finished: bool
) -> RenderProgress:
    out_time_us = state.get("out_time_us") or state.get("out_time_ms") or "0"
    try:
        out_time_sec = int(out_time_us) / 1_000_000.0
    except ValueError:
        out_time_sec = 0.0
    try:
        frame = int(state.get("frame", "0"))
    except ValueError:
        frame = 0
    try:
        fps = float(state.get("fps", "0") or "0")
    except ValueError:
        fps = 0.0
    return RenderProgress(
        reel_id=reel_id,
        out_time_sec=out_time_sec,
        frame=frame,
        fps=fps,
        speed=state.get("speed"),
        bitrate=state.get("bitrate"),
        finished=finished,
    )


__all__ = [
    "DEFAULT_RENDER_CONCURRENCY",
    "FILTER_COMPLEX_INLINE_LIMIT",
    "ProgressCallback",
    "ProjectRenderer",
    "ProjectRendererError",
    "RenderProgress",
    "RenderResult",
]
