"""Claude (Anthropic) client с prompt caching по cache_control=ephemeral.

Паттерн кеширования скопирован с
``universal-rag/packages/backend/app/services/card_creator.py:222-261``.
Наследуется от ``_BaseLLMClient`` (Phase 6.2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from videomaker.services.llm_clients.base import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    LLMError,
    LLMResponse,
    _BaseLLMClient,
)
from videomaker.services.llm_clients.retry import _retry

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic


class ClaudeClient(_BaseLLMClient):
    provider = "anthropic"

    def _create_client(self) -> AsyncAnthropic:
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(api_key=self._api_key)

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
        # Claude: thinking_budget + response_schema + cached_content → no-op.
        # У Anthropic собственное tool_use structured output и собственное
        # prompt caching с cache_control блоками (уже реализовано ниже).
        _ = thinking_budget
        _ = response_schema
        _ = cached_content
        client = self._get_client()

        # Anthropic SDK expects TextBlockParam / MessageParam TypedDict variants.
        # Shape matches at runtime (type=text + cache_control), но TypedDict
        # инвариантность не позволяет pyright принять list[dict[str, Any]].
        # cast() вместо TypedDict-конструкторов — дешевле без потери runtime-safety.
        system_blocks = cast(
            Any,
            [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        )
        messages = cast(
            Any,
            [{"role": "user", "content": [{"type": "text", "text": user}]}],
        )

        response = await _retry(
            lambda: client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_blocks,
                messages=messages,
            ),
            provider=self.provider,
        )

        chunks = [getattr(block, "text", "") for block in response.content]
        text = "".join(c for c in chunks if c)
        if not text:
            raise LLMError("claude returned empty text content")

        usage = getattr(response, "usage", None)
        return LLMResponse(
            text=text,
            input_tokens=getattr(usage, "input_tokens", None) if usage else None,
            output_tokens=getattr(usage, "output_tokens", None) if usage else None,
            cache_read_tokens=getattr(usage, "cache_read_input_tokens", None) if usage else None,
            cache_creation_tokens=getattr(usage, "cache_creation_input_tokens", None)
            if usage
            else None,
            provider=self.provider,
            model=self.model,
        )
