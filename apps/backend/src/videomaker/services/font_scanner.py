"""Сканер системных шрифтов через `system_profiler SPFontsDataType`.

Подход:
* `system_profiler` на macOS возвращает полный список установленных шрифтов
  (user + system + supplemental), но занимает ~6 секунд. Запускать его sync
  при каждом `GET /fonts` — нельзя, UI ушёл бы в 7-секундный stall.
* Решение: файловый кеш `data/fonts_cache.json` + background warmup при
  старте приложения + explicit `POST /fonts/refresh` для пользователя.
* Фильтруем `.`-prefixed семейства — это внутренние PUA-шрифты Apple,
  недоступные для обычного набора текста.

Безопасность: ВСЕ subprocess-вызовы через `create_subprocess_exec` с
литеральным списком аргументов (без shell), поэтому command injection
невозможен в принципе.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from videomaker.core.logging import get_logger

log = get_logger(__name__)

CACHE_VERSION = 1


@dataclass(slots=True)
class FontCache:
    """Содержимое `fonts_cache.json`.

    `scanned_at` — ISO 8601 UTC timestamp последнего успешного сканирования.
    Используется UI для отображения «обновлено N минут назад».
    """

    fonts: list[str]
    scanned_at: str
    version: int = CACHE_VERSION
    platform: str = "darwin"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "platform": self.platform,
            "scanned_at": self.scanned_at,
            "fonts": list(self.fonts),
        }


class FontScannerError(RuntimeError):
    """Сканер не смог получить список шрифтов."""


async def scan_system_fonts(timeout_sec: float = 30.0) -> list[str]:
    """Запускает `system_profiler SPFontsDataType -json` и парсит уникальные
    font-family из поля `typefaces[].family`. Возвращает отсортированный
    список, отфильтровав:

    * `.`-prefixed (PUA/internal) шрифты,
    * пустые имена.

    Raises FontScannerError если команда упала или вышло за timeout.
    """

    proc = await asyncio.create_subprocess_exec(
        "system_profiler",
        "SPFontsDataType",
        "-json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_sec
        )
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise FontScannerError(
            f"system_profiler timed out after {timeout_sec}s"
        ) from exc

    if proc.returncode != 0:
        raise FontScannerError(
            f"system_profiler exited {proc.returncode}: "
            f"{stderr.decode(errors='replace')[:400]}"
        )

    try:
        data: dict[str, Any] = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise FontScannerError(f"system_profiler output is not JSON: {exc}") from exc

    items = data.get("SPFontsDataType", [])
    families: set[str] = set()
    for item in items:
        for typeface in item.get("typefaces") or []:
            fam = typeface.get("family")
            if isinstance(fam, str):
                name = fam.strip()
                if name and not name.startswith("."):
                    families.add(name)

    return sorted(families, key=str.casefold)


def load_cache(path: Path) -> FontCache | None:
    """Читает кеш с диска. Возвращает None если файл отсутствует или
    несовместимой версии."""

    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("font_cache_read_failed", error=str(exc))
        return None
    if not isinstance(raw, dict):
        return None
    version = raw.get("version")
    fonts = raw.get("fonts")
    if version != CACHE_VERSION or not isinstance(fonts, list):
        return None
    return FontCache(
        fonts=[str(f) for f in fonts],
        scanned_at=str(raw.get("scanned_at", "")),
        version=version,
        platform=str(raw.get("platform", "darwin")),
    )


def save_cache(path: Path, cache: FontCache) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(cache.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


async def refresh_cache(path: Path) -> FontCache:
    """Сканирует систему и атомарно обновляет кеш. Возвращает новый FontCache."""

    fonts = await scan_system_fonts()
    cache = FontCache(
        fonts=fonts,
        scanned_at=datetime.now(tz=UTC).isoformat(timespec="seconds"),
    )
    save_cache(path, cache)
    log.info("fonts_cache_refreshed", count=len(fonts), path=str(path))
    return cache


async def ensure_cache_warm(path: Path) -> FontCache | None:
    """Если кеш пуст — запускает сканирование. Если уже прогрет — возвращает
    закешированное.

    Логика вызова: на старте приложения запускается как background task.
    UI получает актуальный список после первого /fonts запроса (без блокировки
    на старте).
    """

    existing = load_cache(path)
    if existing is not None:
        return existing
    try:
        return await refresh_cache(path)
    except FontScannerError as scan_err:
        log.warning("fonts_cache_warmup_failed", error=str(scan_err))
        return None


__all__ = [
    "FontCache",
    "FontScannerError",
    "ensure_cache_warm",
    "load_cache",
    "refresh_cache",
    "save_cache",
    "scan_system_fonts",
]
