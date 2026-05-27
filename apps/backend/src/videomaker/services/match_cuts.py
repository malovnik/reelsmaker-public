"""T2.6 — Match-cuts (perceptual hashing без новых dependencies).

Вычисляет perceptual hash (aHash) кадров через PIL (уже в deps), не
требуя PySceneDetect / imagehash. Используется для перестановки
порядка рилсов в галерее так, чтобы визуально-похожие шли подряд
(mimicking match-cut эффект).

Алгоритм aHash (average hash):
1. Resize до 8×8 grayscale.
2. Compute mean brightness.
3. Bit = 1 если pixel > mean, иначе 0.
4. Возвращаем 64-bit hash (8 bytes).

Hamming distance / 64 → 0..1 similarity (0 = identical, 1 = opposite).

Не привязано к scene-detection (у нас рилсы уже имеют границы). Фокус
— сравнивать first/last frame между рилсами для упорядочивания в gallery.

Интерфейс:
- `compute_aash(image_path) -> int` — 64-bit integer hash.
- `hamming_distance(hash_a, hash_b) -> int` — count of differing bits.
- `visual_similarity(hash_a, hash_b) -> float` — 1 - hamming / 64.
- `order_reels_by_visual_similarity(reels, hashes_by_reel) -> list[reel_id]` —
  жадный ближайший-сосед порядок.
"""

from __future__ import annotations

from pathlib import Path


def compute_aash(image_path: Path) -> int:
    """Average hash 8×8 greyscale → 64-bit integer.

    Возвращает 0 если PIL не смог открыть файл. Без exception —
    caller увидит 0 hash и решит что делать (например skip).
    """
    try:
        from PIL import Image

        with Image.open(image_path) as im:
            gray = im.convert("L").resize((8, 8), Image.Resampling.LANCZOS)
            pixels: list[int] = list(gray.getdata())  # type: ignore[arg-type]
    except Exception:
        return 0

    if not pixels:
        return 0

    total = sum(pixels)
    mean = total / len(pixels)
    bits = 0
    for i, p in enumerate(pixels):
        if p > mean:
            bits |= 1 << i
    return bits


def hamming_distance(hash_a: int, hash_b: int) -> int:
    """Число различающихся бит между двумя 64-bit hashes."""
    if hash_a == 0 or hash_b == 0:
        return 64  # «максимальное несходство» если один из hash-ей неизвестен
    return bin(hash_a ^ hash_b).count("1")


def visual_similarity(hash_a: int, hash_b: int) -> float:
    """0..1 similarity score. 1.0 = identical aHash."""
    if hash_a == 0 or hash_b == 0:
        return 0.0
    return 1.0 - (hamming_distance(hash_a, hash_b) / 64.0)


def order_reels_by_visual_similarity(
    reel_ids: list[str],
    hashes_by_reel: dict[str, int],
    *,
    start_reel_id: str | None = None,
) -> list[str]:
    """Жадный nearest-neighbor порядок: начинаем с первого рилса, каждый
    следующий — максимально похожий на предыдущий (ближайший hamming).

    ``start_reel_id`` — если задан, начинаем с него. Иначе берём первый
    элемент списка.

    Рилсы без hash (значение 0) попадают в конец списка в исходном
    порядке. Порядок оставшихся — детерминистичен при равных расстояниях
    (по id).

    Для галерейного режима это даёт «плавный» слайдер: соседние рилсы
    визуально ближе, пользователь меньше отвлекается на смену темы.
    """
    if not reel_ids:
        return []

    unknowns = [rid for rid in reel_ids if hashes_by_reel.get(rid, 0) == 0]
    knowns = [rid for rid in reel_ids if hashes_by_reel.get(rid, 0) != 0]

    if not knowns:
        return list(reel_ids)

    current = (
        start_reel_id
        if start_reel_id and start_reel_id in knowns
        else knowns[0]
    )

    ordered: list[str] = [current]
    remaining = [rid for rid in knowns if rid != current]

    while remaining:
        current_hash = hashes_by_reel.get(current, 0)
        remaining.sort(
            key=lambda rid: (
                hamming_distance(current_hash, hashes_by_reel.get(rid, 0)),
                rid,
            )
        )
        next_reel = remaining.pop(0)
        ordered.append(next_reel)
        current = next_reel

    ordered.extend(sorted(unknowns))
    return ordered


__all__ = [
    "compute_aash",
    "hamming_distance",
    "order_reels_by_visual_similarity",
    "visual_similarity",
]
