"""Publer API connectivity probe.

Одноразовый диагностический скрипт для проверки API ключа Publer'а
до начала полноценной интеграции. Делает 3 read-only запроса:

1. GET /workspaces      — проверка ключа + сбор workspace ids
2. GET /accounts        — список подключённых соц-аккаунтов первого ws
3. GET /posts?state=scheduled&limit=5 — убеждаемся что список постов читается

Запуск:

    PUBLER_API_KEY=... uv run python scripts/publer_probe.py
    # опционально: PUBLER_WORKSPACE_ID=... чтобы зафиксировать ws_id

Выход 0 — всё зелёное, >0 — сбой на одном из шагов (детали в stderr).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import httpx

BASE_URL = "https://app.publer.com/api/v1"
TIMEOUT = 30.0


def _die(code: int, msg: str) -> None:
    print(f"\n[FAIL] {msg}", file=sys.stderr)
    sys.exit(code)


def _pretty(value: Any, limit: int = 1200) -> str:
    text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    if len(text) > limit:
        return text[:limit] + f"\n… (+{len(text) - limit} chars truncated)"
    return text


def _headers(api_key: str, workspace_id: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer-API {api_key}",
        "Content-Type": "application/json",
    }
    if workspace_id:
        headers["Publer-Workspace-Id"] = workspace_id
    return headers


def probe_workspaces(client: httpx.Client, api_key: str) -> list[dict[str, Any]]:
    print(">>> GET /workspaces")
    resp = client.get(f"{BASE_URL}/workspaces", headers=_headers(api_key))
    print(f"    status={resp.status_code}")
    if resp.status_code != 200:
        _die(2, f"/workspaces вернул {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    workspaces = data if isinstance(data, list) else data.get("workspaces") or data.get("data") or []
    if not isinstance(workspaces, list):
        _die(2, f"/workspaces — неожиданная форма: {_pretty(data)}")
    print(f"    найдено workspace(s): {len(workspaces)}")
    for ws in workspaces:
        print(f"    - id={ws.get('id')} name={ws.get('name')!r} role={ws.get('role')}")
    if not workspaces:
        _die(2, "Публер не вернул ни одного workspace — проверь тариф Business/Enterprise.")
    return workspaces


def probe_accounts(client: httpx.Client, api_key: str, ws_id: str) -> list[dict[str, Any]]:
    print(f"\n>>> GET /accounts (ws={ws_id})")
    resp = client.get(f"{BASE_URL}/accounts", headers=_headers(api_key, ws_id))
    print(f"    status={resp.status_code}")
    if resp.status_code != 200:
        _die(3, f"/accounts вернул {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    accounts = data if isinstance(data, list) else data.get("accounts") or data.get("data") or []
    if not isinstance(accounts, list):
        _die(3, f"/accounts — неожиданная форма: {_pretty(data)}")
    print(f"    найдено account(s): {len(accounts)}")

    by_provider: dict[str, int] = {}
    for acc in accounts:
        provider = str(acc.get("provider") or acc.get("network") or "?")
        by_provider[provider] = by_provider.get(provider, 0) + 1
    print(f"    по провайдерам: {by_provider}")

    for acc in accounts[:10]:
        print(
            "    - "
            f"id={acc.get('id')} "
            f"provider={acc.get('provider')} "
            f"type={acc.get('type')} "
            f"status={acc.get('status')} "
            f"name={acc.get('name') or acc.get('username')!r}"
        )
    return accounts


def probe_posts(client: httpx.Client, api_key: str, ws_id: str) -> None:
    print(f"\n>>> GET /posts?state=scheduled&limit=5 (ws={ws_id})")
    resp = client.get(
        f"{BASE_URL}/posts",
        headers=_headers(api_key, ws_id),
        params={"state": "scheduled", "limit": 5},
    )
    print(f"    status={resp.status_code}")
    if resp.status_code != 200:
        _die(4, f"/posts вернул {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    posts = data if isinstance(data, list) else data.get("posts") or data.get("data") or []
    total = data.get("total") if isinstance(data, dict) else None
    print(f"    получено постов на странице: {len(posts)}; total={total}")


def main() -> None:
    api_key = os.environ.get("PUBLER_API_KEY", "").strip()
    if not api_key:
        _die(1, "Нужен env var PUBLER_API_KEY.")

    ws_override = os.environ.get("PUBLER_WORKSPACE_ID", "").strip() or None

    with httpx.Client(timeout=TIMEOUT) as client:
        workspaces = probe_workspaces(client, api_key)
        ws_id = ws_override or str(workspaces[0]["id"])
        if ws_override:
            print(f"    (используем override PUBLER_WORKSPACE_ID={ws_override})")
        else:
            print(f"    (используем первый ws: id={ws_id})")

        probe_accounts(client, api_key, ws_id)
        probe_posts(client, api_key, ws_id)

    print("\n[OK] Publer API доступен, ключ валиден.")


if __name__ == "__main__":
    main()
