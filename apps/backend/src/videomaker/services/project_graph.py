"""ProjectGraph — декларативная модель одного рилса как набора NLE-нод.

Архитектурный паттерн: вместо последовательности subprocess-вызовов
(render → zoom → concat → loudnorm), мы строим **один декларативный граф**,
который `filter_graph_builder.build_filter_graph(graph)` компилирует
в один ffmpeg `filter_complex`.

Этот модуль содержит ТОЛЬКО pydantic-модели + factory `build_project_graph`.
Никакого ffmpeg/subprocess. Граф сохраняется как JSON-артефакт
`project_graphs.json` рядом с финальными mp4 для reproducibility / debug.

Связь с другими модулями:
* Входы builder'а — те же типы, что использовал `renderer._render_one_plan`
  (ReelSegmentRender, ZoomPlan, ExportPreset, PostProductionConfig).
* Выход — pure Pydantic-объект, фронтенд / тесты могут читать как JSON.

LUT / B-roll (v0.6+) намеренно отсутствуют — добавим как новые `LUTSpec` /
`BRollSpec` поля + новые stages в builder, когда будут разрабатываться.
Делать "пустые слоты" сейчас = создавать мёртвый код.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from videomaker.core.logging import get_logger
from videomaker.models.post_production import PostProductionConfig
from videomaker.services.media import ExportPreset, ReelSegmentRender
from videomaker.services.zoom_planner import (
    AnchorKeyframe,
    BaseCropCommand,
    BaseCropPlan,
    ZoomCommand,
    ZoomPlan,
    ZoomPlane,
)

log = get_logger(__name__)


class CutSpec(BaseModel):
    """Один вырез из source-видео (v + a).

    TIER2-#15 J/L-cut: ``audio_source_start_sec`` / ``audio_source_end_sec``
    задают окно аудио ОТДЕЛЬНО от видео. None → аудио совпадает с видео
    (hard cut). Ненулевое смещение → J/L-cut: аудио одной стороны перетекает
    через границу cut'ов (L-cut — тянется в следующий; J-cut — начинается
    до текущего видео). Суммарная длительность аудио всех cuts должна
    оставаться равной суммарной длительности видео — это инвариант
    планировщика, а не валидатор CutSpec (т.к. CutSpec локален).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_start_sec: float = Field(ge=0.0)
    source_end_sec: float = Field(ge=0.0)
    audio_source_start_sec: float | None = Field(default=None, ge=0.0)
    audio_source_end_sec: float | None = Field(default=None, ge=0.0)

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.source_end_sec - self.source_start_sec)

    @property
    def audio_start_sec(self) -> float:
        return self.audio_source_start_sec if self.audio_source_start_sec is not None else self.source_start_sec

    @property
    def audio_end_sec(self) -> float:
        return self.audio_source_end_sec if self.audio_source_end_sec is not None else self.source_end_sec

    @property
    def audio_duration_sec(self) -> float:
        return max(0.0, self.audio_end_sec - self.audio_start_sec)

    @property
    def has_separate_audio_window(self) -> bool:
        """True если audio-окно отличается от video-окна (J/L-cut применён)."""
        return (
            self.audio_source_start_sec is not None
            and abs(self.audio_source_start_sec - self.source_start_sec) > 1e-4
        ) or (
            self.audio_source_end_sec is not None
            and abs(self.audio_source_end_sec - self.source_end_sec) > 1e-4
        )

    @model_validator(mode="after")
    def _validate_range(self) -> CutSpec:
        if self.source_end_sec <= self.source_start_sec:
            raise ValueError(
                f"source_end_sec ({self.source_end_sec}) must be > "
                f"source_start_sec ({self.source_start_sec})"
            )
        if (
            self.audio_source_start_sec is not None
            and self.audio_source_end_sec is not None
            and self.audio_source_end_sec <= self.audio_source_start_sec
        ):
            raise ValueError(
                f"audio_source_end_sec ({self.audio_source_end_sec}) must be > "
                f"audio_source_start_sec ({self.audio_source_start_sec})"
            )
        return self


