# Publer Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить legacy YouTube/IG OAuth шедулер на Publer Business API. Пакетная публикация лайкнутых рилсов, группировка по проектам-папкам, уникальные caption per account, пресеты prepend/append, отдельная вкладка «Шедулер» с bulk-auto + ручным режимом.

**Architecture:** Один HTTP-клиент httpx для Publer API v1 (`Bearer-API` + `Publer-Workspace-Id`). Новая доменная модель: `Project` → `Job` (FK) → `Artifact(reel)`. Per-account `AccountProfile` + `CaptionPreset` (position=prepend/append) питают генерацию caption через Gemini Flash Lite. Campaign = pool лайкнутых рилсов × список аккаунтов × расписание. Async worker опрашивает очередь `ScheduleAssignment` и доставляет в Publer bulk POST. Timezone system-wide: `Asia/Ho_Chi_Minh` (+07).

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic + Pydantic v2; httpx 0.28; Gemini 2.5 Flash Lite; Next.js 16 + React 19 + Tailwind 4; Publer Business API v1.

**Known runtime constants (probe 2026-04-23):**
- Workspace id: `69e5fe51d43c84a890edd082`
- IG account `Malov Nik`: `69e9fdef152e6a68e48ef567`
- IG account `Никита Малов | ИИ Первопроходец`: `69e5fea390bea7026a01f04b`
- YT account `Малов Никита`: `69e5fec390bea7026a01f0af`

**Build gates (запускать после каждой Python-задачи):**
```bash
cd apps/backend && uv run ruff check src/videomaker/ && uv run pyright src/videomaker/<touched_files>
```

**Frontend gates (после каждой TS-задачи):**
```bash
cd apps/frontend && npx tsc --noEmit -p tsconfig.json
```

**No new unit tests** (videomaker constraint — build gates only). **No mocks, no stubs, no TODO/FIXME.** Код production-ready.

---

## File Structure

### Backend (create)
- `apps/backend/src/videomaker/services/publer/__init__.py` — пакет-маркер
- `apps/backend/src/videomaker/services/publer/client.py` — httpx async клиент (auth, retry, rate limit)
- `apps/backend/src/videomaker/services/publer/schemas.py` — Pydantic v2 запросы/ответы Publer
- `apps/backend/src/videomaker/services/publer/media_uploader.py` — upload video file ≤200MB
- `apps/backend/src/videomaker/services/publer/post_builder.py` — сборка bulk payload
- `apps/backend/src/videomaker/services/publer/caption_generator.py` — Flash Lite + preset applier
- `apps/backend/src/videomaker/services/publer/scheduler_service.py` — фасад: создание campaign, расчёт расписания
- `apps/backend/src/videomaker/services/publer/worker.py` — async loop delivery
- `apps/backend/src/videomaker/services/publer/preset_applier.py` — detach для чистого модуля
- `apps/backend/src/videomaker/services/projects_store.py` — CRUD проектов
- `apps/backend/src/videomaker/services/account_profiles_store.py` — CRUD профилей аккаунтов
- `apps/backend/src/videomaker/services/scheduler_campaigns_store.py` — CRUD campaigns/assignments
- `apps/backend/src/videomaker/api/routes/projects.py` — REST
- `apps/backend/src/videomaker/api/routes/scheduler.py` — REST (accounts, profiles, presets, campaigns, assignments)
- `apps/backend/src/videomaker/prompts_data/publer_caption.md` — system prompt caption gen
- `apps/backend/scripts/publer_probe.py` — уже создан, остаётся
- `apps/backend/alembic/versions/<rev>_publer_scheduler.py` — миграция

### Backend (rewrite)
- `apps/backend/src/videomaker/models/scheduler.py` — удаление OAuth-схемы, новая Publer-схема

### Backend (delete)
- `apps/backend/src/videomaker/services/scheduler_worker.py`
- `apps/backend/src/videomaker/services/scheduled_posts_store.py`
- `apps/backend/src/videomaker/services/connections_store.py`

### Backend (modify)
- `apps/backend/src/videomaker/models/job_orm.py` — добавить `project_id` FK
- `apps/backend/src/videomaker/main.py` — зарегистрировать новые роуты, подключить worker
- `apps/backend/src/videomaker/services/prompts.py` — регистрация `publer_caption`
- `apps/backend/src/videomaker/core/settings.py` — `PUBLER_API_KEY`, `PUBLER_WORKSPACE_ID`, `PUBLER_SCHEDULER_TZ`

### Frontend (create)
- `apps/frontend/src/app/scheduler/page.tsx` — dashboard (campaigns + queue)
- `apps/frontend/src/app/scheduler/new/page.tsx` — wizard: source → destinations → schedule
- `apps/frontend/src/app/scheduler/presets/page.tsx` — управление пресетами caption
- `apps/frontend/src/app/scheduler/accounts/page.tsx` — профили аккаунтов
- `apps/frontend/src/app/projects/page.tsx` — управление проектами
- `apps/frontend/src/components/scheduler/ReelPicker.tsx` — выбор лайкнутых рилсов
- `apps/frontend/src/components/scheduler/AccountsPicker.tsx`
- `apps/frontend/src/components/scheduler/ScheduleTimeline.tsx`
- `apps/frontend/src/components/scheduler/CaptionGrid.tsx` — reel×account edit
- `apps/frontend/src/components/scheduler/CaptionPresetEditor.tsx`
- `apps/frontend/src/components/scheduler/AccountProfileEditor.tsx`
- `apps/frontend/src/components/nav/SchedulerNavItem.tsx` — вкладка в header
- `apps/frontend/src/lib/api/scheduler.ts`
- `apps/frontend/src/lib/api/projects.ts`

---

## Task List

### Task 1: Удалить legacy scheduler (YouTube/IG OAuth)

