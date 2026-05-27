"""Unit-тесты для font_scanner — парсинг, cache i/o, filter."""

from __future__ import annotations

from pathlib import Path

import pytest

from videomaker.services.font_scanner import (
    CACHE_VERSION,
    FontCache,
    load_cache,
    save_cache,
)


def test_save_and_load_cache_roundtrip(tmp_path: Path) -> None:
    cache = FontCache(
        fonts=["Arial", "Helvetica", "Inter"],
        scanned_at="2026-04-16T10:00:00+00:00",
    )
    target = tmp_path / "fonts_cache.json"
    save_cache(target, cache)

    loaded = load_cache(target)
    assert loaded is not None
    assert loaded.fonts == ["Arial", "Helvetica", "Inter"]
    assert loaded.scanned_at == "2026-04-16T10:00:00+00:00"
    assert loaded.version == CACHE_VERSION


def test_load_cache_returns_none_for_missing_file(tmp_path: Path) -> None:
    assert load_cache(tmp_path / "nonexistent.json") is None


def test_load_cache_returns_none_for_wrong_version(tmp_path: Path) -> None:
    target = tmp_path / "fonts_cache.json"
    target.write_text(
        '{"version": 99, "fonts": ["Arial"], "scanned_at": "2020-01-01"}',
        encoding="utf-8",
    )
    assert load_cache(target) is None


def test_load_cache_returns_none_for_corrupted_json(tmp_path: Path) -> None:
    target = tmp_path / "fonts_cache.json"
    target.write_text("not a json at all", encoding="utf-8")
    assert load_cache(target) is None


def test_load_cache_returns_none_for_wrong_shape(tmp_path: Path) -> None:
    target = tmp_path / "fonts_cache.json"
    # fonts не list
    target.write_text(
        '{"version": 1, "fonts": "Arial", "scanned_at": "2020-01-01"}',
        encoding="utf-8",
    )
    assert load_cache(target) is None


def test_save_cache_is_atomic(tmp_path: Path) -> None:
    # Убеждаемся что после save нет временного файла.
    cache = FontCache(fonts=["Arial"], scanned_at="2026-04-16T10:00:00+00:00")
    target = tmp_path / "fonts_cache.json"
    save_cache(target, cache)
    assert target.exists()
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


@pytest.mark.integration
async def test_scan_system_fonts_returns_darwin_fonts() -> None:
    """Интеграционный тест на macOS — реально дёргает system_profiler.

    Проверяет что результат — список, содержит Arial (гарантированно
    установленный на всех macOS) и что нет `.`-prefixed семейств.
    """

    from videomaker.services.font_scanner import scan_system_fonts

    fonts = await scan_system_fonts(timeout_sec=60.0)
    assert len(fonts) > 20
    assert "Arial" in fonts or "Helvetica" in fonts
    for f in fonts:
        assert not f.startswith("."), f"PUA font leaked through filter: {f}"
    # Отсортировано case-insensitive
    lower_sorted = sorted(fonts, key=str.casefold)
    assert fonts == lower_sorted
