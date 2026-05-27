"""CRUD для AccountProfileRow + CaptionPresetRow."""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from videomaker.models.scheduler import (
    AccountProfileRow,
    CaptionPresetPosition,
    CaptionPresetRow,
)

_MUTABLE_PROFILE_FIELDS = frozenset({
    "language",
    "audience",
    "tone",
    "default_hashtags_json",
    "banned_words_json",
    "cta_style",
    "max_caption_length",
})


async def list_profiles(db: AsyncSession) -> Sequence[AccountProfileRow]:
    result = await db.execute(
        select(AccountProfileRow).order_by(AccountProfileRow.display_name)
    )
    return result.scalars().all()


async def get_profile(
    db: AsyncSession, publer_account_id: str
) -> AccountProfileRow | None:
    return await db.get(AccountProfileRow, publer_account_id)


async def upsert_profile(
    db: AsyncSession,
    *,
    publer_account_id: str,
    display_name: str,
    network: str,
    **fields: Any,
) -> AccountProfileRow:
    row = await db.get(AccountProfileRow, publer_account_id)
    if row is None:
        row = AccountProfileRow(
            publer_account_id=publer_account_id,
            display_name=display_name,
            network=network,
        )
        db.add(row)
    else:
        row.display_name = display_name
        row.network = network
    for key, value in fields.items():
        if key in _MUTABLE_PROFILE_FIELDS and value is not None:
            setattr(row, key, value)
    await db.flush()
    await db.refresh(row)
    return row


async def delete_profile(db: AsyncSession, publer_account_id: str) -> None:
    row = await db.get(AccountProfileRow, publer_account_id)
    if row is not None:
        await db.delete(row)
        await db.flush()


async def list_presets_for_scope(
    db: AsyncSession, *, account_id: str | None
) -> list[CaptionPresetRow]:
    """Presets, применимые к посту на ``account_id`` (только активные).

    Порядок склейки итогового caption:
    global-prepend → scoped-prepend → generated → scoped-append → global-append.
    Внутри каждой группы — по возрастанию ``id`` (порядок создания).
    """
    stmt = select(CaptionPresetRow).where(CaptionPresetRow.is_active.is_(True))
    result = await db.execute(stmt)
    all_active = list(result.scalars().all())

    prepend_position = CaptionPresetPosition.prepend.value
    append_position = CaptionPresetPosition.append.value

    scoped = [
        p
        for p in all_active
        if p.account_id is None or p.account_id == account_id
    ]
    scoped.sort(key=lambda p: p.id)

    pre_global = [
        p for p in scoped
        if p.account_id is None and p.position == prepend_position
    ]
    pre_scoped = [
        p for p in scoped
        if p.account_id == account_id and p.position == prepend_position
    ]
    app_scoped = [
        p for p in scoped
        if p.account_id == account_id and p.position == append_position
    ]
    app_global = [
        p for p in scoped
        if p.account_id is None and p.position == append_position
    ]
    return pre_global + pre_scoped + app_scoped + app_global


async def list_all_presets(
    db: AsyncSession, *, account_id: str | None = None
) -> Sequence[CaptionPresetRow]:
    """Для UI: все пресеты (активные + неактивные). Фильтр по scope опционально.

    Если ``account_id`` задан — вернёт только глобальные + scoped к этому аккаунту.
    Если None — все пресеты независимо от scope.
    """
    stmt = select(CaptionPresetRow).order_by(CaptionPresetRow.id.desc())
    if account_id is not None:
        stmt = stmt.where(
            (CaptionPresetRow.account_id == account_id)
            | (CaptionPresetRow.account_id.is_(None))
        )
    result = await db.execute(stmt)
    return result.scalars().all()


async def create_preset(
    db: AsyncSession,
    *,
    name: str,
    position: str,
    content: str,
    account_id: str | None,
) -> CaptionPresetRow:
    row = CaptionPresetRow(
        name=name,
        position=position,
        content=content,
        account_id=account_id,
        is_active=True,
    )
    db.add(row)
    await db.flush()
    await db.refresh(row)
    return row


async def update_preset(
    db: AsyncSession,
    preset_id: int,
    *,
    name: str | None = None,
    position: str | None = None,
    content: str | None = None,
    account_id: str | None = None,
    is_active: bool | None = None,
) -> CaptionPresetRow | None:
    row = await db.get(CaptionPresetRow, preset_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if position is not None:
        row.position = position
    if content is not None:
        row.content = content
    if account_id is not None:
        row.account_id = account_id or None
    if is_active is not None:
        row.is_active = is_active
    await db.flush()
    await db.refresh(row)
    return row


async def delete_preset(db: AsyncSession, preset_id: int) -> None:
    row = await db.get(CaptionPresetRow, preset_id)
    if row is not None:
        await db.delete(row)
        await db.flush()
