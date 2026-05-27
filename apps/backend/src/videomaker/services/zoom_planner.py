"""Zoom planner: строит план кинематографических зумов для рилса.

Архитектура (v0.6 — dynamic tracking):

* Зум применяется на склейках между сегментами рилса (после coerce + concat).
* Из всех склеек выбираем каждую `apply_every_nth_cut`-ю.
* Между двумя выбранными склейками должно быть >= `min_interval_sec` секунд.
* Длинные сегменты (>`long_segment_threshold_sec`) разбиваются на под-планы
  длительностью `random.uniform(subsegment_min, subsegment_max)` каждый.
  Seed = детерминированный hash(reel_id) → один и тот же reel даёт один и
  тот же план при повторных рендерах.
* Для каждого под-плана определяется plane (close/medium/wide) циклически,
  если `alternating_planes_enabled`. Иначе все under = close.

**Dynamic face tracking внутри sub-plan:**
* Каждый `ZoomCommand` содержит `keyframes: tuple[AnchorKeyframe, ...]` —
  плотный семплинг anchor-точки с шагом `KEYFRAME_SAMPLE_DT_SEC` (0.3 с).
* Raw anchors из `FaceTrackResult.best_face_at(source_t)` проходят:
  1. **Rule of thirds** — смещение anchor_y так, чтобы глаза спикера
     попадали на верхнюю треть финального кадра (а не в центр).
  2. **EMA smoothing** — экспоненциальное сглаживание α=0.3 убирает jitter
     от мелких движений головы/шума детектора.
  3. **Dead-zone reduction** — keyframes со смещением <3% от предыдущего
     выбрасываются (нет смысла двигать crop-окно на 1 пиксель).
  4. **Per-keyframe clamping** — anchor зажимается в допустимый диапазон
     для данного zoom_percent, чтобы crop-окно не вышло за границы кадра.
* Итог: плавный панорамный tracking внутри cut вместо статичного crop.
  Между cuts — мгновенный переход, но eyeline остаётся в верхней трети
  финального кадра (правило монтажа «не прыгать глазами»).

Output: `ZoomPlan` с `list[ZoomCommand]`. Непосредственная генерация
ffmpeg crop-выражения (piecewise-linear по keyframes) — задача
`services/filter_graph_builder.py`.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from enum import StrEnum

from videomaker.core.logging import get_logger
from videomaker.models.post_production import PostProductionConfig
from videomaker.services.face_tracker import FaceTrackResult
from videomaker.services.media import ReelSegmentRender
from videomaker.services.object_tracker import ObjectTrack

log = get_logger(__name__)

# Дефолтный anchor: x=0.5 (центр), y=0.4 (анатомически уровень глаз
# при кадрировании по плечи). Используется когда лицо не обнаружено.
DEFAULT_ANCHOR_X = 0.5
DEFAULT_ANCHOR_Y = 0.4

# --- Параметры dynamic tracking -------------------------------------------------
# Шаг семплинга keyframes внутри sub-plan. 0.3 сек = 3.3 Hz — достаточно
# частый для плавного движения головы, но даёт компактные filter_complex
# expressions (для 7-сек cut'а ≤24 семпла, после dead-zone ≤5 keyframes).
KEYFRAME_SAMPLE_DT_SEC = 0.3

# Коэффициент экспоненциального сглаживания: 0.3 даёт time constant ~3 семпла
# (=0.9 сек) — сглаживает jitter за ~1 секунду, но не запаздывает за
# быстрым поворотом головы.
EMA_ALPHA = 0.3

# Порог dead-zone по нормализованным координатам (1.0 = full frame). 3%
# от ширины кадра = ~58 px на 1920-px source. Меньше — не двигаем crop.
DEAD_ZONE_NORM = 0.03

# Коэффициент сдвига anchor_y для rule of thirds. Финальный кадр 9:16:
# при crop-окне высотой H*scale мы хотим, чтобы глаза попадали на 1/3
# сверху окна. Center окна — на 1/2 сверху → сдвигаем anchor_y вниз от
# eyes на (0.5 - 0.33) * scale_factor = 0.167 * scale_factor.
RULE_OF_THIRDS_Y_SHIFT = 1.0 / 6.0


class ZoomPlane(StrEnum):
    close = "close"
    medium = "medium"
    wide = "wide"


# Циклический паттерн чередования по теории монтажа:
# близкий → средний → дальний → близкий → ... — глаза зрителя плавно
# адаптируются к смене плана, не дёргаются.
PLANE_CYCLE: tuple[ZoomPlane, ...] = (ZoomPlane.close, ZoomPlane.medium, ZoomPlane.wide)


@dataclass(slots=True, frozen=True)
class AnchorKeyframe:
    """Один keyframe динамического anchor-трекинга внутри sub-plan.

    `t_offset_sec` отсчитывается от начала ZoomCommand (то есть с 0 в момент
    входа в этот sub-plan). Координаты нормализованы (0..1) и уже
    проклэмплены под соответствующий zoom_percent.
    """

    t_offset_sec: float
    anchor_x: float
    anchor_y: float


@dataclass(slots=True)
class ZoomCommand:
    """Одна команда зума, привязанная к временному окну внутри рилса.

    Все координаты anchor нормализованы (0..1) — позволяет планировать
    независимо от финального разрешения.

    `start_offset_sec_in_reel` — отсчёт от начала склеенного рилса
    (после concat сегментов), не от source-видео.

    `keyframes` содержит минимум 1 точку (статичный anchor) и до ~10 точек
    (плавный tracking). Все keyframes предварительно проклэмплены под
    `zoom_percent` — потребителю (filter_graph_builder) достаточно построить
    piecewise-linear expression по (t_offset_sec, anchor_x, anchor_y).
    """

    reel_segment_idx: int
    start_offset_sec_in_reel: float
    duration_sec: float
    plane: ZoomPlane
    zoom_percent: int
    keyframes: tuple[AnchorKeyframe, ...]

    def __post_init__(self) -> None:
        if not self.keyframes:
            raise ValueError("ZoomCommand requires at least one keyframe")

    @property
    def end_offset_sec_in_reel(self) -> float:
        return self.start_offset_sec_in_reel + self.duration_sec

    @property
    def anchor_x(self) -> float:
        """Anchor первого keyframe — backward compat и snapshot для логов."""
        return self.keyframes[0].anchor_x

    @property
    def anchor_y(self) -> float:
        return self.keyframes[0].anchor_y

    @property
    def is_static(self) -> bool:
        """True если keyframes свернулись в одну точку (без tracking)."""
        return len(self.keyframes) == 1


@dataclass(slots=True)
class ZoomPlan:
    reel_id: str
    frame_width: int
    frame_height: int
    commands: list[ZoomCommand] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.commands

    @property
    def total_duration_sec(self) -> float:
        return sum(c.duration_sec for c in self.commands)


@dataclass(slots=True, frozen=True)
class BaseCropCommand:
    """Face-aware первичный crop для одного ``ReelSegmentRender``.

    ``keyframes`` семплируются по источнику в окне ``source_t_start``..``+duration``
    и привязываются к cut-local времени (t_offset от начала trim'а).
    """

    duration_sec: float
    keyframes: tuple[AnchorKeyframe, ...]

    def __post_init__(self) -> None:
        if not self.keyframes:
            raise ValueError("BaseCropCommand requires at least one keyframe")

    @property
    def is_static(self) -> bool:
        return len(self.keyframes) == 1


@dataclass(slots=True, frozen=True)
class BaseCropPlan:
    """Face-aware aspect-preserving crop для всех cuts одного рилса.

    В отличие от ``ZoomPlan`` (зум поверх уже-собранного timeline рилса),
    ``BaseCropPlan`` применяется per-cut в Stage A ДО scale под preset —
    это первичный crop 16:9 → 9:16 (или любой других aspect).
    """

    source_width: int
    source_height: int
    crop_width: int
    crop_height: int
    commands: tuple[BaseCropCommand, ...]

    @property
    def is_no_op(self) -> bool:
        return (
            self.crop_width == self.source_width
            and self.crop_height == self.source_height
        )


def build_zoom_plan(
    *,
    reel_id: str,
    segments: list[ReelSegmentRender],
    face_track: FaceTrackResult | None,
    config: PostProductionConfig,
    frame_width: int,
    frame_height: int,
    object_track: ObjectTrack | None = None,
    dead_zone_norm: float = DEAD_ZONE_NORM,
    ema_alpha: float = EMA_ALPHA,
    rule_of_thirds_y_shift: float = RULE_OF_THIRDS_Y_SHIFT,
) -> ZoomPlan:
    """Строит ZoomPlan для одного рилса.

    Args:
        reel_id: используется как seed для random.uniform под-планов.
        segments: список ReelSegmentRender ПОСЛЕ coerce+truncate.
        face_track: результат face_tracker (None → anchor = default center).
        config: snapshot post_production_config из Job.
        frame_width / frame_height: размеры выходного кадра рилса.
        object_track: опциональный ObjectTrack от Moondream detect (скринкаст,
            smart-zoom на объект). При наличии переопределяет face_track как
            источник anchor. Geometry-compatible (x/y/w/h normalized).

    Returns:
        ZoomPlan. Если zoom_enabled=False или нет валидных под-планов —
        возвращается с пустым `commands`.
    """

    plan = ZoomPlan(
        reel_id=reel_id,
        frame_width=frame_width,
        frame_height=frame_height,
    )

    if not config.zoom_enabled or not segments:
        log.info("zoom_plan_skipped", reel_id=reel_id, reason="disabled_or_empty")
        return plan

    # 1. Cumulative timeline в reel: для каждого segment сохраняем start_in_reel.
    reel_offsets: list[float] = []
    cursor = 0.0
    for seg in segments:
        reel_offsets.append(cursor)
        cursor += seg.duration

    # 2. Cut-point selection: какие segment-границы получают зум.
    selected_segment_idxs = _select_cut_segments(
        segments=segments,
        reel_offsets=reel_offsets,
        apply_every_nth=config.zoom_apply_every_nth_cut,
        min_interval_sec=config.zoom_min_interval_sec,
    )
    if not selected_segment_idxs:
        log.info("zoom_plan_no_cuts_selected", reel_id=reel_id)
        return plan

    # 3. Для каждого выбранного segment строим план под-сегментов.
    rng = random.Random(_deterministic_seed(reel_id))
    plane_counter = 0
    total_keyframes = 0
    tracked_commands = 0
    static_commands = 0

    for seg_idx in selected_segment_idxs:
        seg = segments[seg_idx]
        reel_start = reel_offsets[seg_idx]

        sub_durations = _split_segment_into_subplans(
            duration=seg.duration,
            threshold=config.zoom_long_segment_threshold_sec,
            sub_min=config.zoom_subsegment_min_sec,
            sub_max=config.zoom_subsegment_max_sec,
            rng=rng,
        )

        sub_offset = 0.0
        for sub_dur in sub_durations:
            plane = _select_plane(
                counter=plane_counter,
                alternating=config.zoom_alternating_planes_enabled,
            )
            zoom_percent = _plane_to_percent(plane, config)

            # Dynamic keyframe tracking: плотный semпл anchor-точки в окне
            # source_t_start..source_t_end с EMA + dead-zone.
            sub_source_t_start = seg.source_start + sub_offset
            keyframes = _build_anchor_keyframes(
                face_track=face_track,
                source_t_start=sub_source_t_start,
                duration_sec=sub_dur,
                zoom_percent=zoom_percent,
                object_track=object_track,
                dead_zone_norm=dead_zone_norm,
                ema_alpha=ema_alpha,
                rule_of_thirds_y_shift=rule_of_thirds_y_shift,
            )

            if len(keyframes) == 1:
                static_commands += 1
            else:
                tracked_commands += 1
            total_keyframes += len(keyframes)

            plan.commands.append(
                ZoomCommand(
                    reel_segment_idx=seg_idx,
                    start_offset_sec_in_reel=reel_start + sub_offset,
                    duration_sec=sub_dur,
                    plane=plane,
                    zoom_percent=zoom_percent,
                    keyframes=keyframes,
                )
            )

            sub_offset += sub_dur
            plane_counter += 1

    plane_counts = {p.value: 0 for p in ZoomPlane}
    for cmd in plan.commands:
        plane_counts[cmd.plane.value] += 1

    log.info(
        "zoom_plan_built",
        reel_id=reel_id,
        total_commands=len(plan.commands),
        planes=plane_counts,
        tracked_commands=tracked_commands,
        static_commands=static_commands,
        total_keyframes=total_keyframes,
        avg_keyframes_per_cmd=round(total_keyframes / len(plan.commands), 2)
        if plan.commands
        else 0.0,
        total_duration_sec=round(plan.total_duration_sec, 2),
    )
    return plan


def _build_anchor_keyframes(
    *,
    face_track: FaceTrackResult | None,
    source_t_start: float,
    duration_sec: float,
    zoom_percent: int,
    object_track: ObjectTrack | None = None,
    dead_zone_norm: float = DEAD_ZONE_NORM,
    ema_alpha: float = EMA_ALPHA,
    rule_of_thirds_y_shift: float = RULE_OF_THIRDS_Y_SHIFT,
) -> tuple[AnchorKeyframe, ...]:
    """Строит keyframes для dynamic anchor tracking внутри sub-plan.

    Этапы:
    1. Семплинг raw anchors каждые KEYFRAME_SAMPLE_DT_SEC в окне source.
    2. Rule of thirds: сдвиг anchor_y вниз от глаз чтобы они попадали
       на верхнюю треть финального кадра.
    3. EMA smoothing с α=0.3 — убирает jitter детектора.
    4. Dead-zone: отбрасываем keyframes со смещением <3% от last kept.
    5. Clamp каждого keyframe под zoom_percent — crop окно не вылезет.

    Returns:
        Tuple минимум из 1 keyframe. Первый всегда на t_offset=0, последний
        на t_offset=duration_sec (или близко к нему, после dead-zone).
    """

    if duration_sec <= 0:
        raise ValueError(f"duration_sec must be > 0, got {duration_sec}")

    scale_factor = max(0.0, 1.0 - zoom_percent / 100.0)

    # Семплируем как минимум 2 точки (начало и конец), даже если duration короткий.
    # Добавляем промежуточные с шагом KEYFRAME_SAMPLE_DT_SEC.
    sample_offsets: list[float] = [0.0]
    t = KEYFRAME_SAMPLE_DT_SEC
    while t < duration_sec - 1e-6:
        sample_offsets.append(t)
        t += KEYFRAME_SAMPLE_DT_SEC
    if sample_offsets[-1] < duration_sec - 1e-6:
        sample_offsets.append(duration_sec)

    # 1 + 2: raw anchors + rule of thirds shift
    raw_points: list[tuple[float, float, float]] = []  # (t_offset, x, y_corrected)
    for offset in sample_offsets:
        source_t = source_t_start + offset
        raw_x, raw_y_eyes, _has_face = _compute_anchor(
            face_track=face_track, source_t=source_t
        )
        # Rule of thirds применяем только если будет реальный crop (scale < 1).
        # При zoom_percent=0 (wide) anchor игнорируется → не важно.
        if scale_factor < 1.0:
            y_corrected = raw_y_eyes + rule_of_thirds_y_shift * scale_factor
        else:
            y_corrected = raw_y_eyes
        raw_points.append((offset, raw_x, y_corrected))

    # 3. EMA smoothing
    smoothed: list[tuple[float, float, float]] = []
    ema_x = raw_points[0][1]
    ema_y = raw_points[0][2]
    for t_offset, x, y in raw_points:
        ema_x = ema_alpha * x + (1.0 - ema_alpha) * ema_x
        ema_y = ema_alpha * y + (1.0 - ema_alpha) * ema_y
        smoothed.append((t_offset, ema_x, ema_y))

    # 4. Dead-zone reduction + гарантия что последняя точка присутствует.
    kept: list[tuple[float, float, float]] = [smoothed[0]]
    for i in range(1, len(smoothed) - 1):
        _t_cur, x_cur, y_cur = smoothed[i]
        _t_prev, x_prev, y_prev = kept[-1]
        if abs(x_cur - x_prev) >= dead_zone_norm or abs(y_cur - y_prev) >= dead_zone_norm:
            kept.append(smoothed[i])
    # Последний keyframe: добавляем всегда (чтобы duration expression был
    # корректным). Если смещение от предыдущего kept меньше dead-zone —
    # заменяем последний kept на этот, сохраняя t_offset.
    last_sample = smoothed[-1]
    if len(kept) > 1:
        _t_prev, x_prev, y_prev = kept[-1]
        if (
            abs(last_sample[1] - x_prev) < dead_zone_norm
            and abs(last_sample[2] - y_prev) < dead_zone_norm
        ):
            # Просто продлеваем текущий keyframe до конца — замена last kept.
            kept[-1] = (last_sample[0], x_prev, y_prev)
        else:
            kept.append(last_sample)
    elif kept[0][0] < last_sample[0] - 1e-6:
        # Только 1 keyframe, но duration > 0 — добавляем конечную точку
        # со смещением 0 (keyframes свернулись в static).
        # Это покрывает случай когда anchor стабилен на весь sub-plan.
        pass  # оставляем только 1 keyframe — is_static=True

    # 5. Clamp каждого keyframe под zoom_percent
    result: list[AnchorKeyframe] = []
    for t_offset, x, y in kept:
        x_clamped, y_clamped = _clamp_anchor_for_zoom(
            anchor_x=x, anchor_y=y, zoom_percent=zoom_percent
        )
        result.append(
            AnchorKeyframe(
                t_offset_sec=round(t_offset, 3),
                anchor_x=round(x_clamped, 4),
                anchor_y=round(y_clamped, 4),
            )
        )

    # Гарантия: минимум 1 keyframe. Если после всех манипуляций 0 (невозможно
    # по коду выше, но защитимся) — делаем default static.
    if not result:
        x_def, y_def = _clamp_anchor_for_zoom(
            anchor_x=DEFAULT_ANCHOR_X,
            anchor_y=DEFAULT_ANCHOR_Y,
            zoom_percent=zoom_percent,
        )
        result.append(AnchorKeyframe(t_offset_sec=0.0, anchor_x=x_def, anchor_y=y_def))

    # Если all-same keyframes после clamp'а (например face не найден → default) —
    # схлопываем в один keyframe для минимального filter_complex.
    if len(result) > 1:
        first = result[0]
        all_same = all(
            abs(kf.anchor_x - first.anchor_x) < 1e-6
            and abs(kf.anchor_y - first.anchor_y) < 1e-6
            for kf in result[1:]
        )
        if all_same:
            return (AnchorKeyframe(t_offset_sec=0.0, anchor_x=first.anchor_x, anchor_y=first.anchor_y),)

    return tuple(result)


def _select_cut_segments(
    *,
    segments: list[ReelSegmentRender],
    reel_offsets: list[float],
    apply_every_nth: int,
    min_interval_sec: float,
) -> list[int]:
    """Выбирает индексы сегментов, которые получают zoom-эффект.

    Логика «склейка = граница между сегментами», поэтому первый сегмент
    (idx=0) — это вход в reel, тоже считается начальной точкой для зума.

    Алгоритм:
    1. Кандидаты: каждая `apply_every_nth`-я склейка начиная с idx=0.
    2. Фильтр min_interval_sec: между двумя выбранными должно быть
       минимум M секунд (по reel_offsets).

    Returns:
        Список индексов сегментов в `segments`, отсортированных asc.
    """

    if apply_every_nth < 1:
        apply_every_nth = 1

    candidates = list(range(0, len(segments), apply_every_nth))
    if not candidates:
        return []

    selected: list[int] = [candidates[0]]
    for idx in candidates[1:]:
        last_offset = reel_offsets[selected[-1]]
        if reel_offsets[idx] - last_offset >= min_interval_sec:
            selected.append(idx)
    return selected


def _split_segment_into_subplans(
    *,
    duration: float,
    threshold: float,
    sub_min: float,
    sub_max: float,
    rng: random.Random,
) -> list[float]:
    """Возвращает список длительностей под-планов внутри сегмента.

    Если `duration <= threshold` → один план на всю длительность.

    Иначе разбиваем на куски `random.uniform(sub_min, sub_max)`. Последний
    кусок дотягивается до конца сегмента, чтобы не оставить хвост <0.5 сек.
    Если хвост получился слишком коротким (<sub_min) — вливаем в предыдущий.
    """

    if duration <= threshold:
        return [duration]

    parts: list[float] = []
    remaining = duration
    while remaining > sub_max:
        d = rng.uniform(sub_min, sub_max)
        d = min(d, remaining)
        parts.append(d)
        remaining -= d

    # Хвост: если короче sub_min — добавим к последнему, иначе создадим
    # отдельный кусок.
    if remaining > 0:
        if parts and remaining < sub_min:
            parts[-1] += remaining
        else:
            parts.append(remaining)

    return parts


def _select_plane(*, counter: int, alternating: bool) -> ZoomPlane:
    if not alternating:
        return ZoomPlane.close
    return PLANE_CYCLE[counter % len(PLANE_CYCLE)]


def _plane_to_percent(plane: ZoomPlane, config: PostProductionConfig) -> int:
    if plane is ZoomPlane.close:
        return config.zoom_close_percent
    if plane is ZoomPlane.medium:
        return config.zoom_medium_percent
    return config.zoom_wide_percent


def _compute_anchor(
    *,
    face_track: FaceTrackResult | None,
    source_t: float,
    object_track: ObjectTrack | None = None,
) -> tuple[float, float, bool]:
    """Возвращает (anchor_x, anchor_y, has_anchor).

    Приоритет источников:
        1. object_track (Moondream detect) — если передан и даёт bbox для source_t
        2. face_track (mediapipe) — fallback для talking-head формата
        3. default center (0.5, 0.5)

    Object-anchor использует геометрический центр bbox (cy), face-anchor
    использует уровень глаз (eyes_y) для rule-of-thirds смещения. Rule of
    thirds применяется в `_build_anchor_keyframes` с учётом scale_factor.
    """

    if object_track is not None:
        obj = object_track.best_bbox_at(source_t)
        if obj is not None:
            return obj.cx, obj.cy, True

    if face_track is None:
        return DEFAULT_ANCHOR_X, DEFAULT_ANCHOR_Y, False
    face = face_track.best_face_at(source_t)
    if face is None:
        return DEFAULT_ANCHOR_X, DEFAULT_ANCHOR_Y, False
    return face.cx, face.eyes_y, True


def _clamp_anchor_for_zoom(
    *,
    anchor_x: float,
    anchor_y: float,
    zoom_percent: int,
) -> tuple[float, float]:
    """Зажимает anchor так, чтобы crop окно гарантированно осталось в кадре.

    При zoom_percent=30 окно занимает 70% кадра. Центр окна не может быть
    ближе к краю, чем `0.5 * (1 - scale_factor) = 0.15`. Иначе край окна
    выйдет за пределы (отрицательная координата).

    Math: для scale_factor = 1 - zoom_percent/100:
    * допустимый диапазон x = [scale_factor/2, 1 - scale_factor/2]

    При scale_factor=1 (wide=0%) диапазон = [0.5, 0.5] — anchor force в центр,
    что корректно (no-op crop).
    """

    scale_factor = max(0.0, 1.0 - zoom_percent / 100.0)
    half = scale_factor / 2.0
    if scale_factor >= 1.0:
        # Wide=0% — anchor не имеет значения для crop результата
        return DEFAULT_ANCHOR_X, DEFAULT_ANCHOR_Y
    x = _clamp(anchor_x, half, 1.0 - half)
    y = _clamp(anchor_y, half, 1.0 - half)
    return x, y


def _clamp(value: float, lo: float, hi: float) -> float:
    if hi < lo:
        return lo
    return max(lo, min(hi, value))


# ── BaseCropPlan: face-aware первичный crop ──────────────────────────────────


def compute_aspect_crop_dims(
    source_width: int,
    source_height: int,
    target_aspect_ratio: float,
) -> tuple[int, int]:
    """Вычисляет aspect-preserving ``(crop_width, crop_height)``.

    ``target_aspect_ratio = target_w / target_h`` (для 9:16 = 0.5625).

    * source шире target (landscape → vertical): режем ширину, ``crop_h = source_h``.
    * source уже target (portrait → landscape): режем высоту, ``crop_w = source_w``.
    * source совпадает — возвращаем исходные размеры (no-op crop).

    Результат всегда чётный (yuv420p требует).
    """
    if source_width <= 0 or source_height <= 0:
        raise ValueError(
            f"source dims must be positive, got {source_width}x{source_height}"
        )
    if target_aspect_ratio <= 0:
        raise ValueError(f"target_aspect_ratio must be positive, got {target_aspect_ratio}")

    # yuv420p требует чётных размеров; для no-op возвращаем source-as-is
    # только если оба чётные (иначе слегка отрежем до ближайшего чётного).
    source_ratio = source_width / source_height
    if abs(source_ratio - target_aspect_ratio) < 1e-4:
        crop_w = source_width - (source_width % 2)
        crop_h = source_height - (source_height % 2)
        return crop_w, crop_h

    if source_ratio > target_aspect_ratio:
        crop_h = source_height - (source_height % 2)
        crop_w = max(2, round(crop_h * target_aspect_ratio))
        crop_w -= crop_w % 2
        return crop_w, crop_h

    crop_w = source_width - (source_width % 2)
    crop_h = max(2, round(crop_w / target_aspect_ratio))
    crop_h -= crop_h % 2
    return crop_w, crop_h


def _build_base_crop_keyframes(
    *,
    face_track: FaceTrackResult | None,
    source_t_start: float,
    duration_sec: float,
    scale_factor_x: float,
    scale_factor_y: float,
    dead_zone_norm: float = DEAD_ZONE_NORM,
    ema_alpha: float = EMA_ALPHA,
) -> tuple[AnchorKeyframe, ...]:
    """Семплирует face anchors для base crop.

    Отличия от ``_build_anchor_keyframes`` (для zoom):
    * НЕТ rule_of_thirds Y-shift. Anchor_y напрямую = eyes_y — crop окно
      центрируется по глазам, содержимое ниже (плечи/торс) попадает в низ 9:16.
    * Двухосевой clamp — асимметричный scale_factor по X и Y. Если по оси
      нет crop (scale_factor = 1.0) — anchor этой оси force в центр, что
      корректно (crop_offset=0, anchor не влияет на результат).

    EMA smoothing, dead-zone reduction, чётная seam minimization — те же что
    в zoom-версии.
    """

    if duration_sec <= 0:
        raise ValueError(f"duration_sec must be > 0, got {duration_sec}")

    sample_offsets: list[float] = [0.0]
    t = KEYFRAME_SAMPLE_DT_SEC
    while t < duration_sec - 1e-6:
        sample_offsets.append(t)
        t += KEYFRAME_SAMPLE_DT_SEC
    if sample_offsets[-1] < duration_sec - 1e-6:
        sample_offsets.append(duration_sec)

    raw_points: list[tuple[float, float, float]] = []
    for offset in sample_offsets:
        source_t = source_t_start + offset
        raw_x, raw_y_eyes, _has_face = _compute_anchor(
            face_track=face_track, source_t=source_t
        )
        raw_points.append((offset, raw_x, raw_y_eyes))

    smoothed: list[tuple[float, float, float]] = []
    ema_x = raw_points[0][1]
    ema_y = raw_points[0][2]
    for t_offset, x, y in raw_points:
        ema_x = ema_alpha * x + (1.0 - ema_alpha) * ema_x
        ema_y = ema_alpha * y + (1.0 - ema_alpha) * ema_y
        smoothed.append((t_offset, ema_x, ema_y))

    kept: list[tuple[float, float, float]] = [smoothed[0]]
    for i in range(1, len(smoothed) - 1):
        _t_cur, x_cur, y_cur = smoothed[i]
        _t_prev, x_prev, y_prev = kept[-1]
        if abs(x_cur - x_prev) >= dead_zone_norm or abs(y_cur - y_prev) >= dead_zone_norm:
            kept.append(smoothed[i])
    last_sample = smoothed[-1]
    if len(kept) > 1:
        _t_prev, x_prev, y_prev = kept[-1]
        if (
            abs(last_sample[1] - x_prev) < dead_zone_norm
            and abs(last_sample[2] - y_prev) < dead_zone_norm
        ):
            kept[-1] = (last_sample[0], x_prev, y_prev)
        else:
            kept.append(last_sample)

    half_x = scale_factor_x / 2.0
    half_y = scale_factor_y / 2.0

    result: list[AnchorKeyframe] = []
    for t_offset, x, y in kept:
        clamped_x = (
            DEFAULT_ANCHOR_X
            if scale_factor_x >= 1.0
            else _clamp(x, half_x, 1.0 - half_x)
        )
        clamped_y = (
            DEFAULT_ANCHOR_Y
            if scale_factor_y >= 1.0
            else _clamp(y, half_y, 1.0 - half_y)
        )
        result.append(
            AnchorKeyframe(
                t_offset_sec=round(t_offset, 3),
                anchor_x=round(clamped_x, 4),
                anchor_y=round(clamped_y, 4),
            )
        )

    if not result:
        fallback_x = (
            DEFAULT_ANCHOR_X
            if scale_factor_x >= 1.0
            else _clamp(DEFAULT_ANCHOR_X, half_x, 1.0 - half_x)
        )
        fallback_y = (
            DEFAULT_ANCHOR_Y
            if scale_factor_y >= 1.0
            else _clamp(DEFAULT_ANCHOR_Y, half_y, 1.0 - half_y)
        )
        result.append(
            AnchorKeyframe(
                t_offset_sec=0.0,
                anchor_x=fallback_x,
                anchor_y=fallback_y,
            )
        )

    if len(result) > 1:
        first = result[0]
        all_same = all(
            abs(kf.anchor_x - first.anchor_x) < 1e-6
            and abs(kf.anchor_y - first.anchor_y) < 1e-6
            for kf in result[1:]
        )
        if all_same:
            return (AnchorKeyframe(t_offset_sec=0.0, anchor_x=first.anchor_x, anchor_y=first.anchor_y),)

    return tuple(result)


def build_base_crop_plan(
    *,
    segments: list[ReelSegmentRender],
    face_track: FaceTrackResult | None,
    source_width: int,
    source_height: int,
    target_aspect_ratio: float,
) -> BaseCropPlan:
    """Строит ``BaseCropPlan`` для reel.

    Для каждого segment семплирует face keyframes (EMA + dead-zone) в source
    окне ``[source_start, source_end]`` и кламит их под рассчитанным aspect
    crop'ом. Команды выдаются в том же порядке что и ``segments``.

    Если source уже попадает в ``target_aspect_ratio`` (например портретное
    видео и вертикальный target) — возвращается ``BaseCropPlan`` с
    ``is_no_op=True`` и статичными centre-keyframes. ``filter_graph_builder``
    может такой план пропустить.
    """
    if not segments:
        raise ValueError("build_base_crop_plan requires at least one segment")

    crop_w, crop_h = compute_aspect_crop_dims(
        source_width=source_width,
        source_height=source_height,
        target_aspect_ratio=target_aspect_ratio,
    )
    scale_factor_x = crop_w / source_width
    scale_factor_y = crop_h / source_height

    commands: list[BaseCropCommand] = []
    for seg in segments:
        duration = float(seg.source_end - seg.source_start)
        if duration <= 0:
            continue
        keyframes = _build_base_crop_keyframes(
            face_track=face_track,
            source_t_start=float(seg.source_start),
            duration_sec=duration,
            scale_factor_x=scale_factor_x,
            scale_factor_y=scale_factor_y,
        )
        commands.append(BaseCropCommand(duration_sec=duration, keyframes=keyframes))

    if not commands:
        raise ValueError("build_base_crop_plan produced zero commands from segments")

    return BaseCropPlan(
        source_width=source_width,
        source_height=source_height,
        crop_width=crop_w,
        crop_height=crop_h,
        commands=tuple(commands),
    )


def _deterministic_seed(reel_id: str) -> int:
    """Hash → 32-bit int. Не использует встроенный hash() из-за PYTHONHASHSEED."""

    digest = hashlib.blake2s(reel_id.encode("utf-8"), digest_size=4).hexdigest()
    return int(digest, 16)


__all__ = [
    "DEAD_ZONE_NORM",
    "DEFAULT_ANCHOR_X",
    "DEFAULT_ANCHOR_Y",
    "EMA_ALPHA",
    "KEYFRAME_SAMPLE_DT_SEC",
    "PLANE_CYCLE",
    "RULE_OF_THIRDS_Y_SHIFT",
    "AnchorKeyframe",
    "BaseCropCommand",
    "BaseCropPlan",
    "ZoomCommand",
    "ZoomPlan",
    "ZoomPlane",
    "build_base_crop_plan",
    "build_zoom_plan",
    "compute_aspect_crop_dims",
]
