"""Работа с промптами в БД: версионированный seed, get-with-fallback, batch-upsert.

Версионирование через ``default_content_hash`` column:
- На каждый seed вычисляется SHA-256 хеш текущего ``DEFAULT_PROMPTS[key]``.
- Если DB-row отсутствует → вставляется новый с хешем дефолта.
- Если ``row.default_content_hash == new_hash`` → no-op (актуально).
- Иначе дефолт в коде изменился. Сравниваем ``hash(row.content)`` с
  ``row.default_content_hash``:
    * Равны (или default_content_hash=NULL) → пользователь не редактировал,
      мигрируем content к новому дефолту + обновляем хеш.
    * Расходятся → пользователь редактировал, content сохраняем, но
      ``default_content_hash`` обновляем до нового (чтобы следующее
      сравнение user-edit vs default опиралось на актуальный baseline).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy import delete, select

from videomaker.core.db import session_scope
from videomaker.core.logging import get_logger
from videomaker.models.job import PromptSetting
from videomaker.services.prompts import (
    DEFAULT_PROMPTS,
    LEGACY_PROMPT_KEYS,
    PromptKey,
)

log = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class SeedResult:
    """Итог сида дефолтных промптов."""

    added: int
    migrated: int
    preserved_user_edits: int
    legacy_cleaned: int


def _prompt_hash(content: str) -> str:
    """SHA-256 hex-digest для UTF-8 контента промпта."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def seed_default_prompts() -> SeedResult:
    """Сидит дефолты + мигрирует к новым версиям без потери user-edits.

    Подробности алгоритма — в docstring модуля.
    """
    added = 0
    migrated = 0
    preserved = 0
    legacy_cleaned = 0

    async with session_scope() as session:
        if LEGACY_PROMPT_KEYS:
            cleanup_result = await session.execute(
                delete(PromptSetting).where(
                    PromptSetting.key.in_(LEGACY_PROMPT_KEYS),
                )
            )
            legacy_cleaned = cleanup_result.rowcount or 0
            if legacy_cleaned:
                log.info("legacy_prompts_cleaned", count=legacy_cleaned)

        existing_rows = {
            row.key: row for row in (await session.execute(select(PromptSetting))).scalars()
        }

        for key, content in DEFAULT_PROMPTS.items():
            new_default_hash = _prompt_hash(content)
            row = existing_rows.get(key.value)

            if row is None:
                session.add(
                    PromptSetting(
                        key=key.value,
                        content=content,
                        default_content_hash=new_default_hash,
                    )
                )
                added += 1
                continue

            if row.default_content_hash == new_default_hash:
                continue

            current_content_hash = _prompt_hash(row.content)
            user_edited = (
                row.default_content_hash is not None
                and current_content_hash != row.default_content_hash
            )
            if user_edited:
                row.default_content_hash = new_default_hash
                preserved += 1
                log.warning(
                    "prompt_user_edit_preserved_default_changed",
                    key=key.value,
                )
            else:
                row.content = content
                row.default_content_hash = new_default_hash
                migrated += 1

    if added or migrated or preserved:
        log.info(
            "default_prompts_seeded",
            added=added,
            migrated=migrated,
            preserved_user_edits=preserved,
        )
    return SeedResult(
        added=added,
        migrated=migrated,
        preserved_user_edits=preserved,
        legacy_cleaned=legacy_cleaned,
    )


async def get_prompt(key: PromptKey | str) -> str:
    key_str = key.value if isinstance(key, PromptKey) else key
    async with session_scope() as session:
        row = await session.get(PromptSetting, key_str)
        if row is not None:
            return row.content
    fallback_key = PromptKey(key_str) if key_str in PromptKey._value2member_map_ else None
    if fallback_key is not None:
        return DEFAULT_PROMPTS[fallback_key]
    raise KeyError(f"prompt {key_str!r} not found and no default exists")


async def load_all_prompts() -> dict[str, str]:
    async with session_scope() as session:
        result = await session.execute(select(PromptSetting))
        rows = list(result.scalars().all())
    loaded = {row.key: row.content for row in rows}
    merged: dict[str, str] = {key.value: content for key, content in DEFAULT_PROMPTS.items()}
    merged.update(loaded)
    return merged