class AnchorKeyframeSpec(BaseModel):
    """Один keyframe для dynamic anchor tracking внутри ZoomCommand.

    `t_offset_sec` — отсчёт от начала содержащего ZoomCommand (с 0).
    Координаты нормализованы (0..1) и уже проклэмплены под zoom_percent
    командой — filter_graph_builder использует их напрямую.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    t_offset_sec: float = Field(ge=0.0)
    anchor_x: float = Field(ge=0.0, le=1.0)
    anchor_y: float = Field(ge=0.0, le=1.0)


class ZoomCommandSpec(BaseModel):
    """Зум-команда внутри финального reel-таймлайна (после concat сегментов).

    `keyframes` содержит минимум 1 точку. Если len==1 → статичный anchor
    на весь sub-plan. Если len>1 → dynamic piecewise-linear tracking
    между keyframes (filter_graph_builder генерирует crop=W:H:x(t):y(t)).

    Координаты anchor нормализованы (0..1) — независимы от resolution
    proxy vs source.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_offset_sec_in_reel: float = Field(ge=0.0)
    duration_sec: float = Field(gt=0.0)
    plane: Literal["close", "medium", "wide"]
    zoom_percent: int = Field(ge=0, le=80)
    keyframes: tuple[AnchorKeyframeSpec, ...]

    @model_validator(mode="after")
    def _validate_keyframes(self) -> ZoomCommandSpec:
        if not self.keyframes:
            raise ValueError("ZoomCommandSpec requires at least one keyframe")
        prev_t = -1.0
        for kf in self.keyframes:
            if kf.t_offset_sec < prev_t:
                raise ValueError(
                    "keyframes must be sorted by t_offset_sec ascending"
                )
            if kf.t_offset_sec > self.duration_sec + 1e-6:
                raise ValueError(
                    f"keyframe t_offset_sec ({kf.t_offset_sec}) exceeds duration "
                    f"({self.duration_sec})"
                )
            prev_t = kf.t_offset_sec
        return self

    @property
    def end_offset_sec_in_reel(self) -> float:
        return self.start_offset_sec_in_reel + self.duration_sec

    @property
    def anchor_x(self) -> float:
        """Snapshot first keyframe — для логов и legacy-совместимости."""
        return self.keyframes[0].anchor_x

    @property
    def anchor_y(self) -> float:
        return self.keyframes[0].anchor_y


