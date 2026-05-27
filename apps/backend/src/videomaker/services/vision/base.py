"""VisionClient Protocol — контракт для всех vision-бэкендов.

Дизайн через Protocol (не ABC) — следуем паттерну `videomaker.services.llm_client.LLMClient`.
Это позволяет MoondreamLocalClient не наследоваться явно и упрощает unit-тесты
через duck-typing.

Все методы async. Реализации обязаны respect'ить asyncio.Semaphore ограничения
на concurrent inference — llama.cpp GGUF однопоточный по GPU.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

from videomaker.services.vision.types import (
    VisionCaptionResult,
    VisionDetectResult,
    VisionHealthStatus,
    VisionQueryResult,
)


@runtime_checkable
class VisionClient(Protocol):
    """Контракт vision-бэкенда: query/caption/detect/health.

    Все методы принимают `Path` на JPEG/PNG/WebP файл. Клиент сам отвечает
    за загрузку и препроцессинг (resize до ≤1568px для Moondream, нормализация).
    """

    async def query(
        self, image_path: Path, question: str, *, max_tokens: int = 32
    ) -> VisionQueryResult:
        """Yes/no VQA. `question` должен быть закрытым вопросом."""
        ...

    async def caption(
        self,
        image_path: Path,
        *,
        length: Literal["short", "normal", "long"] = "short",
    ) -> VisionCaptionResult:
        """Описание кадра. `short` — фраза, `normal` — предложение, `long` — абзац."""
        ...

    async def detect(
        self, image_path: Path, label: str, *, max_detections: int = 5
    ) -> VisionDetectResult:
        """Детекция объектов с label в кадре. Возвращает bbox в normalized coords."""
        ...

    async def health(self) -> VisionHealthStatus:
        """Lightweight ping. Не грузит модель если ещё не загружена —
        возвращает статус загрузки и backend (metal/cpu/unavailable)."""
        ...

    async def close(self) -> None:
        """Освобождает ресурсы (llama.cpp instance, Metal context)."""
        ...
