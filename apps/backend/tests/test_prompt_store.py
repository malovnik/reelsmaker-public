"""Unit-тесты версионированного seed'а дефолтных промптов.

Покрывает:
- Первоначальную вставку с default_content_hash.
- No-op при совпадающем хеше.
- Авто-миграцию к новому дефолту если пользователь не редактировал.
- Сохранение user-edit + обновление default_content_hash baseline.
- Cleanup legacy-ключей.
- Обратную совместимость с legacy-row (default_content_hash=NULL).

Используется session-scoped _initialized_db из conftest.py; между тестами
очищаем только таблицу prompt_settings, чтобы не ломать fixture-кэш.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from videomaker.core.db import session_scope
from videomaker.models.job import PromptSetting
from videomaker.services import prompt_store


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@pytest_asyncio.fixture
async def clean_prompts(_initialized_db: Path) -> AsyncIterator[None]:
    """Очищает таблицу prompt_settings перед каждым тестом."""
    async with session_scope() as session:
        await session.execute(delete(PromptSetting))
    yield


@pytest.mark.asyncio
async def test_seed_first_run_inserts_all_defaults(clean_prompts) -> None:
    from videomaker.services.prompts import DEFAULT_PROMPTS

    result = await prompt_store.seed_default_prompts()

    assert result.added == len(DEFAULT_PROMPTS)
    assert result.migrated == 0
    assert result.preserved_user_edits == 0

    async with session_scope() as session:
        rows = list((await session.execute(select(PromptSetting))).scalars().all())
    assert len(rows) == len(DEFAULT_PROMPTS)
    for row in rows:
        assert row.default_content_hash is not None
        assert row.default_content_hash == _hash(row.content)


@pytest.mark.asyncio
async def test_seed_second_run_noop(clean_prompts) -> None:
    await prompt_store.seed_default_prompts()
    result = await prompt_store.seed_default_prompts()

    assert result.added == 0
    assert result.migrated == 0
    assert result.preserved_user_edits == 0


@pytest.mark.asyncio
async def test_seed_migrates_when_default_changes_and_user_untouched(
    clean_prompts, monkeypatch
) -> None:
    from videomaker.services.prompts import DEFAULT_PROMPTS, PromptKey

    await prompt_store.seed_default_prompts()
    old_content = DEFAULT_PROMPTS[PromptKey.closure_check]
    new_content = old_content + "\n\nОбновление дефолта v2."
    monkeypatch.setitem(DEFAULT_PROMPTS, PromptKey.closure_check, new_content)

    result = await prompt_store.seed_default_prompts()

    assert result.migrated >= 1
    assert result.preserved_user_edits == 0

    async with session_scope() as session:
        row = await session.get(PromptSetting, PromptKey.closure_check.value)
    assert row is not None
    assert row.content == new_content
    assert row.default_content_hash == _hash(new_content)


@pytest.mark.asyncio
async def test_seed_preserves_user_edit_when_default_changes(clean_prompts, monkeypatch) -> None:
    from videomaker.services.prompts import DEFAULT_PROMPTS, PromptKey

    await prompt_store.seed_default_prompts()
    original_default = DEFAULT_PROMPTS[PromptKey.hook_hunter]

    user_edited = original_default + "\n\nМой кастомный фрагмент от пользователя."
    async with session_scope() as session:
        row = await session.get(PromptSetting, PromptKey.hook_hunter.value)
        assert row is not None
        row.content = user_edited

    new_default = original_default + "\n\nНовый деф v2."
    monkeypatch.setitem(DEFAULT_PROMPTS, PromptKey.hook_hunter, new_default)

    result = await prompt_store.seed_default_prompts()

    assert result.preserved_user_edits >= 1

    async with session_scope() as session:
        row = await session.get(PromptSetting, PromptKey.hook_hunter.value)
    assert row is not None
    assert row.content == user_edited
    assert row.default_content_hash == _hash(new_default)


@pytest.mark.asyncio
async def test_seed_legacy_null_hash_treated_as_untouched(clean_prompts) -> None:
    """Row с default_content_hash=NULL мигрирует на текущий дефолт."""
    from videomaker.services.prompts import DEFAULT_PROMPTS, PromptKey

    legacy_key = PromptKey.compression.value
    async with session_scope() as session:
        session.add(
            PromptSetting(
                key=legacy_key,
                content="старый legacy-контент без хеша",
                default_content_hash=None,
            )
        )

    result = await prompt_store.seed_default_prompts()

    assert result.migrated >= 1
    async with session_scope() as session:
        row = await session.get(PromptSetting, legacy_key)
    assert row is not None
    assert row.content == DEFAULT_PROMPTS[PromptKey.compression]
    assert row.default_content_hash == _hash(row.content)


@pytest.mark.asyncio
async def test_seed_cleans_legacy_keys(clean_prompts) -> None:
    from videomaker.services.prompts import LEGACY_PROMPT_KEYS

    legacy_key = next(iter(LEGACY_PROMPT_KEYS))
    async with session_scope() as session:
        session.add(PromptSetting(key=legacy_key, content="legacy", default_content_hash="x"))

    result = await prompt_store.seed_default_prompts()

    assert result.legacy_cleaned >= 1
    async with session_scope() as session:
        row = await session.get(PromptSetting, legacy_key)
    assert row is None


def test_prompt_hash_matches_sha256() -> None:
    from videomaker.services.prompt_store import _prompt_hash

    assert _prompt_hash("hello") == hashlib.sha256(b"hello").hexdigest()
    assert _prompt_hash("кириллица") == hashlib.sha256("кириллица".encode()).hexdigest()
