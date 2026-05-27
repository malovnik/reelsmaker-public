"""Применение caption-пресетов (prepend/append) к сгенерированному тексту."""
from __future__ import annotations

from videomaker.models.scheduler import CaptionPresetPosition, CaptionPresetRow


def apply_presets(
    *,
    generated_caption: str,
    presets: list[CaptionPresetRow],
) -> tuple[str, list[int]]:
    """Склеивает итоговый caption: все активные prepend (в порядке создания)
    + generated + все активные append (в порядке создания).

    Возвращает ``(итоговый_текст, применённые_preset_ids)``.
    """
    prepend_parts: list[str] = []
    append_parts: list[str] = []
    applied: list[int] = []

    for preset in presets:
        if not preset.is_active:
            continue
        if preset.position == CaptionPresetPosition.prepend.value:
            prepend_parts.append(preset.content.strip())
            applied.append(preset.id)
        elif preset.position == CaptionPresetPosition.append.value:
            append_parts.append(preset.content.strip())
            applied.append(preset.id)

    pieces: list[str] = []
    pieces.extend(prepend_parts)
    if generated_caption.strip():
        pieces.append(generated_caption.strip())
    pieces.extend(append_parts)
    return ("\n\n".join(p for p in pieces if p), applied)
