"""Преобразование пользовательского `SubtitleStyleConfig` в низкоуровневый `SubtitleStyle`
для ASS-рендера, а также пачка builtin-пресетов для seed'а таблицы.

Ключевая математика:

* **ASS цвета** записываются в формате `&HAABBGGRR&`, где `AA` — transparency (00 —
  полная непрозрачность, FF — полностью прозрачный). В UI пользователь задаёт
  opacity 0-100 % (100 % = непрозрачный).
* **Alignment** — numpad 1-9. Мы используем только `2` (bottom-center),
  `5` (mid-center) и `8` (top-center). MarginV при `5` игнорируется libass'ом,
  поэтому offset для anchor=center мы реализуем через переключение на `2/8` с
  пересчётом margin от центра кадра.
* **MarginV** отсчитывается от края кадра, соответствующего Alignment. Для
  `fit`-режима видео занимает меньше кадра (letterbox сверху/снизу), поэтому
  нижняя граница видео находится на высоте `letterbox_bottom` от нижнего edge
  кадра, и чтобы положить саб на отступ `offset_px` ниже видео, используем
  `margin_v = letterbox_bottom - offset_px` (аналогично для top).
"""

from __future__ import annotations

from dataclasses import dataclass

from videomaker.models.job import (
    FontWeight,
    SubtitleAnchor,
    SubtitleStyleConfig,
)
from videomaker.services.media import MediaInfo
from videomaker.services.subtitles import SubtitleStyle

# ============================================================================
# Instagram Reels safe zones (9:16 канва 1080×1920).
# ============================================================================
#
# Источники: Meta Creator Studio guidelines, IG Reels 2024-2026 publishing
# spec. Значения — в пикселях 1080-canvas; для других aspect'ов масштабируется
# пропорционально (см. ``scale_safe_zones``).
#
# - top (caption/follow button overlay): ~220 px
# - bottom (like/comment stack + caption): ~440 px
# - left pillar (gutter): ~64 px
# - right (sidebar icons: mute, share, save, more): ~144 px
#
# Инстаграм использует вариативные значения в зависимости от устройства и
# наличия шапки/подписи — держим с запасом, чтобы текст не перекрывался ни в
# каком сценарии.

INSTAGRAM_SAFE_ZONES_9_16 = {
    "top": 220,
    "bottom": 440,
    "left": 64,
    "right": 144,
}


@dataclass(slots=True)
class SafeZonePixels:
    """Абсолютные отступы safe-zone в пикселях целевого canvas'а."""

    top: int
    bottom: int
    left: int
    right: int


def compute_safe_zones(preset_width: int, preset_height: int) -> SafeZonePixels:
    """Возвращает пиксельные safe-zone отступы для указанного aspect'а.

    Для 9:16 1080×1920 — возвращает ровно INSTAGRAM_SAFE_ZONES_9_16.
    Для других соотношений (1:1, 4:5, 16:9) — масштабирует пропорционально
    по меньшей из размерностей (чтобы зоны не «разъехались»).
    """

    scale_h = preset_height / 1920
    scale_w = preset_width / 1080
    scale = min(scale_h, scale_w) if scale_h > 0 and scale_w > 0 else 1.0
    return SafeZonePixels(
        top=round(INSTAGRAM_SAFE_ZONES_9_16["top"] * scale),
        bottom=round(INSTAGRAM_SAFE_ZONES_9_16["bottom"] * scale),
        left=round(INSTAGRAM_SAFE_ZONES_9_16["left"] * scale),
        right=round(INSTAGRAM_SAFE_ZONES_9_16["right"] * scale),
    )


@dataclass(slots=True)
class ResolvedSubtitleStyle:
    """Готовый набор параметров для ASS-рендера."""

    ass_style: SubtitleStyle
    border_style: int  # 1 — outline+shadow, 3 — opaque box


# -------------------------- ASS color helpers --------------------------