**Files:**
- Delete: `apps/backend/src/videomaker/services/scheduler_worker.py`
- Delete: `apps/backend/src/videomaker/services/scheduled_posts_store.py`
- Delete: `apps/backend/src/videomaker/services/connections_store.py`
- Modify: `apps/backend/src/videomaker/models/scheduler.py` (полная перезапись на пустой placeholder — классы заменятся в Task 2)
- Modify: `apps/backend/src/videomaker/main.py` (снять импорты/startup-вызовы worker'а)
- Modify: `apps/backend/src/videomaker/api/routes/*` (если есть роуты legacy-шедулера — снять)

- [ ] **Step 1: Удалить файлы legacy**

```bash
rm apps/backend/src/videomaker/services/scheduler_worker.py
rm apps/backend/src/videomaker/services/scheduled_posts_store.py
rm apps/backend/src/videomaker/services/connections_store.py
```

- [ ] **Step 2: Найти все ссылки на удалённые модули**

Используй Serena:
```
find_referencing_symbols(name_path="SocialPlatform", relative_path="apps/backend/src/videomaker/models/scheduler.py")
find_referencing_symbols(name_path="OAuthConnectionRow", relative_path="apps/backend/src/videomaker/models/scheduler.py")
find_referencing_symbols(name_path="ScheduledPostRow", relative_path="apps/backend/src/videomaker/models/scheduler.py")
```
Плюс `search_for_pattern("scheduler_worker|scheduled_posts_store|connections_store", restrict_search_to_code_files=True)`.

- [ ] **Step 3: Снять все импорты и вызовы**

Для каждого найденного места — прочитать через `find_symbol(include_body=True)`, удалить строки импорта и вызова. В `main.py` удалить `startup` регистрацию worker'а, `router.include_router(...)` легаси-роутов.

- [ ] **Step 4: Очистить `models/scheduler.py`**

Через Serena `replace_symbol_body` или Edit — содержимое файла привести к:
```python
"""Publer scheduler ORM models.

Legacy YouTube/IG OAuth модели удалены 2026-04-23.
Новые модели добавятся в Task 2.
"""
from __future__ import annotations
```

- [ ] **Step 5: Build gate**

```bash
cd apps/backend && uv run ruff check src/videomaker/ && uv run pyright src/videomaker/
```
Expected: 0 new errors. Если остались ссылки на удалённые символы — вернуться в Step 3.

- [ ] **Step 6: Commit**

```bash
git add -A apps/backend/src/videomaker/
git commit -m "refactor(scheduler): remove legacy YouTube/IG OAuth scheduler — preparing Publer migration"
git push origin HEAD
```

---

### Task 2: ORM модели Publer-шедулера

**Files:**
- Modify: `apps/backend/src/videomaker/models/scheduler.py` (наполнить)
- Create: `apps/backend/src/videomaker/models/project.py`
- Modify: `apps/backend/src/videomaker/models/job_orm.py` (+ FK `project_id`)

- [ ] **Step 1: Создать `models/project.py`**

```python
"""Project: логическая группа джобов (папка).

Один проект может содержать много джобов (видео). Scheduler использует
проект как source для pool'а лайкнутых рилсов.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from videomaker.core.db import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    color: Mapped[str] = mapped_column(String(16), nullable=False, default="#6366f1")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )
```

- [ ] **Step 2: Добавить FK `project_id` в `JobRow`**

Через Serena: `find_symbol("JobRow", include_body=True, relative_path="apps/backend/src/videomaker/models/job_orm.py")`, затем `replace_symbol_body` — добавить:

```python
from sqlalchemy import ForeignKey

project_id: Mapped[int | None] = mapped_column(
    Integer, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
)
```

- [ ] **Step 3: Наполнить `models/scheduler.py`**

Классы (все через SQLAlchemy 2 mapped_column, Base из `videomaker.core.db`):

```python
"""Publer scheduler ORM models."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from videomaker.core.db import Base


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PublerNetwork(StrEnum):
    instagram = "instagram"
    youtube = "youtube"


class AssignmentStatus(StrEnum):
    draft = "draft"
    queued = "queued"
    uploading = "uploading"
    scheduled = "scheduled"
    published = "published"
    failed = "failed"
    cancelled = "cancelled"


class CaptionPresetPosition(StrEnum):
    prepend = "prepend"
    append = "append"


class AccountProfileRow(Base):
    """Профиль Publer-аккаунта: язык/тон/ЦА/дефолтные хештеги.

    Используется caption_generator как контекст для уникального текста.
    Primary key — не autoincrement, а publer_account_id (24-hex string).
    """

    __tablename__ = "account_profiles"

    publer_account_id: Mapped[str] = mapped_column(String(24), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    network: Mapped[str] = mapped_column(String(32), nullable=False)

    language: Mapped[str] = mapped_column(String(8), nullable=False, default="ru")
    audience: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tone: Mapped[str] = mapped_column(Text, nullable=False, default="")
    default_hashtags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    banned_words_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    cta_style: Mapped[str] = mapped_column(Text, nullable=False, default="")
    max_caption_length: Mapped[int] = mapped_column(Integer, nullable=False, default=2200)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


class CaptionPresetRow(Base):
    """Пресет текста, добавляемого в начало ИЛИ в конец сгенерированного caption.

    Может быть привязан к конкретному account_id (scope) или быть глобальным
    (account_id IS NULL). На один пост — применяется первый глобальный
    prepend + первый scoped prepend + generated + первый scoped append +
    первый глобальный append, если выбраны.
    """

    __tablename__ = "caption_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    position: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    account_id: Mapped[str | None] = mapped_column(
        String(24),
        ForeignKey("account_profiles.publer_account_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


class ScheduleCampaignRow(Base):
    """Группа запланированных публикаций (источник + назначения + расписание)."""

    __tablename__ = "schedule_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    tz: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Ho_Chi_Minh")
    time_of_day: Mapped[str] = mapped_column(String(8), nullable=False)  # "HH:MM"
    dates_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)  # ISO dates
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )


class ScheduleAssignmentRow(Base):
    """Одна публикация: (reel_artifact, account) → дата/время + готовый caption."""

    __tablename__ = "schedule_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("schedule_campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reel_artifact_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    publer_account_id: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    network: Mapped[str] = mapped_column(String(32), nullable=False)

    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    caption: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    applied_preset_ids_json: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)

    scheduled_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=AssignmentStatus.draft.value, index=True
    )
    publer_media_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publer_job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publer_post_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publer_post_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now, onupdate=_utc_now
    )
```

- [ ] **Step 4: Build gate**

```bash
cd apps/backend && uv run ruff check src/videomaker/models/ && uv run pyright src/videomaker/models/scheduler.py src/videomaker/models/project.py src/videomaker/models/job_orm.py
```
Expected: 0 new errors.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/src/videomaker/models/
git commit -m "feat(scheduler): Publer ORM — Project/AccountProfile/CaptionPreset/ScheduleCampaign/Assignment"
git push origin HEAD
```

---

### Task 3: Alembic миграция

**Files:**
- Create: `apps/backend/alembic/versions/<auto>_publer_scheduler.py`

- [ ] **Step 1: Сгенерировать миграцию**

```bash
cd apps/backend
uv run alembic revision --autogenerate -m "publer_scheduler_schema"
```
Expected: создан файл `apps/backend/alembic/versions/<hash>_publer_scheduler_schema.py` с:
- `op.create_table('projects', ...)`
- `op.create_table('account_profiles', ...)`
- `op.create_table('caption_presets', ...)`
- `op.create_table('schedule_campaigns', ...)`
- `op.create_table('schedule_assignments', ...)`
- `op.add_column('jobs', sa.Column('project_id', ...))`
- Drop старых таблиц `oauth_connections`, `scheduled_posts` (если autogenerate их видит)

- [ ] **Step 2: Проверить autogenerate вручную**

Открыть сгенерированный файл, проверить:
1. Все 5 `create_table` на месте с правильными колонками
2. FK на `jobs.id`, `artifacts.id`, `schedule_campaigns.id`, `account_profiles.publer_account_id` с `ondelete='CASCADE'` где надо
3. `op.add_column('jobs', project_id ...)` — с `ForeignKey('projects.id', ondelete='SET NULL')`
4. Drop таблиц `oauth_connections` и `scheduled_posts` присутствует (если их Alembic задетектил)

Если автоген не увидел drop — дописать вручную в начале `upgrade()`:
```python
op.drop_table('scheduled_posts')
op.drop_table('oauth_connections')
```

- [ ] **Step 3: Применить миграцию локально**

```bash
cd apps/backend && uv run alembic upgrade head
```
Expected: `INFO ... Running upgrade ... -> <hash>, publer_scheduler_schema`

- [ ] **Step 4: Проверить схему БД**

```bash
cd apps/backend && uv run python -c "
import sqlite3
conn = sqlite3.connect('data/videomaker.sqlite3')
cur = conn.cursor()
for row in cur.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\"):
    print(row[0])
"
```
Expected output содержит: `account_profiles, caption_presets, projects, schedule_assignments, schedule_campaigns`. Отсутствует: `oauth_connections, scheduled_posts`.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/alembic/versions/
git commit -m "feat(scheduler): alembic migration — Publer schema + drop legacy oauth tables"
git push origin HEAD
```

---

### Task 4: Publer HTTP-клиент + Pydantic schemas

**Files:**
- Create: `apps/backend/src/videomaker/services/publer/__init__.py`
- Create: `apps/backend/src/videomaker/services/publer/schemas.py`
- Create: `apps/backend/src/videomaker/services/publer/client.py`
- Modify: `apps/backend/src/videomaker/core/settings.py` (+ PUBLER_* переменные)

- [ ] **Step 1: Расширить settings**

Через Serena `find_symbol("Settings", relative_path="apps/backend/src/videomaker/core/settings.py")` + `replace_symbol_body`. Добавить поля:
```python
publer_api_key: str = Field(default="", alias="PUBLER_API_KEY")
publer_workspace_id: str = Field(default="", alias="PUBLER_WORKSPACE_ID")
publer_scheduler_tz: str = Field(default="Asia/Ho_Chi_Minh", alias="PUBLER_SCHEDULER_TZ")
publer_base_url: str = Field(
    default="https://app.publer.com/api/v1", alias="PUBLER_BASE_URL"
)
publer_request_timeout_sec: float = Field(default=30.0, alias="PUBLER_REQUEST_TIMEOUT_SEC")
```

- [ ] **Step 2: Создать `publer/__init__.py`**

```python
"""Publer Business API integration."""
```

- [ ] **Step 3: Создать `publer/schemas.py`**

Pydantic v2 модели (все с `model_config = ConfigDict(extra="allow")` для forward-compat Publer-а):
- `PublerWorkspace(id: str, name: str, role: str | None = None)`
- `PublerAccount(id: str, provider: str, type: str | None = None, name: str | None = None, status: str | None = None)`
- `PublerMediaThumbnail(id: str, small: str, real: str)`
- `PublerMediaRef(id: str, path: str, type: str, thumbnails: list[PublerMediaThumbnail] = [], default_thumbnail: int = 0)`
- `PublerReelDetails(type: Literal["reel"] = "reel", feed: bool = True, audio: str | None = None)`
- `PublerShortDetails(type: Literal["short"] = "short", privacy: Literal["public","private","unlisted"] = "public")`
- `PublerInstagramNetwork(type: Literal["video"] = "video", text: str, media: list[PublerMediaRef], details: PublerReelDetails)`
- `PublerYoutubeNetwork(type: Literal["video"] = "video", title: str, text: str, media: list[PublerMediaRef], details: PublerShortDetails)`
- `PublerAccountTarget(id: str, scheduled_at: str | None = None, labels: list[str] = [])`  # scheduled_at = ISO 8601 с tz offset
- `PublerPost(networks: dict[str, PublerInstagramNetwork | PublerYoutubeNetwork], accounts: list[PublerAccountTarget])`
- `PublerBulk(state: Literal["scheduled","draft","scheduled_publish"] = "scheduled", posts: list[PublerPost])`
- `PublerScheduleRequest(bulk: PublerBulk)`
- `PublerJobStatus(status: Literal["working","complete","failed"], result: dict | None = None)`

- [ ] **Step 4: Создать `publer/client.py`**

Базовый каркас — async httpx клиент с retry (3 попытки, exponential 1s/3s/9s, уважать 429):

```python
"""HTTP-клиент Publer Business API v1."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from videomaker.core.settings import Settings
from videomaker.services.publer.schemas import (
    PublerAccount,
    PublerJobStatus,
    PublerScheduleRequest,
    PublerWorkspace,
)

log = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_SCHEDULE = (1.0, 3.0, 9.0)
_RATE_LIMIT_SLEEP = 125.0  # 100 req/2 min — при 429 ждём 2 мин + запас


class PublerClientError(RuntimeError):
    pass


class PublerClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.publer_api_key:
            raise PublerClientError("PUBLER_API_KEY не задан")
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=settings.publer_request_timeout_sec)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self, *, workspace: bool = True) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer-API {self._settings.publer_api_key}",
            "Content-Type": "application/json",
        }
        if workspace:
            if not self._settings.publer_workspace_id:
                raise PublerClientError("PUBLER_WORKSPACE_ID не задан")
            headers["Publer-Workspace-Id"] = self._settings.publer_workspace_id
        return headers

    async def _request(self, method: str, path: str, *, workspace: bool = True, **kwargs: Any) -> httpx.Response:
        url = f"{self._settings.publer_base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.request(method, url, headers=self._headers(workspace=workspace), **kwargs)
                if resp.status_code == 429:
                    log.warning("publer_rate_limited", extra={"path": path, "sleep": _RATE_LIMIT_SLEEP})
                    await asyncio.sleep(_RATE_LIMIT_SLEEP)
                    continue
                if resp.status_code >= 500:
                    raise PublerClientError(f"Publer 5xx on {path}: {resp.status_code}")
                return resp
            except (httpx.HTTPError, PublerClientError) as exc:
                last_exc = exc
                if attempt + 1 >= _MAX_RETRIES:
                    break
                await asyncio.sleep(_BACKOFF_SCHEDULE[attempt])
        raise PublerClientError(f"Publer {method} {path} провалился: {last_exc}")

    async def list_workspaces(self) -> list[PublerWorkspace]:
        resp = await self._request("GET", "/workspaces", workspace=False)
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("workspaces") or data.get("data") or []
        return [PublerWorkspace.model_validate(item) for item in items]

    async def list_accounts(self) -> list[PublerAccount]:
        resp = await self._request("GET", "/accounts")
        resp.raise_for_status()
        data = resp.json()
        items = data if isinstance(data, list) else data.get("accounts") or data.get("data") or []
        return [PublerAccount.model_validate(item) for item in items]

    async def upload_media_file(self, *, file_path: str, filename: str, content_type: str) -> str:
        """Multipart upload, returns Publer media id."""
        with open(file_path, "rb") as fh:
            files = {"file": (filename, fh, content_type)}
            headers = {k: v for k, v in self._headers().items() if k != "Content-Type"}
            url = f"{self._settings.publer_base_url}/media"
            resp = await self._client.post(url, headers=headers, files=files)
        resp.raise_for_status()
        data = resp.json()
        media_id = data.get("id") or (data.get("data") or {}).get("id")
        if not media_id:
            raise PublerClientError(f"upload_media_file: id отсутствует в ответе {data}")
        return str(media_id)

    async def schedule_posts(self, payload: PublerScheduleRequest) -> str:
        resp = await self._request(
            "POST",
            "/posts/schedule",
            json=payload.model_dump(mode="json", exclude_none=True),
        )
        resp.raise_for_status()
        data = resp.json()
        job_id = (data.get("data") or {}).get("job_id") or data.get("job_id")
        if not job_id:
            raise PublerClientError(f"schedule_posts: job_id отсутствует {data}")
        return str(job_id)

    async def get_job_status(self, job_id: str) -> PublerJobStatus:
        resp = await self._request("GET", f"/job_status/{job_id}")
        resp.raise_for_status()
        data = resp.json()
        payload = data.get("data") or data
        return PublerJobStatus.model_validate(payload)
```

- [ ] **Step 5: Build gate**

```bash
cd apps/backend && uv run ruff check src/videomaker/services/publer/ src/videomaker/core/settings.py && uv run pyright src/videomaker/services/publer/ src/videomaker/core/settings.py
```

- [ ] **Step 6: Commit**

```bash
git add apps/backend/src/videomaker/services/publer/ apps/backend/src/videomaker/core/settings.py
git commit -m "feat(publer): HTTP client + Pydantic schemas + settings"
git push origin HEAD
```

---

### Task 5: Caption generator + preset applier

**Files:**
- Create: `apps/backend/src/videomaker/prompts_data/publer_caption.md`
- Modify: `apps/backend/src/videomaker/services/prompts.py` (регистрация)
- Create: `apps/backend/src/videomaker/services/publer/preset_applier.py`
- Create: `apps/backend/src/videomaker/services/publer/caption_generator.py`

- [ ] **Step 1: Создать системный промпт `publer_caption.md`**

```markdown
=== IDENTITY ===

Ты — SMM-копирайтер. Пишешь caption для видео-рилса под конкретный соц-аккаунт. Опираешься на транскрипт-хук видео и профиль аккаунта (язык / тон / ЦА / запрещённые слова / стиль CTA).

=== RULES ===

1. Язык caption'а — строго `language` из профиля аккаунта.
2. Стиль речи — строго `tone` из профиля. Если `tone` пуст — нейтральный живой язык.
3. CTA — в конце caption'а, строго по `cta_style`. Если пуст — без CTA.
4. Запрещённые слова из `banned_words` НЕ используй.
5. Не повторяй хук дословно — перефразируй.
6. Caption не длиннее `max_caption_length` символов, включая хештеги.
7. Хештеги — отдельным массивом, не в теле caption'а. Максимум 7 релевантных.
8. Не добавляй эмодзи если `tone` не допускает.
9. Для YouTube — дополнительно `title` ≤ 100 символов, провокативный, без clickbait-обмана.
10. Для Instagram — `title` не возвращай (пустая строка).

=== OUTPUT SCHEMA (strict JSON) ===

```json
{
  "title": "...",
  "caption": "...",
  "hashtags": ["#tag1", "#tag2"]
}
```

Никакого текста вне JSON. Если что-то невозможно вычислить — верни пустую строку/массив, но JSON всегда валиден.
```

- [ ] **Step 2: Зарегистрировать промпт в `prompts.py`**

Через Serena `find_symbol("PromptKey", include_body=True)` + `find_symbol("DEFAULT_PROMPTS", include_body=True)` → добавить enum entry `publer_caption = "publer_caption"` и загрузить файл через существующий `_load_stage_prompt("publer_caption.md")`.

- [ ] **Step 3: Создать `preset_applier.py`**

```python
"""Применение caption-пресетов (prepend/append) к сгенерированному тексту."""
from __future__ import annotations

from videomaker.models.scheduler import CaptionPresetPosition, CaptionPresetRow


def apply_presets(
    *,
    generated_caption: str,
    presets: list[CaptionPresetRow],
) -> tuple[str, list[int]]:
    """Склеивает итоговый caption из активных пресетов + сгенерированного текста.

    Порядок: все prepend (в порядке создания) + generated + все append (в порядке создания).
    Возвращает (итоговый_текст, применённые_preset_ids).
    """
    prepend_parts: list[str] = []
    append_parts: list[str] = []
    applied: list[int] = []

    for preset in presets:
        if not preset.is_active:
            continue
        applied.append(preset.id)
        if preset.position == CaptionPresetPosition.prepend.value:
            prepend_parts.append(preset.content.strip())
        elif preset.position == CaptionPresetPosition.append.value:
            append_parts.append(preset.content.strip())

    pieces: list[str] = []
    pieces.extend(prepend_parts)
    if generated_caption.strip():
        pieces.append(generated_caption.strip())
    pieces.extend(append_parts)
    return ("\n\n".join(p for p in pieces if p), applied)
```

- [ ] **Step 4: Создать `caption_generator.py`**

```python
"""Генерация caption + title per (reel × account) через Gemini Flash Lite."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from videomaker.models.reel_plan import ReelPlan
from videomaker.models.scheduler import AccountProfileRow
from videomaker.services.llm.client import LLMClient
from videomaker.services.prompts import PromptKey, get_prompt_store

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeneratedCaption:
    title: str
    caption: str
    hashtags: list[str]


async def generate_caption(
    *,
    reel: ReelPlan,
    profile: AccountProfileRow,
    llm: LLMClient,
) -> GeneratedCaption:
    system = get_prompt_store().get(PromptKey.publer_caption).system
    user = _build_user_message(reel=reel, profile=profile)

    response = await llm.complete_json(
        system=system,
        user=user,
        temperature=0.7,
        max_tokens=4096,
    )

    try:
        parsed = json.loads(response) if isinstance(response, str) else response
    except json.JSONDecodeError as exc:
        log.warning("caption_json_parse_failed", extra={"reel_id": reel.reel_id, "error": str(exc)})
        raise

    title = str(parsed.get("title") or "")
    caption = str(parsed.get("caption") or "")
    hashtags = [str(h) for h in (parsed.get("hashtags") or []) if isinstance(h, str)]
    return GeneratedCaption(title=title, caption=caption, hashtags=hashtags)


def _build_user_message(*, reel: ReelPlan, profile: AccountProfileRow) -> str:
    return (
        f"АККАУНТ: {profile.display_name} ({profile.network})\n"
        f"LANGUAGE: {profile.language}\n"
        f"AUDIENCE: {profile.audience or '(не задано)'}\n"
        f"TONE: {profile.tone or '(нейтральный)'}\n"
        f"CTA_STYLE: {profile.cta_style or '(без CTA)'}\n"
        f"DEFAULT_HASHTAGS: {', '.join(profile.default_hashtags_json) or '(нет)'}\n"
        f"BANNED_WORDS: {', '.join(profile.banned_words_json) or '(нет)'}\n"
        f"MAX_CAPTION_LENGTH: {profile.max_caption_length}\n"
        f"\n"
        f"РИЛС:\n"
        f"HOOK: {reel.hook}\n"
        f"TARGET_AUDIENCE_ORIG: {reel.target_audience or '(не задано)'}\n"
        f"DURATION_SEC: {reel.predicted_duration_sec:.1f}\n"
        f"SEGMENTS_REASONING: {' | '.join(s.reasoning for s in reel.segments[:3])}\n"
        f"\n"
        f"Верни строго JSON {{title, caption, hashtags}}."
    )
```

- [ ] **Step 5: Build gate**

```bash
cd apps/backend && uv run ruff check src/videomaker/services/publer/ src/videomaker/services/prompts.py && uv run pyright src/videomaker/services/publer/caption_generator.py src/videomaker/services/publer/preset_applier.py src/videomaker/services/prompts.py
```

- [ ] **Step 6: Commit**

```bash
git add apps/backend/src/videomaker/services/publer/ apps/backend/src/videomaker/services/prompts.py apps/backend/src/videomaker/prompts_data/publer_caption.md
git commit -m "feat(publer): caption_generator + preset_applier + system prompt"
git push origin HEAD
```

---

### Task 6: Scheduler service (фасад + расписание)

**Files:**
- Create: `apps/backend/src/videomaker/services/publer/post_builder.py`
- Create: `apps/backend/src/videomaker/services/publer/media_uploader.py`
- Create: `apps/backend/src/videomaker/services/publer/scheduler_service.py`
- Create: `apps/backend/src/videomaker/services/projects_store.py`
- Create: `apps/backend/src/videomaker/services/account_profiles_store.py`
- Create: `apps/backend/src/videomaker/services/scheduler_campaigns_store.py`

- [ ] **Step 1: Создать `projects_store.py`**

Async CRUD через SQLAlchemy session:
- `list_projects(db) -> list[ProjectRow]`
- `create_project(db, *, name, description, color) -> ProjectRow`
- `get_project(db, project_id) -> ProjectRow | None`
- `update_project(db, project_id, **fields) -> ProjectRow`
- `delete_project(db, project_id) -> None`
- `assign_job_to_project(db, job_id, project_id | None) -> None`
- `list_jobs_by_project(db, project_id) -> list[JobRow]`

- [ ] **Step 2: Создать `account_profiles_store.py`**

CRUD для `AccountProfileRow` + `CaptionPresetRow`:
- `list_profiles(db) -> list[AccountProfileRow]`
- `upsert_profile(db, *, publer_account_id, display_name, network, **fields) -> AccountProfileRow`
- `delete_profile(db, publer_account_id) -> None`
- `list_presets(db, account_id: str | None = None) -> list[CaptionPresetRow]` (возвращает активные + заданного scope + глобальные)
- `create_preset(db, *, name, position, content, account_id) -> CaptionPresetRow`
- `update_preset(db, preset_id, **fields) -> CaptionPresetRow`
- `delete_preset(db, preset_id) -> None`

`list_presets` возвращает в порядке: сначала глобальные prepend, потом scoped prepend, потом scoped append, потом глобальные append — чтобы `apply_presets` просто перебирал в этом порядке.

- [ ] **Step 3: Создать `scheduler_campaigns_store.py`**

CRUD для `ScheduleCampaignRow` + `ScheduleAssignmentRow`:
- `create_campaign(db, *, name, tz, time_of_day, dates) -> ScheduleCampaignRow`
- `list_campaigns(db, *, status=None, limit=50) -> list[ScheduleCampaignRow]`
- `get_campaign(db, id) -> ScheduleCampaignRow | None`
- `delete_campaign(db, id) -> None`
- `create_assignment(db, **fields) -> ScheduleAssignmentRow`
- `list_assignments(db, *, campaign_id=None, status=None) -> list[ScheduleAssignmentRow]`
- `get_assignment(db, id) -> ScheduleAssignmentRow | None`
- `update_assignment(db, id, **fields) -> ScheduleAssignmentRow`
- `list_pending_due(db, *, now_utc) -> list[ScheduleAssignmentRow]` — `status=queued AND scheduled_at_utc<=now_utc`

- [ ] **Step 4: Создать `publer/post_builder.py`**

```python
"""Сборка PublerScheduleRequest из доменных данных."""
from __future__ import annotations

from videomaker.models.scheduler import PublerNetwork, ScheduleAssignmentRow
from videomaker.services.publer.schemas import (
    PublerAccountTarget,
    PublerBulk,
    PublerInstagramNetwork,
    PublerMediaRef,
    PublerPost,
    PublerReelDetails,
    PublerScheduleRequest,
    PublerShortDetails,
    PublerYoutubeNetwork,
)

LABEL = "videomaker-auto"


def build_schedule_request(
    *,
    assignments: list[ScheduleAssignmentRow],
    media_refs_by_assignment_id: dict[int, PublerMediaRef],
) -> PublerScheduleRequest:
    """Каждое assignment → отдельный PublerPost (уникальный caption per account)."""
    posts: list[PublerPost] = []
    for a in assignments:
        media = media_refs_by_assignment_id[a.id]
        if a.network == PublerNetwork.instagram.value:
            net = PublerInstagramNetwork(
                text=a.caption,
                media=[media],
                details=PublerReelDetails(feed=True),
            )
            networks = {"instagram": net}
        elif a.network == PublerNetwork.youtube.value:
            net = PublerYoutubeNetwork(
                title=a.title,
                text=a.caption,
                media=[media],
                details=PublerShortDetails(privacy="public"),
            )
            networks = {"youtube": net}
        else:
            raise ValueError(f"Неизвестный network: {a.network}")

        posts.append(PublerPost(
            networks=networks,
            accounts=[PublerAccountTarget(
                id=a.publer_account_id,
                scheduled_at=a.scheduled_at_utc.isoformat(),
                labels=[LABEL, f"campaign-{a.campaign_id}"],
            )],
        ))
    return PublerScheduleRequest(bulk=PublerBulk(state="scheduled", posts=posts))
```

- [ ] **Step 5: Создать `publer/media_uploader.py`**

```python
"""Upload рилса → Publer media + кешируемый media_id."""
from __future__ import annotations

import logging
from pathlib import Path

from videomaker.services.publer.client import PublerClient

log = logging.getLogger(__name__)

_MAX_DIRECT_UPLOAD_BYTES = 200 * 1024 * 1024  # 200 MB


async def upload_reel_to_publer(
    *,
    reel_path: Path,
    client: PublerClient,
) -> str:
    """Возвращает media_id. Raises PublerClientError если больше 200 MB
    (требуется URL flow — добавляется отдельной задачей при необходимости).
    """
    size = reel_path.stat().st_size
    if size > _MAX_DIRECT_UPLOAD_BYTES:
        raise ValueError(
            f"Reel {reel_path.name} = {size} bytes > 200 MB. URL-flow пока не реализован."
        )

    media_id = await client.upload_media_file(
        file_path=str(reel_path),
        filename=reel_path.name,
        content_type="video/mp4",
    )
    log.info("publer_media_uploaded", extra={"reel": reel_path.name, "media_id": media_id})
    return media_id
```

- [ ] **Step 6: Создать `publer/scheduler_service.py`** (главный фасад)

```python
"""Scheduler service — фасад для создания кампаний и доставки в Publer."""
from __future__ import annotations

import logging
from datetime import datetime, time
from zoneinfo import ZoneInfo

from videomaker.models.scheduler import (
    AccountProfileRow,
    AssignmentStatus,
    ScheduleAssignmentRow,
    ScheduleCampaignRow,
)

log = logging.getLogger(__name__)


def compute_scheduled_at_utc(*, date_iso: str, time_of_day: str, tz_name: str) -> datetime:
    """date_iso=YYYY-MM-DD, time_of_day=HH:MM, tz=IANA → datetime UTC."""
    y, m, d = (int(p) for p in date_iso.split("-"))
    hh, mm = (int(p) for p in time_of_day.split(":"))
    tz = ZoneInfo(tz_name)
    local = datetime(y, m, d, hh, mm, tzinfo=tz)
    return local.astimezone(ZoneInfo("UTC"))
```

Плюс главная функция `build_campaign_from_pool` — принимает: list of (reel_artifact_id, job_id), list of publer_account_id, time_of_day, dates, tz. Для каждой пары (reel, account) генерит caption через `caption_generator.generate_caption`, применяет пресеты, считает scheduled_at_utc (round-robin по датам: assignment_index % len(dates) → date), создаёт `ScheduleAssignmentRow` в статусе `draft`. Возвращает `ScheduleCampaignRow` + `list[ScheduleAssignmentRow]`.

Псевдо-план распределения по датам (полная реализация в коде):
```
assignment_idx = 0
for reel in reels:
    for account in accounts:
        date = dates[assignment_idx % len(dates)]
        scheduled_at = compute_scheduled_at_utc(date, time_of_day, tz_name)
        assignment_idx += 1
```

- [ ] **Step 7: Build gate**

```bash
cd apps/backend && uv run ruff check src/videomaker/services/ && uv run pyright src/videomaker/services/publer/ src/videomaker/services/projects_store.py src/videomaker/services/account_profiles_store.py src/videomaker/services/scheduler_campaigns_store.py
```

- [ ] **Step 8: Commit**

```bash
git add apps/backend/src/videomaker/services/
git commit -m "feat(publer): scheduler_service + stores + post_builder + media_uploader"
git push origin HEAD
```

---

### Task 7: REST API endpoints

**Files:**
- Create: `apps/backend/src/videomaker/api/routes/projects.py`
- Create: `apps/backend/src/videomaker/api/routes/scheduler.py`
- Modify: `apps/backend/src/videomaker/main.py` — register routers
- Modify: `apps/backend/src/videomaker/api/routes/jobs.py` — добавить фильтр `GET /artifacts/liked`

- [ ] **Step 1: `routes/projects.py`**

Эндпоинты:
- `GET /api/v1/projects` → list projects
- `POST /api/v1/projects` `{name, description, color}` → create
- `GET /api/v1/projects/{id}` → detail + jobs[]
- `PATCH /api/v1/projects/{id}` → update
- `DELETE /api/v1/projects/{id}` → delete (jobs → project_id=NULL)
- `PATCH /api/v1/jobs/{job_id}/project` `{project_id: int | null}` → assign/unassign

Все через FastAPI `APIRouter(prefix="/api/v1")`, Pydantic DTO `ProjectRead/Create/Update`.

- [ ] **Step 2: Endpoint лайкнутых рилсов в `jobs.py`**

Добавить через Serena `insert_after_symbol` рядом с существующим `update_artifact_like`:

```python
@router.get("/artifacts/liked", response_model=list[ArtifactRead])
async def list_liked_reels(
    project_id: int | None = None,
    job_id: str | None = None,
    limit: int = 100,
    service: JobService = Depends(get_job_service),
) -> list[ArtifactRead]:
    """Все артефакты kind='reel' где meta.liked='like'.

    Фильтры по project_id (через JobRow.project_id) и/или job_id.
    """
    return await service.list_liked_reels(project_id=project_id, job_id=job_id, limit=limit)
```

В `JobService` реализовать `list_liked_reels` через SQL: join `artifacts × jobs` где `artifacts.kind='reel' AND json_extract(artifacts.meta, '$.liked') = 'like'` + опциональные фильтры.

- [ ] **Step 3: `routes/scheduler.py`**

Эндпоинты (prefix `/api/v1/scheduler`):
- `GET /connection/status` → probe Publer (same as probe script) → `{ok, workspace, accounts_count}`
- `GET /accounts` → `list[PublerAccount]` напрямую из Publer
- `GET /accounts/profiles` → `list[AccountProfileRow]`
- `PUT /accounts/profiles/{publer_account_id}` → upsert
- `DELETE /accounts/profiles/{publer_account_id}`
- `GET /presets?account_id=` → `list[CaptionPresetRow]`
- `POST /presets` `{name, position, content, account_id?}` → create
- `PATCH /presets/{id}` → update
- `DELETE /presets/{id}`
- `GET /campaigns?status=` → list
- `POST /campaigns` `{name, time_of_day, dates, tz, reel_artifact_ids, account_ids}` → создаёт + запускает `build_campaign_from_pool` + возвращает campaign + drafts
- `GET /campaigns/{id}` → detail + assignments[]
- `POST /campaigns/{id}/approve` → переводит drafts → queued (worker подберёт)
- `DELETE /campaigns/{id}`
- `GET /assignments?campaign_id=` → list
- `PATCH /assignments/{id}` `{caption?, title?, hashtags?, scheduled_at_utc?}` — ручное редактирование
- `POST /assignments/{id}/cancel` → status=cancelled, попытка удалить в Publer через `DELETE /posts/{publer_post_id}` если опубликован
- `POST /manual/publish-one` `{reel_artifact_id, publer_account_id, scheduled_at_utc, custom_caption?, custom_title?}` — ручной режим: один клик, без campaign-обёртки

- [ ] **Step 4: Зарегистрировать роуты в `main.py`**

Serena: `find_symbol("app", ...)`, добавить:
```python
from videomaker.api.routes.projects import router as projects_router
from videomaker.api.routes.scheduler import router as scheduler_router
app.include_router(projects_router)
app.include_router(scheduler_router)
```

- [ ] **Step 5: Build gate**

```bash
cd apps/backend && uv run ruff check src/videomaker/ && uv run pyright src/videomaker/api/routes/projects.py src/videomaker/api/routes/scheduler.py src/videomaker/main.py
```

- [ ] **Step 6: Smoke эндпоинты локально**

```bash
cd apps/backend && PUBLER_API_KEY='...' PUBLER_WORKSPACE_ID=69e5fe51d43c84a890edd082 ./run.sh &
sleep 10
curl -s http://127.0.0.1:8000/api/v1/scheduler/connection/status | python3 -m json.tool
curl -s http://127.0.0.1:8000/api/v1/scheduler/accounts | python3 -m json.tool
```
Expected:
- `connection/status` → `{"ok": true, "workspace": "malovnik", "accounts_count": 3}`
- `/accounts` — 3 аккаунта с id `69e9fdef152e6a68e48ef567`, `69e5fea390bea7026a01f04b`, `69e5fec390bea7026a01f0af`

- [ ] **Step 7: Commit**

```bash
git add apps/backend/src/videomaker/api/ apps/backend/src/videomaker/main.py
git commit -m "feat(publer): REST API — projects, accounts, profiles, presets, campaigns, assignments, manual publish"
git push origin HEAD
```

---

### Task 8: Delivery worker

**Files:**
- Create: `apps/backend/src/videomaker/services/publer/worker.py`
- Modify: `apps/backend/src/videomaker/main.py` — стартовать worker в `lifespan`

- [ ] **Step 1: `publer/worker.py`**

```python
"""Background worker — опрашивает queued assignments и доставляет в Publer."""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from videomaker.core.db import AsyncSessionLocal
from videomaker.core.settings import Settings
from videomaker.models.scheduler import AssignmentStatus, ScheduleAssignmentRow
from videomaker.services.publer.client import PublerClient
from videomaker.services.publer.media_uploader import upload_reel_to_publer
from videomaker.services.publer.post_builder import build_schedule_request
from videomaker.services.publer.schemas import PublerMediaRef
from videomaker.services.scheduler_campaigns_store import (
    list_pending_due,
    update_assignment,
)

log = logging.getLogger(__name__)
POLL_INTERVAL_SEC = 30
MAX_ATTEMPTS = 3


class PublerWorker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="publer-worker")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        if not self._settings.publer_api_key:
            log.info("publer_worker_disabled_no_api_key")
            return
        async with PublerClient(self._settings) as client:
            while not self._stop.is_set():
                try:
                    await self._tick(client)
                except Exception:
                    log.exception("publer_worker_tick_failed")
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=POLL_INTERVAL_SEC)
                except TimeoutError:
                    continue

    async def _tick(self, client: PublerClient) -> None:
        async with AsyncSessionLocal() as db:
            due = await list_pending_due(db, now_utc=datetime.now(UTC))
            if not due:
                return
            for assignment in due:
                await self._deliver_one(db, client, assignment)

    async def _deliver_one(
        self,
        db: AsyncSession,
        client: PublerClient,
        assignment: ScheduleAssignmentRow,
    ) -> None:
        await update_assignment(
            db,
            assignment.id,
            status=AssignmentStatus.uploading.value,
            attempts=assignment.attempts + 1,
            last_attempt_at=datetime.now(UTC),
        )
        try:
            reel_path = self._resolve_reel_path(assignment)
            media_id = await upload_reel_to_publer(reel_path=reel_path, client=client)
            media_ref = PublerMediaRef(
                id=media_id,
                path=f"file://{reel_path}",
                type="video",
            )
            payload = build_schedule_request(
                assignments=[assignment],
                media_refs_by_assignment_id={assignment.id: media_ref},
            )
            publer_job_id = await client.schedule_posts(payload)
            await update_assignment(
                db,
                assignment.id,
                status=AssignmentStatus.scheduled.value,
                publer_media_id=media_id,
                publer_job_id=publer_job_id,
            )
        except Exception as exc:
            log.exception("publer_delivery_failed", extra={"assignment_id": assignment.id})
            final_status = (
                AssignmentStatus.failed.value
                if assignment.attempts + 1 >= MAX_ATTEMPTS
                else AssignmentStatus.queued.value
            )
            await update_assignment(
                db,
                assignment.id,
                status=final_status,
                error_message=str(exc)[:1000],
            )

    def _resolve_reel_path(self, assignment: ScheduleAssignmentRow) -> Path:
        artifacts_root = Path(self._settings.artifacts_root)
        candidate = artifacts_root / assignment.job_id / "reels" / f"{assignment.reel_artifact_id}.mp4"
        if not candidate.exists():
            raise FileNotFoundError(f"Reel не найден: {candidate}")
        return candidate

    async def __aenter__(self) -> "PublerWorker":
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.stop()
```

Примечание: `_resolve_reel_path` требует согласования с реальной структурой артефактов. В текущей кодовой базе рилсы лежат в `data/artifacts/<job_id>/reels/<artifact_id>.mp4` или под `artifact.path` в БД. Проверить через `find_symbol("Artifact", ...)` и либо использовать `artifact.path` напрямую.

- [ ] **Step 2: Подключить worker в `main.py` lifespan**

Serena `find_symbol("lifespan", ...)` — вставить после существующего startup:
```python
worker = PublerWorker(settings)
await worker.start()
try:
    yield
finally:
    await worker.stop()
```

- [ ] **Step 3: Build gate**

```bash
cd apps/backend && uv run ruff check src/videomaker/services/publer/worker.py src/videomaker/main.py && uv run pyright src/videomaker/services/publer/worker.py src/videomaker/main.py
```

- [ ] **Step 4: Commit**

```bash
git add apps/backend/src/videomaker/services/publer/worker.py apps/backend/src/videomaker/main.py
git commit -m "feat(publer): delivery worker — upload + schedule + retry"
git push origin HEAD
```

---

### Task 9: Frontend — API client + типы

**Files:**
- Create: `apps/frontend/src/lib/api/projects.ts`
- Create: `apps/frontend/src/lib/api/scheduler.ts`

- [ ] **Step 1: `lib/api/projects.ts`**

TypeScript типы (`Project`, `ProjectCreate`, `ProjectUpdate`) + функции `listProjects()`, `createProject()`, `updateProject()`, `deleteProject()`, `assignJobToProject(jobId, projectId | null)`. Все через `fetch(BACKEND_URL + '/api/v1/projects', ...)`.

- [ ] **Step 2: `lib/api/scheduler.ts`**

Типы (`PublerAccount`, `AccountProfile`, `CaptionPreset`, `ScheduleCampaign`, `ScheduleAssignment`) + функции:
- `getConnectionStatus()`, `listAccounts()`
- `listProfiles()`, `upsertProfile(payload)`, `deleteProfile(id)`
- `listPresets(accountId?)`, `createPreset(payload)`, `updatePreset(id, payload)`, `deletePreset(id)`
- `listLikedReels({projectId?, jobId?, limit?})`
- `listCampaigns()`, `createCampaign(payload)`, `approveCampaign(id)`, `deleteCampaign(id)`
- `listAssignments(campaignId)`, `updateAssignment(id, payload)`, `cancelAssignment(id)`
- `manualPublishOne(payload)`

Внутри все типы строго соответствуют backend Pydantic-моделям.

- [ ] **Step 3: TSC gate**

```bash
cd apps/frontend && npx tsc --noEmit -p tsconfig.json
```

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/src/lib/api/
git commit -m "feat(scheduler-ui): API client + TypeScript types"
git push origin HEAD
```

---

### Task 10: Frontend — Projects page + навигация

**Files:**
- Create: `apps/frontend/src/app/projects/page.tsx`
- Create: `apps/frontend/src/components/projects/ProjectsList.tsx`
- Create: `apps/frontend/src/components/projects/ProjectFormModal.tsx`
- Modify: `apps/frontend/src/components/nav/*` (добавить пункты «Проекты» и «Шедулер»)

- [ ] **Step 1: `app/projects/page.tsx`**

SSR с server-side `listProjects()`, render `<ProjectsList>`. Клиентские действия `add/edit/delete` через `use client` дочерний компонент.

- [ ] **Step 2: `ProjectsList.tsx`** — grid карточек, каждая с `name`, `description`, `color` (как левый border-4), счётчик джобов, кнопки «Редактировать», «Удалить».

- [ ] **Step 3: `ProjectFormModal.tsx`** — форма с полями name/description/color (input type=color).

- [ ] **Step 4: Добавить NavItem «Проекты» и «Шедулер» в header**

Найти существующий nav компонент (`apps/frontend/src/components/nav/*`), добавить два пункта с иконками (lucide-react `FolderOpen` и `CalendarClock`).

- [ ] **Step 5: TSC gate**

```bash
cd apps/frontend && npx tsc --noEmit -p tsconfig.json
```

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/app/projects apps/frontend/src/components/projects apps/frontend/src/components/nav
git commit -m "feat(scheduler-ui): projects page + navigation entries"
git push origin HEAD
```

---

### Task 11: Frontend — AccountProfiles + CaptionPresets pages

**Files:**
- Create: `apps/frontend/src/app/scheduler/accounts/page.tsx`
- Create: `apps/frontend/src/app/scheduler/presets/page.tsx`
- Create: `apps/frontend/src/components/scheduler/AccountProfileEditor.tsx`
- Create: `apps/frontend/src/components/scheduler/CaptionPresetEditor.tsx`

- [ ] **Step 1: `accounts/page.tsx`**

Один раз при mount тянет `listAccounts()` (живые Publer-аккаунты) + `listProfiles()` → merge: для каждого Publer-аккаунта показать форму редактирования профиля (создастся/обновится через upsert). Поля профиля: language (select ru/en/vi/...), audience (textarea), tone (textarea), default_hashtags (tag-input), banned_words (tag-input), cta_style (textarea), max_caption_length (number).

- [ ] **Step 2: `presets/page.tsx`**

Список `CaptionPreset` сгруппированный по `account_id` (включая «Глобальные» где account_id=null). Для каждой строки: name + position badge (prepend/append) + content preview + toggle active + edit/delete. Кнопка «Новый пресет» — форма name/position/content/account_id (select из профилей + «Глобальный»).

- [ ] **Step 3: UX детали**

- Пресеты показывают пример итогового текста: `[prepend content]\n\n<сгенерированный caption>\n\n[append content]`.
- В форме position — radio prepend/append. Позиция задаёт ТОЛЬКО место вставки, не порядок между несколькими prepend'ами (все prepend'ы клеятся сверху в порядке создания).

- [ ] **Step 4: TSC gate**

```bash
cd apps/frontend && npx tsc --noEmit -p tsconfig.json
```

- [ ] **Step 5: Commit**

```bash
git add apps/frontend/src/app/scheduler/accounts apps/frontend/src/app/scheduler/presets apps/frontend/src/components/scheduler/AccountProfileEditor.tsx apps/frontend/src/components/scheduler/CaptionPresetEditor.tsx
git commit -m "feat(scheduler-ui): account profiles + caption presets pages"
git push origin HEAD
```

---

### Task 12: Frontend — Campaign wizard + Scheduler dashboard

**Files:**
- Create: `apps/frontend/src/app/scheduler/page.tsx` — dashboard (campaigns + timeline)
- Create: `apps/frontend/src/app/scheduler/new/page.tsx` — wizard
- Create: `apps/frontend/src/components/scheduler/ReelPicker.tsx`
- Create: `apps/frontend/src/components/scheduler/AccountsPicker.tsx`
- Create: `apps/frontend/src/components/scheduler/ScheduleTimeline.tsx`
- Create: `apps/frontend/src/components/scheduler/CaptionGrid.tsx`

- [ ] **Step 1: `scheduler/page.tsx`** — список campaigns (name, status, dates, accounts, reels_count, progress), + separate секция «Queue» (pending assignments). Кнопка «Новая кампания» → `/scheduler/new`.

- [ ] **Step 2: Wizard step 1 — Source**

`<ReelPicker>`:
- Фильтр по project (select из списка проектов)
- Фильтр по job (select)
- Таблица лайкнутых рилсов (`listLikedReels`) с чекбоксом, превью обложки (`cover_path`), hook, duration, composite_score.
- Bulk-действия «Выбрать все», «По проекту».

- [ ] **Step 3: Wizard step 2 — Destinations**

`<AccountsPicker>`:
- Список Publer-аккаунтов с иконками network + display_name.
- Чекбокс-мультивыбор.
- Под каждым аккаунтом — превью активного пресета profile (language, tone).

- [ ] **Step 4: Wizard step 3 — Schedule**

`<ScheduleTimeline>`:
- Input `time` (default 19:00)
- Multi-select дат (кастомный календарь с toggle на клик даты; tz=Asia/Ho_Chi_Minh фиксирован, показывается в UI как «+07»)
- Preview: «N рилсов × M аккаунтов = K публикаций, распределяются по L датам в 19:00 +07».

- [ ] **Step 5: Review step → `CaptionGrid`**

После submit wizard'а — показать результат: сетка рилс × аккаунт. В каждой ячейке — `title` (только для YT) + `caption` + `hashtags`. Inline-editable. Кнопка «Применить» → `approveCampaign` → status=queued → worker подхватит.

- [ ] **Step 6: Manual mode — кнопка на job detail**

В существующем `apps/frontend/src/app/jobs/[id]/page.tsx` в каждой карточке лайкнутого рилса — кнопка «Опубликовать». Popover с выбором 1 аккаунта + 1 дата/время → `manualPublishOne` → toast успеха + link на будущий assignment.

- [ ] **Step 7: TSC gate**

```bash
cd apps/frontend && npx tsc --noEmit -p tsconfig.json
```

- [ ] **Step 8: Next build gate**

```bash
cd apps/frontend && pnpm build
```
Expected: успешная production-сборка.

- [ ] **Step 9: Commit**

```bash
git add apps/frontend/src/app/scheduler apps/frontend/src/components/scheduler apps/frontend/src/app/jobs/
git commit -m "feat(scheduler-ui): wizard + dashboard + manual publish + caption grid"
git push origin HEAD
```

---

### Task 13: End-to-end smoke (без реальной публикации)

**Files:** нет новых, только проверка.

- [ ] **Step 1: Backend + frontend запущены с валидным API key**

```bash
# Terminal 1
cd apps/backend && PUBLER_API_KEY='<redacted — см. Publer Settings → API Keys>' ./run.sh

# Terminal 2
cd apps/frontend && pnpm dev
```

- [ ] **Step 2: UI — создать проект**

`/projects` → «Новый проект» → name="Test", color=#6366f1. Expected: появляется карточка.

- [ ] **Step 3: UI — привязать существующий джоб к проекту**

`/jobs/{id}` → dropdown «Проект» → выбрать Test. Expected: в `/projects/1` этот джоб виден.

- [ ] **Step 4: UI — заполнить профили**

`/scheduler/accounts` → для каждого из 3 Publer-аккаунтов заполнить language/tone/audience. Сохранить. Expected: refresh страницы показывает сохранённые значения.

- [ ] **Step 5: UI — создать пресет**

`/scheduler/presets` → «Новый» → name="Подпись", position=append, content="— Никита Малов, ИИ Первопроходец", account_id=глобальный. Expected: в списке отображается.

- [ ] **Step 6: UI — создать кампанию draft**

`/scheduler/new` → выбрать 2 лайкнутых рилса → 3 аккаунта → time=19:00, dates=[завтра, послезавтра] → next → CaptionGrid показывает 2×3=6 ячеек с сгенерированным title (для YT) / caption + примененным пресетом в конце. **Не нажимать «Применить»** — смотрим только draft.

- [ ] **Step 7: Verify**

DB: `select * from schedule_assignments where status='draft'` → 6 строк с правильными scheduled_at_utc (должно быть `UTC+7 -> UTC`: 19:00 +07 = 12:00 UTC). Правильные публер id аккаунтов.

- [ ] **Step 8: Ручной публикующий smoke (опционально, с реальной публикацией в Publer)**

**⚠️ Публикует реально. Делать только если user готов к тестовому посту.**
`/jobs/{id}` → «Опубликовать» на одном лайкнутом рилсе → выбрать 1 аккаунт (например IG `Malov Nik`) → scheduled_at = через 10 минут. Через 30 секунд worker должен подхватить, залить файл, создать запрос Publer. Проверить `/scheduler` что assignment перешёл в status=scheduled с publer_job_id. Открыть Publer web → увидеть запланированный пост.

- [ ] **Step 9: Если всё ok — cleanup test данных**

Отменить assignment через UI или прямо в Publer.

- [ ] **Step 10: Финальный commit (если были фиксы)**

---

## Глобальные архитектурные заметки

**Timezone:** Backend хранит `scheduled_at_utc` в UTC (SQLAlchemy `DateTime(timezone=True)`). Frontend всегда показывает в `Asia/Ho_Chi_Minh` через `Intl.DateTimeFormat(..., {timeZone: 'Asia/Ho_Chi_Minh'})`.

**Idempotency:** Assignment имеет уникальный индекс (`campaign_id`, `reel_artifact_id`, `publer_account_id`) — если user дважды создаёт одну и ту же кампанию, повторные ассайменты блокируются. На Publer стороне используем label `campaign-{id}` для идентификации.

**Refresh-cycle:** При изменении профиля аккаунта (language/tone) уже созданные `draft` ассаймменты НЕ перегенерятся автоматически. Кнопка «Перегенерить caption» в `CaptionGrid` — явная.

**Cover thumbnail:** `PublerMediaRef.thumbnails[]` заполняется из `reel_plan.cover_path` (vision cover_selector). Если `cover_path` пуст — Publer сам сгенерит дефолтный.

**Безопасность ключа:** `PUBLER_API_KEY` только в `.env` backend'а. В frontend НЕ передаётся — все Publer-вызовы идут через backend-прокси.

**Rate limit discipline:** В одном bulk POST отправляем не более 25 постов (с запасом к 100 req/2min). Если в кампании >25 ассайнментов — worker разбивает на батчи с sleep 5 сек между.

---

## Self-review checklist

- [x] Спец покрывает: удаление legacy, DB model, migrations, HTTP client, caption gen, preset applier, scheduler service, stores, REST, worker, frontend.
- [x] Per-account caption через отдельный `PublerPost` на (reel, account).
- [x] Preset prepend/append реализован через `CaptionPresetRow.position` + `apply_presets`.
- [x] YT: title + description, IG: только description — разные `PublerNetwork` DTO.
- [x] Timezone `Asia/Ho_Chi_Minh` захардкожен в settings + campaign default.
- [x] Vision cover используется (`reel_plan.cover_path` → `thumbnails`).
- [x] Ручной режим (`manualPublishOne`) + автоматический-пакетный (`Campaign`) + UI кнопка на job detail.
- [x] Build gates после каждой задачи (ruff + pyright + tsc).
- [x] No tests, no mocks, no TODO/FIXME.

## Execution Handoff

План сохранён в `docs/plans/2026-04-23-publer-scheduler.md`. Два режима:

1. **Ralph Loop Local (recommended по feedback-памяти user'а)** — один iterator проходит задачи последовательно, каждая task = 1+ коммит, completion promise = «все 13 задач закрыты, E2E smoke прошёл».
2. **Subagent-Driven** — fresh implementer + spec reviewer + code-quality reviewer на каждую задачу.

По умолчанию — **Ralph Loop** согласно твоему паттерну на videomaker. Подтверди или переключи на subagent.
