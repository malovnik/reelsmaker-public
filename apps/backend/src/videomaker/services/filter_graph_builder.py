"""FilterGraphBuilder — pure-function компиляция `ProjectGraph` в ffmpeg argv.

`build_filter_graph(graph)` возвращает `CompiledGraph` с готовыми:
* `inputs` — список `-i <path>` (source + intro? + outro?)
* `filter_complex` — одна строка для `-filter_complex` (или, если >100 KB,
  её можно записать в file и подать через `-filter_complex_script`)
* `output_video_label` / `output_audio_label` — для `-map`
* `extra_args` — encoder/output args (codec, bitrate, faststart, etc.)

Stages (опускаются если данных нет):
* A — per-cut trim+scale+concat (+ 12.5ms audio afade in/out на стыках)
* B — zoom split+crop+concat
* C — subtitles burn
* F — concat с intro/outro
* G — one- или two-pass loudnorm

Никаких subprocess-вызовов. Тестируется через подстроки в строке.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from videomaker.services.media import ffmpeg_escape_path
from videomaker.services.project_graph import (
    AudioNormalizeSpec,
    BaseCropCommandSpec,
    ExportPresetSpec,
    ProjectGraph,
    ZoomCommandSpec,
    ZoomPlanSpec,
)


@dataclass(slots=True)
class CompiledGraph:
    """Результат компиляции ProjectGraph → конкретные ffmpeg argv-куски."""

    inputs: list[Path]
    filter_complex: str
    output_video_label: str
    output_audio_label: str
    extra_args: list[str]
    output_path: Path
    diagnostics: dict[str, object] = field(default_factory=dict)

    def to_argv(self, *, ffmpeg_path: str = "ffmpeg") -> list[str]:
        """Полный argv для `asyncio.create_subprocess_exec`.

        Включает `-y -hide_banner -nostdin -loglevel info -progress pipe:1`
        (renderer парсит progress-stream из stdout).
        """

        argv: list[str] = [
            ffmpeg_path,
            "-y",
            "-hide_banner",
            "-nostdin",
            "-loglevel",
            "info",
            "-progress",
            "pipe:1",
        ]
        for input_path in self.inputs:
            argv.extend(["-i", str(input_path)])
        argv.extend(["-filter_complex", self.filter_complex])
        argv.extend(["-map", self.output_video_label])
        argv.extend(["-map", self.output_audio_label])
        argv.extend(self.extra_args)
        argv.append(str(self.output_path))
        return argv


def build_filter_graph(graph: ProjectGraph) -> CompiledGraph:
    """Pure-function компиляция декларативного `ProjectGraph` в `CompiledGraph`."""

    inputs: list[Path] = [Path(graph.source_path)]
    intro_input_idx: int | None = None
    outro_input_idx: int | None = None
    if graph.intro_path is not None:
        inputs.append(Path(graph.intro_path))
        intro_input_idx = len(inputs) - 1
    if graph.outro_path is not None:
        inputs.append(Path(graph.outro_path))
        outro_input_idx = len(inputs) - 1

    parts: list[str] = []
    preset = graph.export_preset
    base_crop = graph.base_crop_plan
    use_base_crop = base_crop is not None and not base_crop.is_no_op

    # ── Stage A: per-cut trim / (face-aware base crop | preset scale) / fps+setsar ──
    cut_video_labels: list[str] = []
    cut_audio_labels: list[str] = []

    # TIER2-#15: если любой cut имеет отдельное audio-окно (J/L-cut),
    # video и audio сводятся ДВУМЯ отдельными concat, т.к. длительности
    # per-cut audio vs video расходятся. Суммарные длительности v и a
    # равны (инвариант jl_cut_planner), поэтому финальный [v_main]/[a_main]
    # синхронны. Если же все cuts hard (no J/L), оставляем классический
    # concat=n:v=1:a=1 — регрессии на проектах без JL нет.
    has_jl_cuts = any(c.has_separate_audio_window for c in graph.cuts)

    for i, cut in enumerate(graph.cuts):
        v_label = f"vc{i}"
        a_label = f"ac{i}"
        if use_base_crop:
            assert base_crop is not None  # pyright narrowing
            crop_expr = _base_crop_command_to_expr(
                base_crop.commands[i],
                crop_w=base_crop.crop_width,
                crop_h=base_crop.crop_height,
                source_w=base_crop.source_width,
                source_h=base_crop.source_height,
            )
            chain = (
                f"{crop_expr},"
                f"scale={preset.width}:{preset.height},"
                f"fps={preset.fps},setsar=1"
            )
        elif graph.preserve_source_res:
            # Split-screen ветка: body выходит в source aspect. Split panel
            # сам letterbox'ит в main_rect через _scale_expression, что
            # matches editor object-fit:contain. Иначе (scale_filter) body
            # уже 9:16 → panel letterbox 9:16 в 9:8 → полосы слева/справа.
            chain = f"fps={preset.fps},setsar=1"
        else:
            chain = f"{preset.scale_filter},fps={preset.fps},setsar=1"
        parts.append(
            f"[0:v]trim=start={cut.source_start_sec:.3f}:end={cut.source_end_sec:.3f},"
            f"setpts=PTS-STARTPTS,{chain}[{v_label}]"
        )
        # TIER1-#4: 12.5ms afade in/out на обоих концах cut'а → эффективный
        # 25ms crossfade на стыках (fade-out прошлого + fade-in следующего).
        # Убирает click-артефакты от abrupt амплитудных скачков на hard-cut.
        a_start = cut.audio_start_sec
        a_end = cut.audio_end_sec
        a_duration = a_end - a_start
        audio_chain = _audio_cut_chain(a_start, a_end, a_duration)
        parts.append(f"[0:a]{audio_chain}[{a_label}]")
        cut_video_labels.append(v_label)
        cut_audio_labels.append(a_label)

    n_cuts = len(graph.cuts)
    if has_jl_cuts:
        # Раздельные concat для video и audio.
        vconcat_inputs = "".join(f"[{v}]" for v in cut_video_labels)
        aconcat_inputs = "".join(f"[{a}]" for a in cut_audio_labels)
        parts.append(f"{vconcat_inputs}concat=n={n_cuts}:v=1:a=0[v_main]")
        parts.append(f"{aconcat_inputs}concat=n={n_cuts}:v=0:a=1[a_main]")
    else:
        concat_inputs_a = "".join(
            f"[{v}][{a}]" for v, a in zip(cut_video_labels, cut_audio_labels, strict=True)
        )
        parts.append(
            f"{concat_inputs_a}concat=n={n_cuts}:v=1:a=1[v_main][a_main]"
        )
    current_video = "v_main"
    current_audio = "a_main"

    # ── Stage B: zoom split → per-cmd crop+scale → concat ───────────────
    if graph.zoom_plan is not None and not graph.zoom_plan.is_empty:
        current_video = _build_zoom_stage(parts, graph.zoom_plan, current_video)

    # ── Stage B+: motion effects (punch-in zoom, Ken Burns) ─────────────
    # T10.3 + T10.7 — применяется после Stage B zoom (face tracking)
    # и до Stage C subtitles burn. Обычно это zoompan expression.
    if graph.motion_filter_expr:
        parts.append(
            f"[{current_video}]{graph.motion_filter_expr}[v_motion]"
        )
        current_video = "v_motion"

    # ── Stage C: subtitles burn ─────────────────────────────────────────
    if graph.subtitle_path is not None:
        escaped = ffmpeg_escape_path(Path(graph.subtitle_path))
        parts.append(f"[{current_video}]subtitles={escaped}[v_subbed]")
        current_video = "v_subbed"

    # ── Stage D: pluggable video effects (bw / vignette / lut / …) ──────
    # Итерируем `graph.video_effects` в порядке `EFFECTS_REGISTRY`.
    # Каждый эффект — собственный chain link с labeled output.
    for i, effect in enumerate(graph.video_effects):
        next_label = f"v_fx{i}"
        parts.append(
            f"[{current_video}]{effect.filter_expr}[{next_label}]"
        )
        current_video = next_label

    # ── Stage F: concat с intro/outro ───────────────────────────────────
    if intro_input_idx is not None or outro_input_idx is not None:
        current_video, current_audio = _build_extras_stage(
            parts=parts,
            intro_input_idx=intro_input_idx,
            outro_input_idx=outro_input_idx,
            video_label=current_video,
            audio_label=current_audio,
            preset=preset,
        )

    # ── Stage G: loudnorm ───────────────────────────────────────────────
    if graph.audio_normalize.enabled:
        current_audio = _build_loudnorm_stage(parts, graph.audio_normalize, current_audio)

    filter_complex = ";".join(parts)
    extra_args = _build_encoder_args(preset)

    diagnostics: dict[str, object] = {
        "reel_id": graph.reel_id,
        "n_cuts": n_cuts,
        "has_base_crop": use_base_crop,
        "base_crop_dims": (
            f"{base_crop.crop_width}x{base_crop.crop_height}" if base_crop else None
        ),
        "has_zoom": graph.zoom_plan is not None and not graph.zoom_plan.is_empty,
        "zoom_commands": len(graph.zoom_plan.commands) if graph.zoom_plan else 0,
        "has_subtitles": graph.subtitle_path is not None,
        "has_intro": intro_input_idx is not None,
        "has_outro": outro_input_idx is not None,
        "loudnorm_enabled": graph.audio_normalize.enabled,
        "loudnorm_two_pass": graph.audio_normalize.has_measurement,
        "video_effects": [e.effect_id for e in graph.video_effects],
        "has_jl_cuts": has_jl_cuts,
        "filter_complex_chars": len(filter_complex),
    }

    return CompiledGraph(
        inputs=inputs,
        filter_complex=filter_complex,
        output_video_label=f"[{current_video}]",
        output_audio_label=f"[{current_audio}]",
        extra_args=extra_args,
        output_path=Path(graph.output_path),
        diagnostics=diagnostics,
    )


def _build_zoom_stage(
    parts: list[str],
    zoom_plan: ZoomPlanSpec,
    video_label: str,
) -> str:
    """Stage B: split [v_main] на N веток, crop+scale per zoom_cmd, concat."""

    n = len(zoom_plan.commands)
    split_outputs = "".join(f"[vm{i}]" for i in range(n))
    parts.append(f"[{video_label}]split={n}{split_outputs}")

    zoom_video_labels: list[str] = []
    for i, cmd in enumerate(zoom_plan.commands):
        crop_expr = _zoom_command_to_crop_expr(
            cmd, zoom_plan.frame_width, zoom_plan.frame_height
        )
        z_label = f"vz{i}"
        parts.append(
            f"[vm{i}]trim=start={cmd.start_offset_sec_in_reel:.3f}:"
            f"end={cmd.end_offset_sec_in_reel:.3f},"
            f"setpts=PTS-STARTPTS,{crop_expr},setsar=1[{z_label}]"
        )
        zoom_video_labels.append(z_label)

    concat_inputs = "".join(f"[{lbl}]" for lbl in zoom_video_labels)
    parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[v_zoomed]")
    return "v_zoomed"


def _zoom_command_to_crop_expr(
    cmd: ZoomCommandSpec, frame_w: int, frame_h: int
) -> str:
    """Генерирует ffmpeg filter chain для одного ZoomCommand.

    Для 1 keyframe — статичный crop: `crop=CW:CH:X:Y,scale=Wf:Hf`.
    Для N>1 keyframes — dynamic piecewise-linear crop:
    `crop=CW:CH:<x_expr(t)>:<y_expr(t)>,scale=Wf:Hf`.

    Expression переменная `t` отсчитывается от начала видеопотока, пришедшего
    в фильтр. `setpts=PTS-STARTPTS` перед crop гарантирует t=0 в начале cut.

    В filter_complex запятые — разделители фильтров chain. Внутри expression
    они экранируются через `\\,`. Двоеточия в expressions не встречаются
    (crop args разделяются `:` на top-level).
    """

    scale_factor = max(0.0, 1.0 - cmd.zoom_percent / 100.0)
    crop_w = max(2, round(frame_w * scale_factor))
    crop_h = max(2, round(frame_h * scale_factor))
    crop_w -= crop_w % 2
    crop_h -= crop_h % 2

    if crop_w >= frame_w and crop_h >= frame_h:
        # Wide=0% — crop no-op, только scale.
        return f"scale={frame_w}:{frame_h}"

    # Конвертация keyframes в пиксельные (x, y) crop-координаты.
    x_pairs: list[tuple[float, float]] = []
    y_pairs: list[tuple[float, float]] = []
    for kf in cmd.keyframes:
        cx = kf.anchor_x * frame_w
        cy = kf.anchor_y * frame_h
        raw_x = cx - crop_w / 2
        raw_y = cy - crop_h / 2
        x_val = _clamp(raw_x, 0.0, float(frame_w - crop_w))
        y_val = _clamp(raw_y, 0.0, float(frame_h - crop_h))
        x_pairs.append((kf.t_offset_sec, x_val))
        y_pairs.append((kf.t_offset_sec, y_val))

    if len(cmd.keyframes) == 1:
        # Статичный anchor: округляем до чётных пикселей (yuv420p требует).
        x_int = round(x_pairs[0][1])
        y_int = round(y_pairs[0][1])
        x_int -= x_int % 2
        y_int -= y_int % 2
        return f"crop={crop_w}:{crop_h}:{x_int}:{y_int},scale={frame_w}:{frame_h}"

    # Dynamic tracking: piecewise-linear expression по (t_offset, pixel_value).
    x_expr = _build_piecewise_expr(x_pairs)
    y_expr = _build_piecewise_expr(y_pairs)
    return f"crop={crop_w}:{crop_h}:{x_expr}:{y_expr},scale={frame_w}:{frame_h}"


def _base_crop_command_to_expr(
    cmd: BaseCropCommandSpec,
    *,
    crop_w: int,
    crop_h: int,
    source_w: int,
    source_h: int,
) -> str:
    """Генерирует ffmpeg ``crop=CW:CH:x(t):y(t)`` для одного Stage A cut.

    В отличие от :func:`_zoom_command_to_crop_expr` (работает на уже-scaled
    frame рилса), base crop применяется к source — ``crop_w`` / ``crop_h``
    в source-пикселях, anchor normalized относительно source frame. Scale
    до target resolution выполняется следующим фильтром chain'а.
    """
    x_pairs: list[tuple[float, float]] = []
    y_pairs: list[tuple[float, float]] = []
    for kf in cmd.keyframes:
        cx = kf.anchor_x * source_w
        cy = kf.anchor_y * source_h
        raw_x = cx - crop_w / 2
        raw_y = cy - crop_h / 2
        x_val = _clamp(raw_x, 0.0, float(source_w - crop_w))
        y_val = _clamp(raw_y, 0.0, float(source_h - crop_h))
        x_pairs.append((kf.t_offset_sec, x_val))
        y_pairs.append((kf.t_offset_sec, y_val))

    if len(cmd.keyframes) == 1:
        x_int = round(x_pairs[0][1])
        y_int = round(y_pairs[0][1])
        x_int -= x_int % 2
        y_int -= y_int % 2
        return f"crop={crop_w}:{crop_h}:{x_int}:{y_int}"

    x_expr = _build_piecewise_expr(x_pairs)
    y_expr = _build_piecewise_expr(y_pairs)
    return f"crop={crop_w}:{crop_h}:{x_expr}:{y_expr}"


def _build_piecewise_expr(pairs: list[tuple[float, float]]) -> str:
    """Строит piecewise-linear ffmpeg expression от переменной `t`.

    Форма: `if(lt(t\\,T1)\\, seg0\\, if(lt(t\\,T2)\\, seg1\\, ... vN))`.
    Каждый сегмент: `v_i + (v_{i+1}-v_i) * (t - t_i) / (t_{i+1} - t_i)`.

    Запятые внутри expression экранированы `\\,` — иначе filter_complex parser
    воспринял бы их как разделители фильтров chain.
    """

    if len(pairs) < 1:
        raise ValueError("pairs must contain at least one (t, value) tuple")
    if len(pairs) == 1:
        return f"{pairs[0][1]:.2f}"

    segments: list[str] = []
    for i in range(len(pairs) - 1):
        t0, v0 = pairs[i]
        t1, v1 = pairs[i + 1]
        dt = t1 - t0
        if dt <= 1e-6:
            # Совпадающие keyframes — используем начальное значение сегмента.
            segments.append(f"{v0:.2f}")
        else:
            dv = v1 - v0
            # Формула piecewise-linear интерполяции.
            segments.append(
                f"{v0:.2f}+({dv:.2f})*(t-{t0:.3f})/({dt:.3f})"
            )

    # Композиция в одну вложенную if-цепочку.
    # if(lt(t\,t1)\, seg0\, if(lt(t\,t2)\, seg1\, ... vN))
    last_v = pairs[-1][1]
    expr = f"{last_v:.2f}"
    for i in reversed(range(len(segments))):
        t_boundary = pairs[i + 1][0]
        expr = f"if(lt(t\\,{t_boundary:.3f})\\,{segments[i]}\\,{expr})"
    return expr


def _build_extras_stage(
    *,
    parts: list[str],
    intro_input_idx: int | None,
    outro_input_idx: int | None,
    video_label: str,
    audio_label: str,
    preset: ExportPresetSpec,
) -> tuple[str, str]:
    """Stage F: нормализуем intro/outro и склеиваем в [v_concat][a_concat]."""

    sequence_video: list[str] = []
    sequence_audio: list[str] = []

    if intro_input_idx is not None:
        v_lbl, a_lbl = _normalize_extra(parts, intro_input_idx, "intro", preset)
        sequence_video.append(v_lbl)
        sequence_audio.append(a_lbl)

    sequence_video.append(video_label)
    sequence_audio.append(audio_label)

    if outro_input_idx is not None:
        v_lbl, a_lbl = _normalize_extra(parts, outro_input_idx, "outro", preset)
        sequence_video.append(v_lbl)
        sequence_audio.append(a_lbl)

    n = len(sequence_video)
    concat_inputs = "".join(
        f"[{v}][{a}]" for v, a in zip(sequence_video, sequence_audio, strict=True)
    )
    parts.append(f"{concat_inputs}concat=n={n}:v=1:a=1[v_concat][a_concat]")
    return "v_concat", "a_concat"


def _normalize_extra(
    parts: list[str],
    input_idx: int,
    role: str,
    preset: ExportPresetSpec,
) -> tuple[str, str]:
    """Приводит intro / outro к target preset (resolution, fps, sar, audio resample)."""

    v_lbl = f"v_{role}"
    a_lbl = f"a_{role}"
    parts.append(
        f"[{input_idx}:v]scale={preset.width}:{preset.height}:"
        f"force_original_aspect_ratio=decrease,"
        f"pad={preset.width}:{preset.height}:(ow-iw)/2:(oh-ih)/2,"
        f"setsar=1,fps={preset.fps}[{v_lbl}]"
    )
    parts.append(f"[{input_idx}:a]aresample=async=1:first_pts=0[{a_lbl}]")
    return v_lbl, a_lbl


def _build_loudnorm_stage(
    parts: list[str], spec: AudioNormalizeSpec, audio_label: str
) -> str:
    """Stage G: single- или two-pass loudnorm.

    Если ``spec.has_measurement`` → использует measured_* от pre-pass и
    ``linear=true`` для точности ±1 LU. Иначе single-pass ±2 LU.
    """

    if spec.has_measurement:
        parts.append(
            f"[{audio_label}]loudnorm=I={spec.target_lufs}:TP={spec.true_peak_dbtp}:"
            f"LRA={spec.lra}:"
            f"measured_I={spec.measured_i}:measured_TP={spec.measured_tp}:"
            f"measured_LRA={spec.measured_lra}:measured_thresh={spec.measured_thresh}:"
            f"offset={spec.measured_offset}:linear=true:print_format=json[a_final]"
        )
    else:
        parts.append(
            f"[{audio_label}]loudnorm=I={spec.target_lufs}:TP={spec.true_peak_dbtp}:"
            f"LRA={spec.lra}:print_format=json[a_final]"
        )
    return "a_final"



# FEAT-#E: adaptive afade. Раньше было 12.5ms на любой длине cut'а
# (TIER1-#4). Для коротких cuts (1-2 сек) это незаметно, но для длинных
# стыков иногда недостаточно чтоб убрать щелчок. Теперь подбираем длину
# пропорционально продолжительности cut'а:
#   < 0.5 sec  → no fade (fade съест сигнал)
#   0.5-2 sec  → 10ms
#   2-5 sec    → 15ms
#   ≥ 5 sec    → 25ms (щелчки на длинных стыках типично громче)


def _adaptive_afade_sec(duration: float) -> float:
    """Подбирает длину afade по длине cut'а. 0 = fade отключён."""

    if duration < 0.5:
        return 0.0
    if duration < 2.0:
        return 0.010
    if duration < 5.0:
        return 0.015
    return 0.025


