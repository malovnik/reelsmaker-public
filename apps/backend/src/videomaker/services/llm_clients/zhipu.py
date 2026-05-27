"""Zhipu Z.AI GLM-5.1 client (OpenAI-compatible API).

Наследуется от ``_BaseLLMClient`` (Phase 6.2). Отличия: base_url опционален,
SDK синхронный (вызовы через ``asyncio.to_thread``), Coding Plan требует
rate-limiting и serialization через семафор.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from videomaker.services.llm_clients.base import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    LLMError,
    LLMResponse,
    _BaseLLMClient,
)
from videomaker.services.llm_clients.retry import _retry

if TYPE_CHECKING:
    from zhipuai import ZhipuAI


class GLMClient(_BaseLLMClient):
    """Zhipu Z.AI GLM-5.1 client (OpenAI-compatible API).

    Использует официальный `zhipuai` SDK (https://open.bigmodel.cn).

    Ограничения по сравнению с Gemini:
    * `response_schema` (OpenAPI dict) не поддерживается нативно — делаем
      fallback: добавляем в system_instruction текстовую инструкцию
      "ответь строго валидным JSON по схеме {json.dumps(schema)}" и
      передаём ``response_format={"type": "json_object"}`` (GLM v4
      гарантирует валидный JSON object на выходе).
    * `cached_content` не поддерживается — игнорируется. GLM не имеет
      explicit prompt caching на уровне API.
    * `thinking_budget > 0` маппится в ``thinking={"type": "enabled"}`` —
      GLM-5.1 имеет reasoning mode с автоматическим бюджетом.

    SDK синхронный — вызовы оборачиваются в ``asyncio.to_thread`` чтобы
    не блокировать FastAPI event loop. Retry-логика наружная через
    ``_retry()``.
    """

    provider = "zhipu"

    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        super().__init__(api_key, model)
        self._base_url = base_url

    def _create_client(self) -> ZhipuAI:
        from zhipuai import ZhipuAI

        if self._base_url:
            return ZhipuAI(api_key=self._api_key, base_url=self._base_url)
        return ZhipuAI(api_key=self._api_key)

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.3,
        max_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS,
        thinking_budget: int | None = None,
        response_schema: dict[str, Any] | None = None,
        cached_content: str | None = None,
    ) -> LLMResponse:
        import asyncio

        # GLM не поддерживает explicit prompt caching — параметр принимаем
        # ради совместимости с LLMClient Protocol, но игнорируем.
        del cached_content

        client = self._get_client()

        system_instruction = system
        if response_schema is not None:
            system_instruction = (
                f"{system}\n\n"
                f"Ответь строго валидным JSON соответствующим схеме:\n"
                f"{json.dumps(response_schema, ensure_ascii=False)}"
            )

        messages = [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": user},
        ]

        # GLM-5.1 на Coding Plan: reasoning mode съедает весь max_tokens
        # бюджет в reasoning_content (8000 tokens → 0 content). Даже при
        # max_tokens=16000/32000 JSON-ответ получается обрезанным или
        # пустым. Отключаем reasoning безусловно — GLM-5.1 и без thinking
        # выдаёт корректный JSON (проверено smoke + эмпирически).
        # `thinking_budget` из Protocol игнорируем (Gemini-specific hint).
        _ = thinking_budget
        thinking_param: dict[str, str] = {"type": "disabled"}
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "thinking": thinking_param,
        }

        from videomaker.services.rate_limiter import (
            get_zhipu_concurrency_gate,
            get_zhipu_rate_limiter,
        )

        gate = get_zhipu_concurrency_gate()
        limiter = get_zhipu_rate_limiter()

        async def _call() -> Any:
            # Сериализуем через семафор (Coding Plan concurrency=1)
            # и лимитируем частоту (Coding Plan Lite ~5 RPM).
            async with gate, limiter.acquire():
                return await asyncio.to_thread(
                    client.chat.completions.create, **payload
                )

        response = await _retry(_call, provider=self.provider)

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LLMError("zhipu returned empty choices")
        choice = choices[0]
        message = getattr(choice, "message", None)
        text = getattr(message, "content", None) if message else None
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        output_tokens = getattr(usage, "completion_tokens", None) if usage else None

        if not isinstance(text, str) or not text:
            # Частая причина — reasoning mode съел весь max_tokens budget и
            # до финального content дело не дошло (finish_reason=length +
            # reasoning_tokens == max_tokens). Даём диагностическое сообщение
            # чтобы причина была очевидна, без гадания по коду.
            finish_reason = getattr(choice, "finish_reason", None)
            reasoning_len = 0
            if message is not None:
                reasoning = getattr(message, "reasoning_content", None)
                if isinstance(reasoning, str):
                    reasoning_len = len(reasoning)
            reasoning_tokens = None
            if usage is not None:
                details = getattr(usage, "completion_tokens_details", None)
                if isinstance(details, dict):
                    reasoning_tokens = details.get("reasoning_tokens")
                elif details is not None:
                    reasoning_tokens = getattr(details, "reasoning_tokens", None)
            raise LLMError(
                "zhipu returned empty content "
                f"(finish_reason={finish_reason}, "
                f"reasoning_tokens={reasoning_tokens}, "
                f"reasoning_chars={reasoning_len}, "
                f"max_tokens={max_tokens}, "
                f"thinking={thinking_param['type']}). "
                "Если finish_reason=length — увеличь max_tokens. "
                "Reasoning mode отключён для GLM безусловно (Coding Plan "
                "reasoning ломает JSON-output)."
            )

        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=None,
            cache_creation_tokens=None,
            provider=self.provider,
            model=self.model,
        )
