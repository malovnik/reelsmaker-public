"""B&W effect: полная десатурация через ``hue=s=0``.

ffmpeg применяет HSL-трансформацию в hardware-accelerated фильтре.
Простейший путь к кинематографичному ЧБ без перехода на ``colormatrix``
или ``colorspace`` (которые требуют точного yuv profile source).

Для усиления "шикарного" вида ЧБ — можно потом добавить:
- ``eq=contrast=1.12:brightness=-0.02`` — лёгкий бьюти-контраст.
- film grain через `geq` или pre-rendered overlay.
Сейчас только чистая десатурация — безопасно, быстро, без риска clipping.
"""

from __future__ import annotations

from videomaker.services.video_effects.base import VideoEffectContext


class BWEffect:
    effect_id = "bw"
    label = "Чёрно-белое (кинематографичное)"

    def build_filter_expr(self, context: VideoEffectContext) -> str | None:
        if not context.post_production_config.bw_enabled:
            return None
        # saturation=0 через hue filter. Брайтнес/контраст оставляем источнику
        # — HEVC на 25M bitrate сохраняет тонкие тонова без dithering.
        return "hue=s=0"
