"""LLM clients package — split of legacy services/llm_client.py (Phase 5.3).

Содержит:
- ``base`` — ``LLMClient`` Protocol, ``LLMResponse``, ``LLMError``,
  ``_BaseLLMClient`` с lazy-init шаблоном, ``DEFAULT_MAX_OUTPUT_TOKENS``.
- ``retry`` — tenacity wrapper ``_retry`` + ``_is_retryable``.
- ``json_parser`` — ``parse_json_response`` + repair fallbacks.
- ``tier_resolver`` — ``LLMTier`` alias + ``_resolve_tier_models`` +
  runtime_settings override.
- ``gemini`` / ``claude`` / ``openai`` / ``zhipu`` — конкретные клиенты,
  все наследуются от ``_BaseLLMClient`` (Phase 6.2).

Импорты наружу идут через ``services.llm_client`` facade — см. модуль
``services/llm_client.py`` — для 100% backward compat.
"""

from videomaker.services.llm_clients.base import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    LLMClient,
    LLMError,
    LLMResponse,
    _BaseLLMClient,
)
from videomaker.services.llm_clients.claude import ClaudeClient
from videomaker.services.llm_clients.gemini import GeminiClient
from videomaker.services.llm_clients.json_parser import parse_json_response
from videomaker.services.llm_clients.openai import OpenAIClient
from videomaker.services.llm_clients.retry import _is_retryable, _retry
from videomaker.services.llm_clients.tier_resolver import (
    LLMTier,
    _resolve_tier_models,
    _tier_profiles,
    _try_read_tier_profile,
)
from videomaker.services.llm_clients.zhipu import GLMClient

__all__ = [
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "ClaudeClient",
    "GLMClient",
    "GeminiClient",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "LLMTier",
    "OpenAIClient",
    "_BaseLLMClient",
    "_is_retryable",
    "_resolve_tier_models",
    "_retry",
    "_tier_profiles",
    "_try_read_tier_profile",
    "parse_json_response",
]
