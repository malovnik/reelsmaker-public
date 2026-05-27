"""Retry policy для LLM вызовов (tenacity-based).

Retryable: network/timeout/5xx/408/429. Non-retryable: программные
ошибки (TypeError/ValueError/KeyError/AttributeError), ``LLMError``,
4xx (кроме 408/429). Параметры (max_attempts, min/max_wait) берутся
из ``core.config.Settings.llm_retry_*``.
"""

from __future__ import annotations

from typing import Any

from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from videomaker.core.config import get_settings
from videomaker.services.llm_clients.base import LLMError


def _is_retryable(exc: BaseException) -> bool:
    """Ретраим только transient ошибки: network/timeout/5xx/408/429.

    4xx (кроме 408/429), LLMError и programming errors — сразу в caller.
    """
    if isinstance(exc, LLMError):
        return False
    if isinstance(exc, (TypeError, ValueError, KeyError, AttributeError)):
        return False
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status in (408, 429) or status >= 500
    return True


async def _retry(func: Any, *, provider: str) -> Any:
    cfg = get_settings()
    try:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(cfg.llm_retry_max_attempts),
            wait=wait_exponential(
                multiplier=1,
                min=cfg.llm_retry_min_wait_sec,
                max=cfg.llm_retry_max_wait_sec,
            ),
            retry=retry_if_exception(_is_retryable),
            reraise=True,
        ):
            with attempt:
                return await func()
    except LLMError:
        raise
    except Exception as exc:
        raise LLMError(f"{provider} request failed: {exc}") from exc
    raise LLMError(f"{provider} retry logic exhausted without result")
