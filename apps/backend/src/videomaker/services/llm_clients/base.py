"""Базовые примитивы LLM клиентов.

Содержит:
- ``LLMClient`` Protocol — публичный контракт клиента
- ``LLMResponse`` — унифицированный ответ
- ``LLMError`` — общая ошибка LLM слоя
- ``_BaseLLMClient`` — abstract base с lazy-init шаблоном (``_get_client``)
- ``DEFAULT_MAX_OUTPUT_TOKENS`` — дефолтный бюджет на output

Выделено из ``services/llm_client.py`` в Phase 5.3 + 6.2. ``_BaseLLMClient``
убирает 4× дубликат lazy-init из Gemini/Claude/OpenAI/GLM клиентов.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, runtime_checkable


class LLMError(RuntimeError):
    pass


@dataclass(slots=True)
class LLMResponse:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    cache_read_tokens: int | None
    cache_creation_tokens: int | None
    provider: str
    model: str


#: Дефолтный budget на output при переходе на deep-role prompts v3.
#: Gemini 3.x: input 1M токенов, output до 65K (включая thinking). Gemini 2.5
#: Pro: input 2M. Дефолт 32000 — запас под story_doctor (3-act arc 7-12
#: сегментов), variants_generator (4 варианта), reducer (60 ranked items).
#: Стадии попроще (hook_hunter, compression) явно конфигурируют меньший
#: лимит в call-site. 65K не используем как дефолт чтобы не гонять
#: токены зря в дешёвых вызовах.
DEFAULT_MAX_OUTPUT_TOKENS = 32000


@runtime_checkable
class LLMClient(Protocol):
    provider: str
    model: str

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
    ) -> LLMResponse: ...


class _BaseLLMClient(ABC):
    """Абстрактный базовый класс для LLM клиентов.

    Реализует общий lazy-init паттерн ``_get_client()``. Убирает 4×
    дубликат из Gemini/Claude/OpenAI/GLM клиентов (Phase 6.2).

    Subclasses override:
    - ``provider: ClassVar[str]`` — идентификатор провайдера.
    - ``_env_var_name`` (optional) — имя env var для текста ошибки
      когда ``api_key`` не задан. Дефолт: ``f"{provider.upper()}_API_KEY"``.
    - ``_create_client() -> Any`` — конструктор SDK-клиента (вызывается lazy).
    - ``complete_json(...)`` — обязательный метод из ``LLMClient`` Protocol.
    """

    provider: ClassVar[str]

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise LLMError(f"{self._env_var_name()} is not set")
        self.model = model
        self._api_key = api_key
        self._client: Any | None = None

    def _env_var_name(self) -> str:
        """Имя env var для сообщения об ошибке отсутствующего ключа.

        Дефолт — по провайдеру (``GEMINI_API_KEY``, ``OPENAI_API_KEY``,
        ``ZHIPU_API_KEY``). Claude переопределяет на ``ANTHROPIC_API_KEY``
        т.к. ``provider = "anthropic"`` но исторически в Settings лежит
        ``anthropic_api_key``/``ANTHROPIC_API_KEY``.
        """

        return f"{self.provider.upper()}_API_KEY"

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._create_client()
        return self._client

    @abstractmethod
    def _create_client(self) -> Any:
        """Lazy создание SDK-клиента. Вызывается один раз при первом обращении."""
        ...
