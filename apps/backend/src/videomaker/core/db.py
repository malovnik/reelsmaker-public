"""SQLAlchemy engine + sessionmaker + Base."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from videomaker.core.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _configure_sqlite_connection(dbapi_connection, connection_record) -> None:
    """PRAGMA-настройка каждого нового SQLite-соединения.

    * ``foreign_keys=ON`` — иначе ``ON DELETE CASCADE`` игнорируется SQLite.
    * ``journal_mode=WAL`` — конкурентные читатели не блокируют писателя
      (параллельные ffmpeg-рендеры / джобы).
    * ``busy_timeout=30000`` — ждать до 30 с при заблокированной БД вместо
      мгновенного ``database is locked``.
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        settings.ensure_directories()
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            future=True,
            connect_args={"timeout": 30},
        )
        if settings.database_url.startswith("sqlite"):
            event.listen(
                _engine.sync_engine,
                "connect",
                _configure_sqlite_connection,
            )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _sessionmaker


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    sm = get_sessionmaker()
    async with sm() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _sessionmaker = None
