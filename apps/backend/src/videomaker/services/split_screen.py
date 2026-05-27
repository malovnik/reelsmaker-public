"""Split-screen post-process pass — вертикальный композит 9:16 TikTok/Shorts.

Берёт reel BODY (верх) и companion (низ), производит новый mp4 со стеком.
Companion loop'ится до длины рилса через -stream_loop -1.
Audio — только с [0] (рилс-body).

ВАЖНО: split-screen выполняется ОДНИМ ffmpeg-проходом через
``render_split_single_pass``. Inner body-chain (cuts → face crop → concat →
loudnorm → optional intro/outro concat) собирается ``build_filter_graph``
и расширяется vstack'ом с companion + optional subtitles overlay поверх
полного 1080×1920 canvas. Intro/outro при этом остаются полноэкранными
(они отдельные inputs в compiled graph), а vstack применяется только к
reel-body порции — заставки не попадают в верхнюю половину split-canvas'а.
"""

# ─── Architecture note (2026-04-22 research) ──────────────────────────────
# Single-pass split-screen uses CompiledGraph.filter_complex (from
# build_filter_graph) as inner body chain. CompiledGraph:
#   - filter_complex: str ending with labels [output_video_label] / [output_audio_label]
#   - inputs: list[Path] (source + optional intro + optional outro)
# render_split_single_pass (below) extends filter_complex with:
#   - companion input at index len(inputs), via -stream_loop -1 at argv level
#   - vstack of [output_video_label] + scaled companion
#   - optional subtitles=ass overlay поверх full canvas
# ──────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from videomaker.core.logging import get_logger
from videomaker.models.post_production import SplitScreenConfig
from videomaker.services.filter_graph_builder import build_filter_graph
from videomaker.services.project_graph import ProjectGraph
from videomaker.services.project_renderer import FILTER_COMPLEX_INLINE_LIMIT
from videomaker.services.subprocess_utils import (
    DEFAULT_SUBPROCESS_TIMEOUT_SEC,
    communicate_with_timeout,
)

log = get_logger(__name__)

CANVAS_WIDTH: int = 1080
CANVAS_HEIGHT: int = 1920


class SplitScreenError(RuntimeError):
    """Ошибка при выполнении split-screen ffmpeg pass."""


def _round_even(value: float) -> int:
    """Округлить к ближайшему чётному числу вниз.

    HEVC encoder (hevc_videotoolbox на Apple Silicon) требует чётные
    ширину и высоту. Нечётные dimensions в cascade pad filter ломают
    pipeline: ``pad=1080:967:...`` на input 1080x1920 после scale выдаёт
    'Padded dimensions cannot be smaller than input dimensions'.

    Используем ``int(x) & ~1`` — сбрасывает младший бит, гарантированно
    чётное. Округляем ВНИЗ чтобы rect не выходил за canvas boundary.
    """
    return int(value) & ~1


def _compute_panels(
    config: SplitScreenConfig,
) -> tuple[tuple[int, int, int, int], tuple[int, int, int, int]]:
    """Вычислить прямоугольники главного и companion слоёв в пикселях canvas'а.

    Transform = source of truth для ПОЗИЦИИ панели на canvas'е.
    ``*_fit_mode`` управляет только scale поведением СОДЕРЖИМОГО внутри
    rect (letterbox/cover/manual-content), не положением rect'а.

    Это матчит поведение SplitScreenPreviewEditor в UI: юзер двигает
    рамки → transform обновляется → рендер берёт точно эту рамку.
    Editor = render 1:1 для позиции; внутри рамки fit_mode определяет
    letterbox (contain) или cover (fill + crop по центру).

    Все dimensions округляются к чётным — требование HEVC encoder.

    Returns:
        (main_rect, comp_rect) где rect = (x, y, w, h) в пикселях canvas'а.
    """
    t = config.main_transform
    main_rect = (
        _round_even(t.x_pct * CANVAS_WIDTH / 100),
        _round_even(t.y_pct * CANVAS_HEIGHT / 100),
        _round_even(t.width_pct * CANVAS_WIDTH / 100),
        _round_even(t.height_pct * CANVAS_HEIGHT / 100),
    )

    c = config.companion_transform
    comp_rect = (
        _round_even(c.x_pct * CANVAS_WIDTH / 100),
        _round_even(c.y_pct * CANVAS_HEIGHT / 100),
        _round_even(c.width_pct * CANVAS_WIDTH / 100),
        _round_even(c.height_pct * CANVAS_HEIGHT / 100),
    )

    return main_rect, comp_rect