class ZoomPlanSpec(BaseModel):
    """Набор `ZoomCommandSpec` для одного reel + размеры финального кадра."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    commands: tuple[ZoomCommandSpec, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.commands


class BaseCropCommandSpec(BaseModel):
    """Face-aware первичный crop для ОДНОГО ``CutSpec``.

    В отличие от ``ZoomCommandSpec`` (который применяется уже после concat
    всех cut'ов и в timeline-пространстве рилса), ``BaseCropCommandSpec``
    относится к одному cut'у — его ``t_offset_sec`` keyframes отсчитываются
    от начала cut'а (после ``trim + setpts=PTS-STARTPTS``).

    Координаты ``anchor_x`` / ``anchor_y`` нормализованы в source (0..1).
    ``filter_graph_builder`` переводит их в пиксельные ``x(t)`` / ``y(t)``
    с учётом ``crop_width`` / ``crop_height`` из ``BaseCropPlanSpec``.

    Минимум 1 keyframe. Если ``len(keyframes) == 1`` — crop статичный.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    duration_sec: float = Field(gt=0.0)
    keyframes: tuple[AnchorKeyframeSpec, ...]

    @model_validator(mode="after")
    def _validate_keyframes(self) -> BaseCropCommandSpec:
        if not self.keyframes:
            raise ValueError("BaseCropCommandSpec requires at least one keyframe")
        prev_t = -1.0
        for kf in self.keyframes:
            if kf.t_offset_sec < prev_t:
                raise ValueError(
                    "keyframes must be sorted by t_offset_sec ascending"
                )
            if kf.t_offset_sec > self.duration_sec + 1e-6:
                raise ValueError(
                    f"keyframe t_offset_sec ({kf.t_offset_sec}) exceeds duration "
                    f"({self.duration_sec})"
                )
            prev_t = kf.t_offset_sec
        return self


class BaseCropPlanSpec(BaseModel):
    """Face-aware aspect-preserving crop до preset aspect.

    Применяется в Stage A ДО scale. Одна ``BaseCropCommandSpec`` на каждый
    ``CutSpec`` в ``ProjectGraph.cuts`` (по индексу).

    Поля:
        source_width / source_height — размер входного (source/proxy) видео.
        crop_width / crop_height — размер crop-окна после aspect correction.
            Для перехода 16:9 → 9:16 с source 1920×1080 это 608×1080.
        commands — по одной команде на каждый cut.

    Если ``BaseCropPlanSpec`` отсутствует (None в ``ProjectGraph``) —
    Stage A использует legacy ``preset.scale_filter`` (содержит статичный
    crop по центру для обратной совместимости).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    crop_width: int = Field(gt=0)
    crop_height: int = Field(gt=0)
    commands: tuple[BaseCropCommandSpec, ...]

    @model_validator(mode="after")
    def _validate(self) -> BaseCropPlanSpec:
        if not self.commands:
            raise ValueError("BaseCropPlanSpec requires at least one command")
        if self.crop_width > self.source_width:
            raise ValueError(
                f"crop_width ({self.crop_width}) > source_width ({self.source_width})"
            )
        if self.crop_height > self.source_height:
            raise ValueError(
                f"crop_height ({self.crop_height}) > source_height ({self.source_height})"
            )
        return self

    @property
    def is_no_op(self) -> bool:
        """True когда crop совпадает с source (no change)."""
        return (
            self.crop_width == self.source_width
            and self.crop_height == self.source_height
        )


class AudioNormalizeSpec(BaseModel):
    """Параметры EBU R128 loudnorm.

    * ``enabled=False`` → стадия пропускается.
    * ``two_pass=True`` (default) → внешний measurement-pass заполняет
      ``measured_*`` поля, главный рендер использует ``linear=true`` ±1 LU.
    * ``two_pass=False`` → single-pass ±2 LU (быстрее, менее точно).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = True
    target_lufs: float = Field(default=-14.0, ge=-30.0, le=-5.0)
    true_peak_dbtp: float = Field(default=-1.5, ge=-9.0, le=-1.0)
    lra: float = Field(default=11.0, ge=1.0, le=30.0)
    two_pass: bool = True
    measured_i: float | None = None
    measured_tp: float | None = None
    measured_lra: float | None = None
    measured_thresh: float | None = None
    measured_offset: float | None = None

    @property
    def has_measurement(self) -> bool:
        """True если все measured_* заданы → two-pass режим в filter_graph."""
        return (
            self.measured_i is not None
            and self.measured_tp is not None
            and self.measured_lra is not None
            and self.measured_thresh is not None
            and self.measured_offset is not None
        )


class VideoEffectSpec(BaseModel):
    """Snapshot одного pluggable видеоэффекта для Stage D filter_graph.

    ``effect_id`` — стабильный идентификатор (bw / vignette / lut / …),
    хранится для логов и reproducibility. ``filter_expr`` — готовая
    ffmpeg-строка без внешних зависимостей (чтобы повторный рендер не
    зависел от актуального кода эффекта).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    effect_id: str = Field(min_length=1, max_length=32)
    filter_expr: str = Field(min_length=1)


class ExportPresetSpec(BaseModel):
    """Snapshot финального формата (resolution / fps / codecs / bitrates).

    Зеркалит `services.media.ExportPreset` (dataclass), но в Pydantic-форме
    для JSON-сериализации в артефакт.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    aspect: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: int = Field(gt=0)
    video_codec: str
    video_tag: str
    video_bitrate: str
    video_maxrate: str
    video_bufsize: str
    audio_codec: str
    audio_bitrate: str
    scale_filter: str
    pix_fmt: str

    @classmethod
    def from_export_preset(cls, preset: ExportPreset) -> ExportPresetSpec:
        return cls(
            aspect=preset.aspect,
            width=preset.width,
            height=preset.height,
            fps=preset.fps,
            video_codec=preset.video_codec,
            video_tag=preset.video_tag,
            video_bitrate=preset.video_bitrate,
            video_maxrate=preset.video_maxrate,
            video_bufsize=preset.video_bufsize,
            audio_codec=preset.audio_codec,
            audio_bitrate=preset.audio_bitrate,
            scale_filter=preset.scale_filter,
            pix_fmt=preset.pix_fmt,
        )

    def to_export_preset(self) -> ExportPreset:
        return ExportPreset(
            aspect=self.aspect,
            width=self.width,
            height=self.height,
            fps=self.fps,
            video_codec=self.video_codec,
            video_tag=self.video_tag,
            video_bitrate=self.video_bitrate,
            video_maxrate=self.video_maxrate,
            video_bufsize=self.video_bufsize,
            audio_codec=self.audio_codec,
            audio_bitrate=self.audio_bitrate,
            scale_filter=self.scale_filter,
            pix_fmt=self.pix_fmt,
        )


class ProjectGraph(BaseModel):
    """Декларативное описание одного рилса для FilterGraphBuilder.

    Все пути сохраняются как строки (Pydantic JSON-friendly).

    Семантика стадий:
    * Stage A (всегда) — режем `cuts` из `source_path`, склеиваем.
    * Stage B (если `zoom_plan` есть и не is_empty) — split + crop + concat.
    * Stage C (если `subtitle_path` указан) — burn ASS/SRT субтитров.
    * Stage F (если `intro_path` или `outro_path`) — concat с extras.
    * Stage G (если `audio_normalize.enabled`) — single-pass loudnorm.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    reel_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    source_path: str = Field(min_length=1)
    output_path: str = Field(min_length=1)

    cuts: tuple[CutSpec, ...]
    base_crop_plan: BaseCropPlanSpec | None = None
    zoom_plan: ZoomPlanSpec | None = None
    subtitle_path: str | None = None
    video_effects: tuple[VideoEffectSpec, ...] = ()

    # T10.3 + T10.7 — Motion filter expression (punch-in zoom, Ken Burns drift).
    # Строковый FFmpeg expression (обычно zoompan=...), вставляется между
    # Stage B (zoom) и Stage C (subtitles) в filter_graph_builder. None →
    # stage пропускается. Пустая строка также трактуется как «нет эффекта».
    motion_filter_expr: str | None = None
    """Pluggable эффекты Stage D (bw / vignette / lut / …). Применяются в
    порядке, заданном ``EFFECTS_REGISTRY``."""
    intro_path: str | None = None
    outro_path: str | None = None
    audio_normalize: AudioNormalizeSpec = Field(default_factory=AudioNormalizeSpec)
    export_preset: ExportPresetSpec

    # Split-screen ветка: body должно выходить в SOURCE aspect ratio
    # (1920×1080 для HD 16:9 источника), не в canvas aspect (1080×1920).
    # Потом split_screen._scale_expression letterbox'ит source в panel rect
    # — matches editor object-fit:contain behaviour. Иначе graph уже режет
    # body до 9:16 и split letterbox'ит 9:16 в 9:8 → полосы слева/справа
    # вместо сверху/снизу → editor ≠ render.
    preserve_source_res: bool = False

    @model_validator(mode="after")
    def _validate_cuts_not_empty(self) -> ProjectGraph:
        if not self.cuts:
            raise ValueError("ProjectGraph requires at least one CutSpec")
        if self.base_crop_plan is not None and len(self.base_crop_plan.commands) != len(self.cuts):
            raise ValueError(
                "base_crop_plan.commands length must match cuts length "
                f"(got {len(self.base_crop_plan.commands)} vs {len(self.cuts)})"
            )
        return self

    @property
    def total_cuts_duration_sec(self) -> float:
        return sum(c.duration_sec for c in self.cuts)

    def has_extras(self) -> bool:
        return self.intro_path is not None or self.outro_path is not None


def build_project_graph(
    *,
    reel_id: str,
    source_path: Path,
    output_path: Path,
    segments: list[ReelSegmentRender],
    zoom_plan: ZoomPlan | None,
    subtitle_path: Path | None,
    post_production_config: PostProductionConfig | None,
    preset: ExportPreset,
    base_crop_plan: BaseCropPlan | None = None,
    exclude_post_production: bool = False,
    exclude_subtitles: bool = False,
    preserve_source_res: bool = False,
) -> ProjectGraph:
    """Собирает `ProjectGraph` из существующих доменных типов pipeline'а.

    Args:
        reel_id: уникальный идентификатор reel (используется в логах + как имя
            JSON-артефакта).
        source_path: путь к исходному видео (или proxy — определяет вызывающий).
        output_path: куда renderer должен записать финальный mp4.
        segments: уже coerce'нутые/truncate'нутые `ReelSegmentRender`.
        zoom_plan: результат `build_zoom_plan(...)`. None / is_empty → Stage B пропускается.
        subtitle_path: путь к ASS-файлу или None.
        post_production_config: snapshot (intro/outro/audio_normalize). None → без extras и без loudnorm.
        preset: финальный `ExportPreset` (HEVC, AAC, faststart).
        exclude_post_production: если True, intro/outro исключаются из графа
            (остаётся только reel-body из `segments`). Исторически
            использовался для legacy post-hoc concat pass'а; с переходом на
            single-pass split-screen (``render_split_single_pass``) intro/outro
            остаются в графе — поэтому вызывающий код передаёт False.
            audio_normalize и прочие post-effects в графе сохраняются
            независимо от флага.
        exclude_subtitles: если True, ``subtitle_path`` не прописывается в
            граф (Stage C burn пропускается). Используется когда после
            рендера body применяется split-screen pass, который сам
            вжигает субтитры поверх полного 1080×1920 canvas. ASS-файл
            сам по себе генерится как обычно и передаётся в
            ``render_split_single_pass`` отдельным параметром.

    Returns:
        Frozen `ProjectGraph`, готовый к JSON-сериализации и к подаче в
        `FilterGraphBuilder`.
    """

    cuts = tuple(
        CutSpec(
            source_start_sec=round(seg.source_start, 3),
            source_end_sec=round(seg.source_end, 3),
        )
        for seg in segments
        if seg.duration >= 0.1
    )
    if not cuts:
        raise ValueError(
            f"reel {reel_id}: all segments shorter than 0.1s, cannot build graph"
        )

    zoom_spec: ZoomPlanSpec | None
    if zoom_plan is not None and not zoom_plan.is_empty:
        zoom_spec = ZoomPlanSpec(
            frame_width=zoom_plan.frame_width,
            frame_height=zoom_plan.frame_height,
            commands=tuple(_zoom_command_to_spec(c) for c in zoom_plan.commands),
        )
    else:
        zoom_spec = None

    base_crop_spec: BaseCropPlanSpec | None = (
        _base_crop_plan_to_spec(base_crop_plan, n_cuts=len(cuts))
        if base_crop_plan is not None
        else None
    )

    if post_production_config is None:
        intro_path: str | None = None
        outro_path: str | None = None
        # BUG-#F defensive default: без preset всё равно нормализуем звук.
        # -14 LUFS — обязательная гигиена для соцсетей (TikTok/Reels/Shorts).
        # Раньше тут был enabled=False, из-за чего job'ы без post_production
        # выходили с разной громкостью и TikTok сам не всегда догонял.
        audio_norm = AudioNormalizeSpec()
        video_effects: tuple[VideoEffectSpec, ...] = ()
    else:
        # Legacy-флаг: раньше split-screen требовал отдельного post-hoc
        # concat pass'а для intro/outro, поэтому их вырезали из графа.
        # Single-pass split-screen (``render_split_single_pass``) оставляет
        # intro/outro в compiled chain, поэтому современный pipeline передаёт
        # exclude_post_production=False. Флаг сохранён для обратной
        # совместимости построителей графа.
        intro_path = (
            None if exclude_post_production else post_production_config.intro_path
        )
        outro_path = (
            None if exclude_post_production else post_production_config.outro_path
        )
        audio_norm = AudioNormalizeSpec(
            enabled=post_production_config.audio_normalize_enabled,
            target_lufs=post_production_config.audio_target_lufs,
        )
        video_effects = _collect_video_effects(post_production_config)

    graph_subtitle_path: str | None = (
        None if exclude_subtitles or subtitle_path is None else str(subtitle_path)
    )

    graph = ProjectGraph(
        reel_id=reel_id,
        source_path=str(source_path),
        output_path=str(output_path),
        cuts=cuts,
        base_crop_plan=base_crop_spec,
        zoom_plan=zoom_spec,
        subtitle_path=graph_subtitle_path,
        intro_path=intro_path,
        outro_path=outro_path,
        audio_normalize=audio_norm,
        export_preset=ExportPresetSpec.from_export_preset(preset),
        video_effects=video_effects,
        preserve_source_res=preserve_source_res,
    )

    log.info(
        "project_graph_built",
        reel_id=reel_id,
        cuts=len(cuts),
        has_zoom=zoom_spec is not None,
        zoom_commands=len(zoom_spec.commands) if zoom_spec else 0,
        has_subtitles=graph_subtitle_path is not None,
        has_intro=intro_path is not None,
        has_outro=outro_path is not None,
        loudnorm=audio_norm.enabled,
        target_lufs=audio_norm.target_lufs,
        export_aspect=preset.aspect,
        total_cuts_duration_sec=round(graph.total_cuts_duration_sec, 2),
        video_effects=[e.effect_id for e in video_effects],
    )
    return graph


def _collect_video_effects(
    config: PostProductionConfig,
) -> tuple[VideoEffectSpec, ...]:
    """Итерирует registry и собирает специфические filter_expr для включённых
    эффектов. Результат можно JSON-сериализовать; само состояние конфига
    сохраняется в post_production_config_json отдельно.
    """
    from videomaker.services.video_effects import EFFECTS_REGISTRY, VideoEffectContext

    ctx = VideoEffectContext(post_production_config=config)
    collected: list[VideoEffectSpec] = []
    for effect in EFFECTS_REGISTRY:
        expr = effect.build_filter_expr(ctx)
        if expr is None:
            continue
        collected.append(
            VideoEffectSpec(effect_id=effect.effect_id, filter_expr=expr)
        )
    return tuple(collected)


def _zoom_command_to_spec(cmd: ZoomCommand) -> ZoomCommandSpec:
    plane_name: Literal["close", "medium", "wide"]
    if cmd.plane is ZoomPlane.close:
        plane_name = "close"
    elif cmd.plane is ZoomPlane.medium:
        plane_name = "medium"
    else:
        plane_name = "wide"
    return ZoomCommandSpec(
        start_offset_sec_in_reel=round(cmd.start_offset_sec_in_reel, 3),
        duration_sec=round(cmd.duration_sec, 3),
        plane=plane_name,
        zoom_percent=cmd.zoom_percent,
        keyframes=tuple(_keyframe_to_spec(kf) for kf in cmd.keyframes),
    )


def _keyframe_to_spec(kf: AnchorKeyframe) -> AnchorKeyframeSpec:
    return AnchorKeyframeSpec(
        t_offset_sec=round(kf.t_offset_sec, 3),
        anchor_x=round(kf.anchor_x, 4),
        anchor_y=round(kf.anchor_y, 4),
    )


def _base_crop_command_to_spec(cmd: BaseCropCommand) -> BaseCropCommandSpec:
    return BaseCropCommandSpec(
        duration_sec=round(cmd.duration_sec, 3),
        keyframes=tuple(_keyframe_to_spec(kf) for kf in cmd.keyframes),
    )


def _base_crop_plan_to_spec(
    plan: BaseCropPlan,
    *,
    n_cuts: int,
) -> BaseCropPlanSpec:
    """Конвертирует domain ``BaseCropPlan`` → pydantic ``BaseCropPlanSpec``.

    Проверяет что количество commands совпадает с числом cuts (иначе
    ``ProjectGraph`` валидатор бросит при построении).
    """
    if len(plan.commands) != n_cuts:
        raise ValueError(
            "BaseCropPlan.commands length must match cuts length "
            f"(got {len(plan.commands)} vs {n_cuts})"
        )
    return BaseCropPlanSpec(
        source_width=plan.source_width,
        source_height=plan.source_height,
        crop_width=plan.crop_width,
        crop_height=plan.crop_height,
        commands=tuple(_base_crop_command_to_spec(c) for c in plan.commands),
    )


__all__ = [
    "AnchorKeyframeSpec",
    "AudioNormalizeSpec",
    "BaseCropCommandSpec",
    "BaseCropPlanSpec",
    "CutSpec",
    "ExportPresetSpec",
    "ProjectGraph",
    "VideoEffectSpec",
    "ZoomCommandSpec",
    "ZoomPlanSpec",
    "build_project_graph",
]
