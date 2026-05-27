"""OpenAI client (GPT-5 responses API через AsyncOpenAI SDK).

Наследуется от ``_BaseLLMClient`` (Phase 6.2). Structured output через
``response_format={"type": "json_object"}``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from videomaker.services.llm_clients.base import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    LLMError,
    LLMResponse,
    _BaseLLMClient,
)
from videomaker.services.llm_clients.retry import _retry

if TYPE_CHECKING:
    from openai import AsyncOpenAI


class OpenAIClient(_BaseLLMClient):
    provider = "openai"

    def _create_client(self) -> AsyncOpenAI:
        from openai import AsyncOpenAI

        return AsyncOpenAI(api_key=self._api_key)

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
        # OpenAI: все три опции Gemini-specific → no-op. У OpenAI собственные
        # API для prompt caching и structured output (TIER 3 миграция).
        _ = thinking_budget
        _ = response_schema
        _ = cached_content
        client = self._get_client()

        response = await _retry(
            lambda: client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
                max_tokens=max_tokens,
            ),
            provider=self.provider,
        )

        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LLMError("openai returned no choices")
        message = choices[0].message
        text = getattr(message, "content", None) or ""
        if not text:
            raise LLMError("openai returned empty content")

        usage = getattr(response, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
        cached_prompt_tokens = None
        if usage is not None and hasattr(usage, "prompt_tokens_details"):
            details = usage.prompt_tokens_details
            cached_prompt_tokens = getattr(details, "cached_tokens", None)

        return LLMResponse(
            text=text,
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
            cache_read_tokens=cached_prompt_tokens,
            cache_creation_tokens=None,
            provider=self.provider,
            model=self.model,
        )
