"""Pydantic модели Publer Business API v1.

Все модели наследуются от `_PublerBase` с `extra="allow"` — Publer периодически
расширяет ответы новыми полями, и жёсткая валидация сломает клиент без пользы.
`populate_by_name=True` нужен на случай если в ответе snake_case/camelCase
смешаны (реально встречается в /workspaces vs /posts/schedule).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _PublerBase(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class PublerWorkspace(_PublerBase):
    id: str
    name: str
    role: str | None = None


class PublerAccount(_PublerBase):
    id: str
    provider: str
    type: str | None = None
    name: str | None = None
    status: str | None = None


class PublerMediaThumbnail(_PublerBase):
    id: str
    small: str
    real: str


class PublerMediaRef(_PublerBase):
    id: str
    path: str
    type: Literal["video", "photo"] = "video"
    thumbnails: list[PublerMediaThumbnail] = Field(default_factory=list)
    default_thumbnail: int = 0


class PublerReelDetails(_PublerBase):
    type: Literal["reel"] = "reel"
    feed: bool = True
    audio: str | None = None


class PublerShortDetails(_PublerBase):
    type: Literal["short"] = "short"
    privacy: Literal["public", "private", "unlisted"] = "public"


class PublerInstagramNetwork(_PublerBase):
    type: Literal["video"] = "video"
    text: str
    media: list[PublerMediaRef]
    details: PublerReelDetails = Field(default_factory=PublerReelDetails)


class PublerYoutubeNetwork(_PublerBase):
    type: Literal["video"] = "video"
    title: str
    text: str
    media: list[PublerMediaRef]
    details: PublerShortDetails = Field(default_factory=PublerShortDetails)


class PublerAccountTarget(_PublerBase):
    id: str
    scheduled_at: str | None = None
    labels: list[str] = Field(default_factory=list)


class PublerPost(_PublerBase):
    networks: dict[str, PublerInstagramNetwork | PublerYoutubeNetwork]
    accounts: list[PublerAccountTarget]


class PublerBulk(_PublerBase):
    state: Literal["scheduled", "draft", "scheduled_publish"] = "scheduled"
    posts: list[PublerPost]


class PublerScheduleRequest(_PublerBase):
    bulk: PublerBulk


class PublerJobStatus(_PublerBase):
    status: Literal["working", "complete", "failed"]
    result: dict[str, Any] | None = None
