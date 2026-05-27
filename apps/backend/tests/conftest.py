"""Pytest configuration — изолирует тесты от пользовательского .env и БД."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

import pytest

_TEST_DB = Path("/tmp/videomaker_test.db")
_TEST_ASSETS = Path("/tmp/videomaker_test_pp_assets")

os.environ.setdefault("APP_DB_PATH", str(_TEST_DB))
os.environ.setdefault("APP_ARTIFACTS_DIR", "/tmp/videomaker_test_artifacts")
os.environ.setdefault("APP_UPLOAD_DIR", "/tmp/videomaker_test_uploads")
os.environ.setdefault("APP_POST_PRODUCTION_ASSETS_DIR", str(_TEST_ASSETS))

# Ключи из пользовательского .env не должны просачиваться в тесты — иначе
# `test_build_llm_fails_without_key` и т.п. ломаются на чужой машине.
for _secret in (
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "DEEPGRAM_API_KEY",
):
    os.environ.pop(_secret, None)
os.environ["GEMINI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["DEEPGRAM_API_KEY"] = ""


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    from videomaker.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture(scope="session")
def _initialized_db() -> Path:
    """Один раз на pytest run: создаёт fresh test DB через Base.metadata.create_all.

    Используем create_all (а не alembic upgrade), так как:
    * Миграции валидируются отдельно (round-trip в test_renderer + ручной upgrade).
    * create_all быстрее (нет subprocess) и достаточен для unit-тестов сервисов.
    """

    if _TEST_DB.exists():
        _TEST_DB.unlink()

    async def _create_schema() -> None:
        from videomaker.core.db import Base, dispose_engine, get_engine
        from videomaker.models import job as _j  # noqa: F401 — register
        from videomaker.models import post_production as _pp  # noqa: F401

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await dispose_engine()

    asyncio.run(_create_schema())
    return _TEST_DB


@pytest.fixture
async def clean_db(_initialized_db: Path):
    """Очищает все таблицы перед каждым тестом которому нужна чистая БД."""

    from sqlalchemy import delete

    from videomaker.core.db import session_scope
    from videomaker.models.job import Artifact, Job
    from videomaker.models.post_production import (
        PostProductionPresetRow,
        VideoAssetRow,
    )

    async with session_scope() as session:
        await session.execute(delete(Artifact))
        await session.execute(delete(Job))
        await session.execute(delete(PostProductionPresetRow))
        await session.execute(delete(VideoAssetRow))
    yield


def _ensure_ffmpeg_available() -> None:
    if not subprocess.run(
        ["ffmpeg", "-version"], capture_output=True, check=False
    ).returncode == 0:
        pytest.skip("ffmpeg is not available in PATH")


@pytest.fixture
def synth_video(tmp_path: Path):
    """Фабрика тестовых mp4: `synth_video(duration=2, name='clip')` → Path.

    Использует ffmpeg lavfi для синтеза color+sine — без зависимостей от
    внешних файлов. Размер ~10-50 KiB, длительность регулируется.
    """

    _ensure_ffmpeg_available()
    counter = {"n": 0}

    def _make(duration: float = 2.0, name: str = "clip") -> Path:
        counter["n"] += 1
        out = tmp_path / f"{name}_{counter['n']}.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=320x240:d={duration}:r=30",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out),
        ]
        result = subprocess.run(cmd, capture_output=True, check=False)
        if result.returncode != 0:
            pytest.fail(
                f"ffmpeg synth failed: {result.stderr.decode(errors='replace')}"
            )
        return out

    return _make