def ass_color(hex_color: str, opacity_percent: int) -> str:
    """Преобразует `#RRGGBB` + opacity (0-100 %, 100 = непрозрачный) в
    ASS-формат `&HAABBGGRR&`.

    Alpha в ASS инвертирован: 0x00 = полная непрозрачность, 0xFF = прозрачность.
    """

    if not hex_color.startswith("#") or len(hex_color) != 7:
        raise ValueError(f"invalid hex color: {hex_color!r}")
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    opacity = max(0, min(100, opacity_percent))
    alpha = round((100 - opacity) / 100 * 255)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}&"


def _ass_alignment(anchor: SubtitleAnchor) -> int:
    if anchor is SubtitleAnchor.top:
        return 8
    if anchor is SubtitleAnchor.center:
        return 5
    return 2  # bottom


def _bold_flag(weight: FontWeight) -> int:
    # ASS: -1 = bold on (400+), 0 = regular
    return -1 if weight is FontWeight.bold else 0


# -------------------------- letterbox geometry --------------------------

@dataclass(slots=True)
class LetterboxGeometry:
    """Размеры видео-области внутри финального кадра (после fit-scale+pad).

    Для fill-режима `letterbox_top = letterbox_bottom = 0` (видео заполняет
    весь кадр).
    """

    scaled_width: int
    scaled_height: int
    letterbox_top: int
    letterbox_bottom: int
    pillar_left: int
    pillar_right: int


def compute_letterbox(
    preset_width: int,
    preset_height: int,
    fit_mode: str,
    source_info: MediaInfo | None,
) -> LetterboxGeometry:
    """Вычисляет фактические размеры видео внутри финального кадра.

    Для `fill` — всегда полное заполнение (letterbox=0). Для `fit` — применяем
    формулу `force_original_aspect_ratio=decrease`: scale = min(target_w/src_w,
    target_h/src_h). При отсутствии media_info fallback — считаем исходник
    уже 1:1 с target (без letterbox), чтобы рендер не упал.
    """

    if fit_mode == "fill" or source_info is None or source_info.width <= 0 or source_info.height <= 0:
        return LetterboxGeometry(
            scaled_width=preset_width,
            scaled_height=preset_height,
            letterbox_top=0,
            letterbox_bottom=0,
            pillar_left=0,
            pillar_right=0,
        )

    scale_x = preset_width / source_info.width
    scale_y = preset_height / source_info.height
    scale = min(scale_x, scale_y)
    scaled_w = round(source_info.width * scale)
    scaled_h = round(source_info.height * scale)
    # Чётность критична для H.264/HEVC — ffmpeg pad сам подгоняет, нам для
    # расчётов достаточно округления в ближайший пиксель.
    letterbox_total_v = max(0, preset_height - scaled_h)
    letterbox_total_h = max(0, preset_width - scaled_w)
    return LetterboxGeometry(
        scaled_width=scaled_w,
        scaled_height=scaled_h,
        letterbox_top=letterbox_total_v // 2,
        letterbox_bottom=letterbox_total_v - letterbox_total_v // 2,
        pillar_left=letterbox_total_h // 2,
        pillar_right=letterbox_total_h - letterbox_total_h // 2,
    )


# -------------------------- margin_v / alignment --------------------------