def _audio_cut_chain(start_sec: float, end_sec: float, duration: float) -> str:
    """Собирает chain `atrim,asetpts,afade_in?,afade_out?` для одного cut.

    На стыке двух cuts получаем эффективный crossfade 2 × ``_adaptive_afade_sec``.
    FEAT-#E: длина fade адаптируется к длительности cut'а для минимизации
    как click-артефактов, так и потери полезного сигнала.
    """

    chain = (
        f"atrim=start={start_sec:.3f}:end={end_sec:.3f},"
        f"asetpts=PTS-STARTPTS"
    )
    fade = _adaptive_afade_sec(duration)
    if fade > 0:
        fade_out_start = max(0.0, duration - fade)
        chain += (
            f",afade=t=in:st=0:d={fade}"
            f",afade=t=out:st={fade_out_start:.4f}:d={fade}"
        )
    return chain


def _build_encoder_args(preset: ExportPresetSpec) -> list[str]:
    """Компилирует encoder argv для финального `ffmpeg -i ... -c:v ...`.

    TIER1-#5: hevc_videotoolbox получает дополнительные флаги для M-chip
    hardware encoder:
    * ``-allow_sw 1`` — fallback на software HEVC если VT недоступен
      (напр. CI без GPU или старые macOS);
    * ``-realtime 0`` — приоритет качества, не realtime constraint;
    * ``-prio_speed 0`` — та же логика (quality > speed).

    Для software encoder'ов (libx264/libx265) hardware-флаги не добавляются.
    """

    argv: list[str] = [
        "-c:v",
        preset.video_codec,
        "-tag:v",
        preset.video_tag,
        "-b:v",
        preset.video_bitrate,
        "-maxrate",
        preset.video_maxrate,
        "-bufsize",
        preset.video_bufsize,
        "-pix_fmt",
        preset.pix_fmt,
        "-r",
        str(preset.fps),
    ]
    if preset.video_codec == "hevc_videotoolbox":
        argv.extend(
            [
                "-allow_sw",
                "1",
                "-realtime",
                "0",
                "-prio_speed",
                "0",
            ]
        )
    argv.extend(
        [
            "-c:a",
            preset.audio_codec,
            "-b:a",
            preset.audio_bitrate,
            "-movflags",
            "+faststart",
        ]
    )
    return argv


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


__all__ = [
    "CompiledGraph",
    "build_filter_graph",
]