def _scale_expression(width: int, height: int, mode: str) -> str:
    """Построить строку ffmpeg scale/pad/crop фильтра для заданного режима.

    Args:
        width: целевая ширина панели в пикселях.
        height: целевая высота панели в пикселях.
        mode: один из 'fit', 'fill', 'manual'.

    Returns:
        Строка ffmpeg filter expression (без завершающего пробела/запятой).

    Notes:
        - ``fit`` и ``manual`` — scale + pad (letterbox). Изображение вписывается
          в панель полностью, чёрные полосы по необходимости. Для ``manual``
          семантика "user-positioned letterbox": frontend SplitScreenPreviewEditor
          отрисовывает source через object-fit:contain, backend должен делать
          то же через scale+pad — иначе preview ≠ render. Fix 2026-04-22.
        - ``fill`` — scale + crop (cover). Заполняет панель полностью,
          overflow crop'ается по центру.
    """
    if mode in ("fit", "manual"):
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
        )
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )


def _escape_ass_path(path: Path) -> str:
    """Экранировать абсолютный путь к ASS-файлу для ffmpeg subtitles-filter.

    ffmpeg filter syntax использует ``:`` и ``'`` как служебные символы,
    поэтому в значении ``subtitles=<path>`` их нужно эскейпить. Также
    приводим разделители к forward slash — ffmpeg корректно их понимает
    на всех ОС, а бэкслэш в Windows-путях ломает парсинг.
    """
    s = str(path.absolute()).replace("\\", "/")
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    return s








