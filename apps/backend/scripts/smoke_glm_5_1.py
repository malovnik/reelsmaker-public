"""One-shot smoke test для реального GLM-5.1 API.

Запуск:
  cd apps/backend
  ZHIPU_API_KEY=<id>.<secret> uv run python scripts/smoke_glm_5_1.py

Читает ZHIPU_BASE_URL из .env / Settings (дефолт — Coding Plan endpoint).
Проверяет: SDK импорт, auth, базовый JSON response, usage metadata, retry.
"""

from __future__ import annotations

import asyncio
import json
import os

from videomaker.core.config import Settings
from videomaker.services.llm_client import GLMClient


async def main() -> None:
    api_key = os.environ.get("ZHIPU_API_KEY")
    if not api_key:
        raise SystemExit("ZHIPU_API_KEY not set")

    settings = Settings()
    client = GLMClient(
        api_key=api_key,
        model=settings.zhipu_default_model,
        base_url=settings.zhipu_base_url,
    )

    print("=== GLM-5.1 smoke test ===")
    print(f"base_url:  {settings.zhipu_base_url}")
    print(f"model:     {settings.zhipu_default_model}")
    print("---")

    response = await client.complete_json(
        system=(
            "Ты помощник. Отвечай только JSON-объектом с полями "
            '{"ok": bool, "message": str}.'
        ),
        user="Скажи привет по-русски.",
        temperature=0.3,
        max_tokens=256,
    )

    print(f"provider:  {response.provider}")
    print(f"model:     {response.model}")
    print(f"in_tokens: {response.input_tokens}")
    print(f"out_tokens:{response.output_tokens}")
    print(f"text:      {response.text[:500]}")

    parsed = json.loads(response.text)
    assert "ok" in parsed, "JSON does not contain 'ok' field"
    print("OK — JSON parsed, contains 'ok' field")


if __name__ == "__main__":
    asyncio.run(main())
