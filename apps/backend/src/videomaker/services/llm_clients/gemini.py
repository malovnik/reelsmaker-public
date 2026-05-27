"""Gemini client (Google genai SDK) + Gemini-specific helpers.

Наследуется от ``_BaseLLMClient`` (Phase 6.2) — ``_get_client()`` и
lazy-init шаблон живут в базе. Здесь только ``_create_client()`` +
``complete_json()`` + cache management (``create_cache`` / ``delete_cache``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from videomaker.core.logging import get_logger
from videomaker.services.llm_clients.base import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    LLMError,
    LLMResponse,
    _BaseLLMClient,
)
from videomaker.services.llm_clients.retry import _retry

if TYPE_CHECKING:
    from google.genai import Client as GenaiClient

log = get_logger(__name__)


class GeminiClient(_BaseLLMClient):
    provider = "gemini"

    def _create_client(self) -> GenaiClient:
        from google.genai import Client

        return Client(api_key=self._api_key)

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
        from google.genai import types

        client = self._get_client()
        config_kwargs: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
            "response_mime_type": "application/json",
        }
        if cached_content is not None:
            # TIER1-#1: system_instruction уже внутри cache — не дублируем,
            # API ругнётся на коллизию. cached_content даёт -75% input cost
            # на крупных промптах v3 (deep-role, ~10-15K токенов).
            config_kwargs["cached_content"] = cached_content
        else:
            config_kwargs["system_instruction"] = system
        if response_schema is not None:
            # TIER1-#9: `response_schema` (OpenAPI-совместимый dict)
            # заставляет Gemini возвращать строго валидный JSON согласно
            # схеме — убирает большую часть parse fails от обрезанных
            # запятых, незакрытых скобок, лишних markdown-обёрток.
            config_kwargs["response_schema"] = response_schema
        if thinking_budget is not None and thinking_budget > 0:
            # TIER1-#10 + FIX: Gemini 2.5 использует `thinking_budget` (int),
            # Gemini 3.x — `thinking_level` (enum MINIMAL/LOW/MEDIUM/HIGH).
            # Выбор по имени модели. 512 tokens → MEDIUM.
            # Docs: ai.google.dev/gemini-api/docs/thinking.
            config_kwargs["thinking_config"] = _build_thinking_config(
                self.model, thinking_budget, types
            )
        config = types.GenerateContentConfig(**config_kwargs)

        response = await _retry(
            lambda: client.aio.models.generate_content(
                model=self.model,
                contents=user,
                config=config,
            ),
            provider=self.provider,
        )

        text = _gemini_text(response)
        usage = getattr(response, "usage_metadata", None)
        input_tokens = getattr(usage, "prompt_token_count", None) if usage else None
        output_tokens = getattr(usage, "candidates_token_count", None) if usage else None
        cache_read = getattr(usage, "cached_content_token_count", None) if usage else None

        return LLMResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_creation_tokens=None,
            provider=self.provider,
            model=self.model,
        )

    async def create_cache(
        self,
        *,
        system_instruction: str,
        ttl_seconds: int = 1800,
        display_name: str | None = None,
    ) -> str | None:
        """Создаёт explicit context cache с заданным system_instruction.

        Возвращает ``cache.name`` (строка вида ``cachedContents/...``) или
        ``None`` при ошибке (<1024 tokens в content, недоступность модели,
        сетевой fail). Вызывающий код обязан обработать ``None`` как
        сигнал fallback на обычный (некешированный) вызов.

        TIER1-#1: применяется для тяжёлых narrative промптов 10-15K tokens
        которые многократно используются (13 агентов × N chunks) — даёт
        -75% стоимости input-токенов на повторных вызовах.
        """

        from google.genai import types

        client = self._get_client()
        try:
            cache = await client.aio.caches.create(
                model=self.model,
                config=types.CreateCachedContentConfig(
                    system_instruction=system_instruction,
                    ttl=f"{ttl_seconds}s",
                    display_name=display_name or "videomaker-agent",
                ),
            )
        except Exception as exc:
            # Самая частая причина None — content < 1024 tokens (Gemini limit).
            # Также может упасть при отсутствии caching у модели или network.
            log.warning(
                "gemini_cache_create_failed",
                model=self.model,
                error=str(exc)[:300],
            )
            return None
        cache_name = getattr(cache, "name", None)
        if not cache_name:
            log.warning("gemini_cache_create_empty_name", model=self.model)
            return None
        log.info(
            "gemini_cache_created",
            cache=cache_name,
            model=self.model,
            ttl_seconds=ttl_seconds,
        )
        return str(cache_name)

    async def delete_cache(self, cache_name: str) -> None:
        """Явное удаление cache после использования. Ошибки логируются, не бросаются."""

        client = self._get_client()
        try:
            await client.aio.caches.delete(name=cache_name)
        except Exception as exc:
            log.warning(
                "gemini_cache_delete_failed",
                cache=cache_name,
                error=str(exc)[:300],
            )
            return
        log.info("gemini_cache_deleted", cache=cache_name)


def _build_thinking_config(model: str, budget: int, types_module: Any) -> Any:
    """Строит ``ThinkingConfig`` подходящий для семейства модели.

    * **Gemini 2.5**: API поддерживает ``thinking_budget: int`` (0=disabled,
      -1=auto). Минимум 128 для 2.5-Pro; 512 оптимален для Flash.
    * **Gemini 3.x**: API использует ``thinking_level`` enum
      (MINIMAL / LOW / MEDIUM / HIGH). Budget → level mapping:
      ``<=256=LOW``, ``<=1024=MEDIUM``, ``>1024=HIGH``.

    Докстроки и enum подтверждены по
    https://ai.google.dev/gemini-api/docs/thinking.
    """

    model_lower = model.lower()
    if "3.1" in model_lower or "3-" in model_lower or "3-flash" in model_lower or "3-pro" in model_lower:
        # Gemini 3.x → thinking_level
        if budget <= 0:
            level = types_module.ThinkingLevel.MINIMAL
        elif budget <= 256:
            level = types_module.ThinkingLevel.LOW
        elif budget <= 1024:
            level = types_module.ThinkingLevel.MEDIUM
        else:
            level = types_module.ThinkingLevel.HIGH
        return types_module.ThinkingConfig(thinking_level=level)
    # Gemini 2.5 (или legacy) → thinking_budget
    return types_module.ThinkingConfig(thinking_budget=budget)


def _gemini_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text:
        return text
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if not parts:
            continue
        chunks = [getattr(p, "text", None) for p in parts]
        joined = "".join(c for c in chunks if c)
        if joined:
            return joined
    raise LLMError("gemini returned empty response")