async def render_split_single_pass(
    *,
    graph: ProjectGraph,
    companion_path: Path,
    split_config: SplitScreenConfig,
    intro_path: Path | None = None,
    outro_path: Path | None = None,
    subtitle_ass_path: Path | None = None,
    ffmpeg_path: str = "ffmpeg",
) -> None:
    """Single-pass split-screen render — один ffmpeg subprocess из source → final.

    Берёт RAW source через ``graph`` (body chain — cuts, scale, zoom,
    loudnorm) и в одном ``filter_complex`` делает:

      [body] + [companion] → vstack (split 1080×1920) → [split_body]
      [intro][split_body][outro] → concat → [full]          (если intro/outro)
      [full] → subtitles → [out_v]                          (если ASS)

    ВАЖНО — intro и outro **ПОЛНОЭКРАННЫЕ**: они НЕ проходят через vstack
    с companion, а склеиваются отдельно до/после split-body блока. Это
    matches legacy concat_with_intro_outro семантике: заставка и аутро
    выглядят полноразмерно 1080×1920, split применяется только к body.

    Вызывающий код должен передавать ``graph`` с:
      - ``graph.intro_path = None``, ``graph.outro_path = None``
        (т.е. build_project_graph(exclude_post_production=True)) —
        чтобы Stage F concat внутри build_filter_graph не включил
        intro/outro в body stream. intro/outro приходят в этой функции
        как отдельные аргументы и добавляются как новые ffmpeg inputs.
      - ``graph.subtitle_path = None`` — subtitle burn-in Stage C
        пропускается; субтитры приходят через ``subtitle_ass_path``
        и вжигаются ПОВЕРХ full canvas после concat.

    Args:
        graph: ProjectGraph от build_project_graph(..., exclude_post_production=True,
            exclude_subtitles=True). Body-only chain без intro/outro/subs.
        companion_path: путь к companion-видео (loop через -stream_loop -1).
        split_config: конфигурация split (panels, transforms, ratio, fit_modes).
        intro_path: опциональный intro video (fullscreen 1080×1920 до body).
        outro_path: опциональный outro video (fullscreen 1080×1920 после body).
        subtitle_ass_path: опциональный ASS-файл subtitles; применяется после
            intro/outro concat так что center-позиция субтитров = центр
            финального 1080×1920 кадра.
        ffmpeg_path: путь к ffmpeg binary.

    Raises:
        SplitScreenError: валидация или ffmpeg non-zero rc.
    """
    if not companion_path.exists():
        raise SplitScreenError(f"companion_path не найден: {companion_path}")
    if intro_path is not None and not intro_path.exists():
        raise SplitScreenError(f"intro_path не найден: {intro_path}")
    if outro_path is not None and not outro_path.exists():
        raise SplitScreenError(f"outro_path не найден: {outro_path}")
    if subtitle_ass_path is not None and not subtitle_ass_path.exists():
        raise SplitScreenError(
            f"subtitle_ass_path не найден: {subtitle_ass_path}"
        )

    compiled = build_filter_graph(graph)

    # Input layout в argv (order matters — filter labels используют индексы):
    #   0: source (уже в compiled.inputs)
    #   1: companion
    #   2: intro (optional)
    #   3: outro (optional, или 2 если intro отсутствует)
    base_input_count = len(compiled.inputs)
    companion_input_idx = base_input_count
    next_idx = base_input_count + 1
    intro_input_idx: int | None = None
    outro_input_idx: int | None = None
    if intro_path is not None:
        intro_input_idx = next_idx
        next_idx += 1
    if outro_path is not None:
        outro_input_idx = next_idx
        next_idx += 1

    (mx, my, mw, mh), (cx, cy, cw, ch) = _compute_panels(split_config)
    main_scale = _scale_expression(mw, mh, split_config.main_fit_mode)
    comp_scale = _scale_expression(cw, ch, split_config.companion_fit_mode)

    body_v = compiled.output_video_label  # "[v_main]" или "[v_subbed]" etc
    body_a = compiled.output_audio_label  # "[a_final]" после loudnorm

    # Split composite: body + companion → [split_v]
    split_parts: list[str] = [
        f"color=c=black:s={CANVAS_WIDTH}x{CANVAS_HEIGHT}:d=1[split_bg]",
        f"{body_v}{main_scale}[split_main]",
        f"[{companion_input_idx}:v]{comp_scale},setpts=PTS-STARTPTS[split_comp]",
        f"[split_bg][split_main]overlay=x={mx}:y={my}:shortest=0[split_with_main]",
        f"[split_with_main][split_comp]overlay=x={cx}:y={cy}:shortest=1[split_v]",
    ]

    # Intro/outro concat POST-split. Intro/outro нормализуются к canvas
    # (scale к 1080×1920 с preserving aspect + pad если нужно, fps, setsar)
    # — повторяет паттерн _normalize_extra в filter_graph_builder.
    preset = graph.export_preset
    scale_filter = preset.scale_filter  # pre-composed scale+pad expression
    pre_concat_label = "[split_v]"
    pre_concat_audio_label = body_a
    if intro_input_idx is not None or outro_input_idx is not None:
        concat_v_parts: list[str] = []
        concat_a_parts: list[str] = []
        n_segments = 1  # split_v body middle
        if intro_input_idx is not None:
            split_parts.append(
                f"[{intro_input_idx}:v]{scale_filter},fps={preset.fps},setsar=1[v_intro]"
            )
            split_parts.append(
                f"[{intro_input_idx}:a]aresample=async=1[a_intro]"
            )
            concat_v_parts.append("[v_intro]")
            concat_a_parts.append("[a_intro]")
            n_segments += 1
        concat_v_parts.append(pre_concat_label)
        concat_a_parts.append(pre_concat_audio_label)
        if outro_input_idx is not None:
            split_parts.append(
                f"[{outro_input_idx}:v]{scale_filter},fps={preset.fps},setsar=1[v_outro]"
            )
            split_parts.append(
                f"[{outro_input_idx}:a]aresample=async=1[a_outro]"
            )
            concat_v_parts.append("[v_outro]")
            concat_a_parts.append("[a_outro]")
            n_segments += 1
        concat_inputs = "".join(
            v + a for v, a in zip(concat_v_parts, concat_a_parts, strict=True)
        )
        split_parts.append(
            f"{concat_inputs}concat=n={n_segments}:v=1:a=1[full_v][full_a]"
        )
        pre_concat_label = "[full_v]"
        pre_concat_audio_label = "[full_a]"

    # Subtitles overlay ПОСЛЕ concat — center-позиция = центр final canvas.
    if subtitle_ass_path is not None:
        escaped = _escape_ass_path(subtitle_ass_path)
        split_parts.append(
            f"{pre_concat_label}subtitles={escaped}[out_v]"
        )
        final_video_label = "[out_v]"
    else:
        # Rename последнего video label на [out_v] через null filter для
        # единообразного -map [out_v] в argv.
        split_parts.append(f"{pre_concat_label}null[out_v]")
        final_video_label = "[out_v]"

    full_filter_complex = compiled.filter_complex + ";" + ";".join(split_parts)

    argv: list[str] = [
        ffmpeg_path,
        "-y",
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "warning",
    ]
    for input_path in compiled.inputs:
        argv.extend(["-i", str(input_path)])
    argv.extend(["-stream_loop", "-1", "-i", str(companion_path)])
    if intro_path is not None:
        argv.extend(["-i", str(intro_path)])
    if outro_path is not None:
        argv.extend(["-i", str(outro_path)])

    filter_script_path: Path | None = None
    if len(full_filter_complex) > FILTER_COMPLEX_INLINE_LIMIT:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".filtergraph",
            delete=False,
            encoding="utf-8",
        ) as fh:
            fh.write(full_filter_complex)
            filter_script_path = Path(fh.name)
        argv.extend(["-filter_complex_script", str(filter_script_path)])
    else:
        argv.extend(["-filter_complex", full_filter_complex])

    argv.extend(["-map", final_video_label])
    argv.extend(["-map", pre_concat_audio_label])
    argv.extend(compiled.extra_args)
    argv.append(str(compiled.output_path))

    log.info(
        "split_screen.single_pass.start",
        source=str(compiled.inputs[0]),
        companion=str(companion_path),
        intro=str(intro_path) if intro_path else None,
        outro=str(outro_path) if outro_path else None,
        cuts=len(graph.cuts),
        main_fit_mode=split_config.main_fit_mode,
        companion_fit_mode=split_config.companion_fit_mode,
        split_ratio=split_config.split_ratio,
        burn_subtitles=subtitle_ass_path is not None,
        filter_chars=len(full_filter_complex),
        filter_script=str(filter_script_path) if filter_script_path else None,
        out=str(compiled.output_path),
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr_bytes = await communicate_with_timeout(
                proc, timeout_sec=DEFAULT_SUBPROCESS_TIMEOUT_SEC
            )
        except TimeoutError as exc:
            raise SplitScreenError(
                f"single-pass split-screen timed out after "
                f"{DEFAULT_SUBPROCESS_TIMEOUT_SEC:.0f}s, process killed"
            ) from exc
        rc = proc.returncode

        if rc != 0:
            stderr_text = stderr_bytes.decode(errors="replace")
            raise SplitScreenError(
                f"single-pass split-screen failed (code {rc}): {stderr_text[:500]}"
            )
    finally:
        if filter_script_path is not None and filter_script_path.exists():
            filter_script_path.unlink()

    log.info(
        "split_screen.single_pass.done",
        out=str(compiled.output_path),
        returncode=rc,
    )