def compute_margin_v(
    config: SubtitleStyleConfig,
    preset_height: int,
    fit_mode: str,
    letterbox: LetterboxGeometry,
) -> tuple[int, int]:
    """Возвращает (alignment, margin_v) для anchor-режима.

    Используется только при ``position_mode == "anchor"``. Для free-режима
    alignment всегда 5 (middle-center), позиция задаётся через ``\\pos``
    override per-event в dialogue — см. ``resolve_free_position``.

    Семантика anchor:
    * `fill + bottom/top` → смещение `offset_px` от соответствующего edge кадра.
    * `fit + bottom/top`  → смещение `offset_px` от нижней/верхней границы
      видео внутрь letterbox. `margin_v = letterbox - offset_px`.
    * `center + fill`     → при offset=0 alignment=5 с MarginV=0.
      При offset>0 текст сдвигается вниз от центра: alignment=8,
      margin_v = preset_height // 2 + offset_px (baseline оказывается на
      offset_px ниже middle-кадра).
    * `center + fit`      → всегда alignment=5, offset_px игнорируется (logics
      «по центру» слабо совместима с fit-letterbox, UI об этом предупреждает).
    """

    alignment = _ass_alignment(config.anchor)
    offset = max(0, int(config.offset_px))

    if config.anchor is SubtitleAnchor.center:
        if fit_mode == "fit":
            return 5, 0
        if offset == 0:
            return 5, 0
        return 8, max(0, preset_height // 2 + offset)

    if fit_mode == "fit":
        if config.anchor is SubtitleAnchor.bottom:
            margin = max(0, letterbox.letterbox_bottom - offset)
        else:  # top
            margin = max(0, letterbox.letterbox_top - offset)
        return alignment, margin

    # fill-режим: margin_v = offset_px от соответствующего edge кадра.
    return alignment, offset


def resolve_free_position(
    config: SubtitleStyleConfig,
    preset_width: int,
    preset_height: int,
) -> tuple[int, int]:
    """Свободное позиционирование: возвращает (pos_x_px, pos_y_px) центра
    субтитрового блока в координатах canvas'а.

    При ``config.clamp_to_safe_zone=True`` координаты обрезаются так, чтобы
    центр блока находился минимум на расстоянии safe-zone отступа от всех
    четырёх краёв. Это приблизительный clamp — точная ширина/высота текста
    зависит от контента, но для центра достаточно отступа от края.
    """

    pos_x = round(preset_width * max(0.0, min(100.0, config.free_x_pct)) / 100)
    pos_y = round(preset_height * max(0.0, min(100.0, config.free_y_pct)) / 100)
    if not config.clamp_to_safe_zone:
        return pos_x, pos_y

    zones = compute_safe_zones(preset_width, preset_height)
    pos_x = max(zones.left, min(preset_width - zones.right, pos_x))
    pos_y = max(zones.top, min(preset_height - zones.bottom, pos_y))
    return pos_x, pos_y


# -------------------------- full resolution --------------------------

def resolve_style(
    config: SubtitleStyleConfig,
    *,
    preset_width: int,
    preset_height: int,
    fit_mode: str,
    source_info: MediaInfo | None,
) -> ResolvedSubtitleStyle:
    """Собирает финальный SubtitleStyle для рендера ASS-файла."""

    letterbox = compute_letterbox(preset_width, preset_height, fit_mode, source_info)

    pos_x_px: int | None = None
    pos_y_px: int | None = None
    if config.position_mode == "free":
        # В free-режиме каждый dialogue event получает \pos override; MarginV
        # + alignment становятся no-op'ом, ставим alignment=5 (middle-center)
        # чтобы libass использовал \pos как центр блока.
        alignment = 5
        margin_v = 0
        pos_x_px, pos_y_px = resolve_free_position(config, preset_width, preset_height)
    else:
        alignment, margin_v = compute_margin_v(
            config, preset_height, fit_mode, letterbox
        )
        # Safe-zone в anchor-режиме: margin_v отсчитывается от нижнего/верхнего
        # края кадра, поэтому при включённом clamp поднимаем его минимум до
        # safe-zone — иначе текст заходит в небезопасную полосу (UI соцсети),
        # которую превью рисует, но рендер раньше игнорировал.
        if config.clamp_to_safe_zone:
            safe = compute_safe_zones(preset_width, preset_height)
            if config.anchor is SubtitleAnchor.bottom:
                margin_v = max(margin_v, safe.bottom)
            elif config.anchor is SubtitleAnchor.top:
                margin_v = max(margin_v, safe.top)

    # Горизонтальные поля: safe-zone-aware, чтобы libass авто-перенос и
    # визуальный центр уважали IG UI (иконки справа, подпись снизу-слева).
    # Default legacy 40/40 оставляем только если clamp выключен явно.
    if config.clamp_to_safe_zone:
        zones = compute_safe_zones(preset_width, preset_height)
        margin_l = zones.left
        margin_r = zones.right
    else:
        margin_l = 40
        margin_r = 40

    border_style = 3 if config.background else 1
    primary = ass_color(config.primary_color, config.text_opacity)
    outline = ass_color(config.outline_color, 100)
    # libass использует BackColour для тени при border_style=1 и для
    # подложки при border_style=3 — один слот, два смысла.
    if border_style == 3:
        back = ass_color(config.background_color, config.background_opacity)
    else:
        back = ass_color(config.shadow_color, config.shadow_opacity)

    ass_style = SubtitleStyle(
        font=config.font,
        size=config.size,
        primary_colour=primary,
        outline_colour=outline,
        back_colour=back,
        outline=float(config.outline_width),
        shadow=float(config.shadow_width),
        margin_v=margin_v,
        margin_l=margin_l,
        margin_r=margin_r,
        alignment=alignment,
        bold=_bold_flag(config.weight),
        italic=1 if config.italic else 0,
        border_style=border_style,
        wrap_mode=config.wrap_mode,
        max_lines=config.max_lines,
        max_chars_per_line=config.max_chars_per_line,
        pos_x_px=pos_x_px,
        pos_y_px=pos_y_px,
    )
    return ResolvedSubtitleStyle(ass_style=ass_style, border_style=border_style)


# -------------------------- builtin presets --------------------------

BUILTIN_PRESETS: list[tuple[str, bool, SubtitleStyleConfig]] = [
    (
        "Минимализм белый",
        True,  # default
        SubtitleStyleConfig(
            anchor=SubtitleAnchor.bottom,
            offset_px=200,
            font="Arial",
            size=64,
            weight=FontWeight.bold,
            primary_color="#FFFFFF",
            outline_color="#000000",
            outline_width=3.0,
            shadow_width=1.0,
            background=False,
        ),
    ),
    (
        "Жёлтый с обводкой",
        False,
        SubtitleStyleConfig(
            anchor=SubtitleAnchor.bottom,
            offset_px=220,
            font="Arial Black",
            size=72,
            weight=FontWeight.bold,
            primary_color="#FFD700",
            outline_color="#000000",
            outline_width=4.0,
            shadow_width=2.0,
            background=False,
        ),
    ),
    (
        "С подложкой снизу",
        False,
        SubtitleStyleConfig(
            anchor=SubtitleAnchor.bottom,
            offset_px=160,
            font="Helvetica",
            size=60,
            weight=FontWeight.bold,
            primary_color="#FFFFFF",
            outline_color="#000000",
            outline_width=0.0,
            shadow_width=0.0,
            background=True,
            background_color="#000000",
            background_opacity=65,
            background_padding=14,
        ),
    ),
    (
        "Акцент по центру",
        False,
        SubtitleStyleConfig(
            anchor=SubtitleAnchor.center,
            offset_px=0,
            font="Inter",
            size=80,
            weight=FontWeight.bold,
            primary_color="#FFFFFF",
            outline_color="#111111",
            outline_width=5.0,
            shadow_width=2.0,
            background=False,
        ),
    ),
]


# -------------------------- font catalogue --------------------------

SYSTEM_FONTS: tuple[str, ...] = (
    "Arial",
    "Arial Black",
    "Helvetica",
    "Helvetica Neue",
    "SF Pro Display",
    "SF Pro Text",
    "Inter",
    "Roboto",
    "Montserrat",
    "Open Sans",
    "Lato",
    "Oswald",
    "Bebas Neue",
    "Georgia",
    "Times New Roman",
    "Menlo",
    "Courier New",
    "Impact",
    "PT Sans",
    "PT Serif",
)


__all__ = [
    "BUILTIN_PRESETS",
    "SYSTEM_FONTS",
    "LetterboxGeometry",
    "ResolvedSubtitleStyle",
    "ass_color",
    "compute_letterbox",
    "compute_margin_v",
    "resolve_style",
]
