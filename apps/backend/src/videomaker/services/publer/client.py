"""HTTP-клиент Publer Business API v1.

Async httpx клиент с Bearer-API авторизацией + Publer-Workspace-Id header.
Retry policy: 3 попытки с экспоненциальным backoff (1s/3s/9s) на httpx.HTTPError
и 5xx ответы. На 429 (rate limit: 100 req/2 min) спит 125 секунд и retry без
инкремента попытки — rate-limit не должен исчерпать бюджет retry.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from videomaker.core.config import Settings
from videomaker.core.logging import get_logger
from videomaker.services.publer.schemas import (
    PublerAccount,
    PublerJobStatus,
    PublerScheduleRequest,
    PublerWorkspace,
)

log = get_logger(__name__)

_MAX_RETRIES = 3
_BACKOFF_SCHEDULE = (1.0, 3.0, 9.0)
_RATE_LIMIT_SLEEP = 125.0
_MAX_RATE_LIMIT_RETRIES = 5
_UPLOAD_TIMEOUT_SEC = 600.0  # 10 минут — хватит для 500 MB @ 7 Mbps


class PublerClientError(RuntimeError):
    pass


class PublerClient:
    def __init__(
        self, settings: Settings, client: httpx.AsyncClient | None = None
    ) -> None:
        if not settings.publer_api_key:
            raise PublerClientError("PUBLER_API_KEY не задан")
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=settings.publer_request_timeout_sec
        )

    async def __aenter__(self) -> PublerClient:
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        await self.close()

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

    async def _request(
        self,
        method: str,
        path: str,
        *,
        workspace: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        url = f"{self._settings.publer_base_url}{path}"
        last_exc: Exception | None = None
        rate_limit_hits = 0
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.request(
                    method,
                    url,
                    headers=self._headers(workspace=workspace),
                    **kwargs,
                )
                if resp.status_code == 429:
                    rate_limit_hits += 1
                    if rate_limit_hits > _MAX_RATE_LIMIT_RETRIES:
                        raise PublerClientError(
                            f"Publer rate-limit exceeded {rate_limit_hits}x on {path}"
                        )
                    log.warning(
                        "publer_rate_limited",
                        path=path,
                        sleep=_RATE_LIMIT_SLEEP,
                        hit=rate_limit_hits,
                    )
                    await asyncio.sleep(_RATE_LIMIT_SLEEP)
                    continue
                if resp.status_code >= 500:
                    raise PublerClientError(
                        f"Publer 5xx on {path}: {resp.status_code}"
                    )
                return resp
            except (httpx.HTTPError, PublerClientError) as exc:
                last_exc = exc
                if attempt + 1 >= _MAX_RETRIES:
                    break
                await asyncio.sleep(_BACKOFF_SCHEDULE[attempt])
        raise PublerClientError(
            f"Publer {method} {path} провалился: {last_exc}"
        )

    async def list_workspaces(self) -> list[PublerWorkspace]:
        resp = await self._request("GET", "/workspaces", workspace=False)
        resp.raise_for_status()
        data = resp.json()
        items = (
            data
            if isinstance(data, list)
            else data.get("workspaces") or data.get("data") or []
        )
        return [PublerWorkspace.model_validate(item) for item in items]

    async def list_accounts(self) -> list[PublerAccount]:
        resp = await self._request("GET", "/accounts")
        resp.raise_for_status()
        data = resp.json()
        items = (
            data
            if isinstance(data, list)
            else data.get("accounts") or data.get("data") or []
        )
        return [PublerAccount.model_validate(item) for item in items]

    async def upload_media_file(
        self, *, file_path: str, filename: str, content_type: str
    ) -> str:
        """Multipart upload файла, возвращает Publer media id.

        Через ту же retry-логику что и `_request` (3 попытки + экспоненциальный
        backoff на 5xx, sleep 125s на 429). Timeout переопределён до
        `_UPLOAD_TIMEOUT_SEC` — обычный 30s слишком короткий для 100–500 MB видео.
        """
        url = f"{self._settings.publer_base_url}/media"
        headers = {k: v for k, v in self._headers().items() if k != "Content-Type"}

        last_exc: Exception | None = None
        rate_limit_hits = 0
        for attempt in range(_MAX_RETRIES):
            try:
                with open(file_path, "rb") as fh:
                    files = {"file": (filename, fh, content_type)}
                    resp = await self._client.post(
                        url,
                        headers=headers,
                        files=files,
                        timeout=_UPLOAD_TIMEOUT_SEC,
                    )
                if resp.status_code == 429:
                    rate_limit_hits += 1
                    if rate_limit_hits > _MAX_RATE_LIMIT_RETRIES:
                        raise PublerClientError(
                            f"Publer rate-limit exceeded {rate_limit_hits}x on /media"
                        )
                    log.warning(
                        "publer_rate_limited",
                        path="/media",
                        sleep=_RATE_LIMIT_SLEEP,
                        hit=rate_limit_hits,
                    )
                    await asyncio.sleep(_RATE_LIMIT_SLEEP)
                    continue
                if resp.status_code >= 500:
                    raise PublerClientError(
                        f"Publer 5xx on /media: {resp.status_code}"
                    )
                resp.raise_for_status()
                data = resp.json()
                media_id = data.get("id") or (data.get("data") or {}).get("id")
                if not media_id:
                    raise PublerClientError(
                        f"upload_media_file: id отсутствует в ответе {data}"
                    )
                log.info(
                    "publer_media_uploaded",
                    filename=filename,
                    media_id=media_id,
                )
                return str(media_id)
            except (httpx.HTTPError, PublerClientError) as exc:
                last_exc = exc
                if attempt + 1 >= _MAX_RETRIES:
                    break
                await asyncio.sleep(_BACKOFF_SCHEDULE[attempt])
        raise PublerClientError(f"Publer upload /media провалился: {last_exc}")

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
            raise PublerClientError(
                f"schedule_posts: job_id отсутствует {data}"
            )
        return str(job_id)

    async def delete_posts(self, post_ids: list[str]) -> list[str]:
        """Удаляет посты из Publer-workspace (DELETE /posts?post_ids[]=...).

        Принимает любые состояния, кроме уже опубликованных — для них Publer
        вернёт ошибку (role/state restriction). Возвращает список реально
        удалённых id (`deleted_ids` из ответа). Пустой `post_ids` → no-op.
        """
        if not post_ids:
            return []
        resp = await self._request(
            "DELETE",
            "/posts",
            params=[("post_ids[]", pid) for pid in post_ids],
        )
        resp.raise_for_status()
        data = resp.json()
        deleted = data.get("deleted_ids")
        if deleted is None and isinstance(data.get("data"), dict):
            deleted = data["data"].get("deleted_ids")
        return [str(x) for x in (deleted or [])]

    async def get_job_status(self, job_id: str) -> PublerJobStatus:
        resp = await self._request("GET", f"/job_status/{job_id}")
        resp.raise_for_status()
        data = resp.json()
        payload = data.get("data") or data
        return PublerJobStatus.model_validate(payload)
