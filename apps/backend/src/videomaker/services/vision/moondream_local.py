"""MoondreamLocalClient — реализация VisionClient через llama-cpp-python.

Инференс Moondream 2 GGUF через официальный `MoondreamChatHandler` из
llama-cpp-python 0.3+. Используется bundled multimodal projector (mmproj) + text
model Q4_K_M. На Apple Silicon включается Metal backend автоматически через
prebuilt wheel, с `n_gpu_layers=-1` (все слои на GPU).

Thread-safety: llama.cpp instance single-threaded по GPU, поэтому все inference
вызовы сериализованы через `asyncio.Lock`. Концурентность обеспечивается на уровне
верхнего `vision/rate_limiter.py` Semaphore (default max_concurrent=2 — реальный
параллелизм ограничен GPU, но 2 позволяют перекрыть latency IO/инференс).

Паттерн lazy-load: Llama instance грузится только при первом inference вызове.
Это нужно чтобы health() мог отвечать быстро (без грузки модели в RAM), а warm-up
происходил явно через первый `.query()` или через `close()`.

Парсинг yes/no: Moondream 2 иногда отвечает "yes.", "Yes, there is a...", "No,
the image shows..." — первое слово после strip+lower = answer. Всё остальное
классифицируется как "unknown".
"""

from __future__ import annotations

import asyncio
import base64
import time
from pathlib import Path
from typing import Any, Literal

from videomaker.core.config import Settings
from videomaker.core.logging import get_logger
from videomaker.services.vision.model_manager import (
    VisionModelManager,
    VisionModelPaths,
)
from videomaker.services.vision.types import (
    VisionCaptionResult,
    VisionDetection,
    VisionDetectResult,
    VisionHealthStatus,
    VisionQueryResult,
)

log = get_logger(__name__)


_CAPTION_PROMPTS = {
    "short": "Describe this image in one short phrase.",
    "normal": "Describe this image briefly.",
    "long": "Describe this image in detail.",
}

# 9 регионов для эвристического маппинга position→bbox. Ключи совпадают с тем,
# что мы спрашиваем у Moondream через VQA ("Where is the {label}? top-left,
# top-center, top-right, ..."). Значения — normalized XYWH [0,1].
_POSITION_REGIONS: dict[str, tuple[float, float, float, float]] = {
    "top-left": (0.0, 0.0, 0.40, 0.40),
    "top-center": (0.30, 0.0, 0.40, 0.40),
    "top-right": (0.60, 0.0, 0.40, 0.40),
    "center-left": (0.0, 0.30, 0.40, 0.40),
    "center": (0.30, 0.30, 0.40, 0.40),
    "center-right": (0.60, 0.30, 0.40, 0.40),
    "bottom-left": (0.0, 0.60, 0.40, 0.40),
    "bottom-center": (0.30, 0.60, 0.40, 0.40),
    "bottom-right": (0.60, 0.60, 0.40, 0.40),
}


class MoondreamLocalClient:
    """VisionClient через llama-cpp-python + Moondream 2 GGUF.

    Usage:
        mgr = VisionModelManager(cfg)
        client = MoondreamLocalClient(cfg, mgr)
        await client.query(Path("frame.jpg"), "Is face visible?")
        await client.close()

    Клиент совместим с VisionClient Protocol (duck-typed).
    """

    def __init__(self, cfg: Settings, model_manager: VisionModelManager) -> None:
        self._cfg = cfg
        self._manager = model_manager
        self._llm: Any = None  # llama_cpp.Llama — Any чтобы не падать без llama-cpp
        self._chat_handler: Any = None
        self._model_paths: VisionModelPaths | None = None
        self._load_lock = asyncio.Lock()
        self._inference_lock = asyncio.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._llm is not None

    async def _ensure_loaded(self) -> None:
        """Lazy-load llama.cpp instance. Idempotent через asyncio.Lock."""
        if self._llm is not None:
            return
        async with self._load_lock:
            if self._llm is not None:
                return
            paths = await self._manager.ensure_model_available()
            self._model_paths = paths
            t0 = time.perf_counter()
            self._llm, self._chat_handler = await asyncio.to_thread(
                self._load_llama_sync,
                paths,
                self._cfg.vision_n_gpu_layers,
                self._cfg.vision_n_ctx,
            )
            log.info(
                "vision_model_loaded",
                text_model=paths.text_model_path.name,
                mmproj=paths.mmproj_path.name,
                n_gpu_layers=self._cfg.vision_n_gpu_layers,
                n_ctx=self._cfg.vision_n_ctx,
                load_ms=round((time.perf_counter() - t0) * 1000, 1),
            )

    @staticmethod
    def _load_llama_sync(
        paths: VisionModelPaths, n_gpu_layers: int, n_ctx: int
    ) -> tuple[Any, Any]:
        """Синхронная загрузка в thread-pool. Импорт llama_cpp внутри — lazy."""
        from llama_cpp import Llama
        from llama_cpp.llama_chat_format import MoondreamChatHandler

        chat_handler = MoondreamChatHandler(clip_model_path=str(paths.mmproj_path))
        llm = Llama(
            model_path=str(paths.text_model_path),
            chat_handler=chat_handler,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=False,
            logits_all=False,
        )
        return llm, chat_handler

    @staticmethod
    def _image_to_data_uri(image_path: Path) -> str:
        """Читает файл и формирует `data:image/{ext};base64,...` URI."""
        suffix = image_path.suffix.lower().lstrip(".")
        mime = {
            "jpg": "jpeg",
            "jpeg": "jpeg",
            "png": "png",
            "webp": "webp",
        }.get(suffix, "jpeg")
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:image/{mime};base64,{encoded}"

    async def _chat_with_image(
        self, image_path: Path, prompt: str, *, max_tokens: int, temperature: float
    ) -> tuple[str, float]:
        """Ядро инференса. Возвращает (text, latency_ms)."""
        await self._ensure_loaded()
        data_uri = await asyncio.to_thread(self._image_to_data_uri, image_path)
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        async with self._inference_lock:
            t0 = time.perf_counter()
            response = await asyncio.to_thread(
                self._run_chat_sync, messages, max_tokens, temperature
            )
            latency_ms = (time.perf_counter() - t0) * 1000

        text = self._extract_chat_text(response)
        return text, latency_ms

    def _run_chat_sync(
        self, messages: list[dict[str, Any]], max_tokens: int, temperature: float
    ) -> dict[str, Any]:
        """Синхронный chat в to_thread."""
        assert self._llm is not None
        result: dict[str, Any] = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return result

    @staticmethod
    def _extract_chat_text(response: dict[str, Any]) -> str:
        try:
            choices = response.get("choices") or []
            if not choices:
                return ""
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            return ""
        except (AttributeError, KeyError, TypeError):
            return ""

    @staticmethod
    def _parse_yes_no(text: str) -> tuple[Literal["yes", "no", "unknown"], float]:
        """Парсит yes/no. Возвращает (answer, confidence).

        Строгие правила:
          * первое слово == "yes" → (yes, 0.9)
          * первое слово == "no" → (no, 0.9)
          * содержит "yes" но не первое → (yes, 0.6)
          * содержит "no" но не первое → (no, 0.6)
          * иначе → (unknown, 0.0)
        """
        stripped = text.strip().lower()
        if not stripped:
            return ("unknown", 0.0)
        first_word = stripped.split(None, 1)[0].strip(".,!?;:")
        if first_word == "yes":
            return ("yes", 0.9)
        if first_word == "no":
            return ("no", 0.9)
        if "yes" in stripped and "no" not in stripped:
            return ("yes", 0.6)
        if "no" in stripped and "yes" not in stripped:
            return ("no", 0.6)
        return ("unknown", 0.0)

    async def query(
        self, image_path: Path, question: str, *, max_tokens: int = 32
    ) -> VisionQueryResult:
        """Yes/no VQA. Prompt оборачивается в инструкцию отвечать yes/no."""
        prompt = f"Answer with only 'yes' or 'no'. {question}"
        text, latency_ms = await self._chat_with_image(
            image_path, prompt, max_tokens=max_tokens, temperature=0.0
        )
        answer, confidence = self._parse_yes_no(text)
        return VisionQueryResult(
            answer=answer,
            raw_response=text,
            confidence=confidence,
            latency_ms=latency_ms,
        )

    async def caption(
        self,
        image_path: Path,
        *,
        length: Literal["short", "normal", "long"] = "short",
    ) -> VisionCaptionResult:
        """Captioning. length→prompt + max_tokens."""
        prompt = _CAPTION_PROMPTS[length]
        max_tokens = {"short": 48, "normal": 128, "long": 512}[length]
        text, latency_ms = await self._chat_with_image(
            image_path, prompt, max_tokens=max_tokens, temperature=0.2
        )
        return VisionCaptionResult(
            caption=text, length=length, latency_ms=latency_ms
        )

    async def detect(
        self, image_path: Path, label: str, *, max_detections: int = 5
    ) -> VisionDetectResult:
        """Эвристическая детекция через VQA+position.

        Moondream 2 GGUF не имеет нативного detect (в отличие от MD3 Cloud).
        Используем 2-х этапный VQA: сначала есть ли объект, потом где он.
        Возвращает максимум 1 bbox (не поддерживает multiple instances).
        max_detections параметр — для совместимости API, игнорируется.
        """
        _ = max_detections  # API compatibility — single-object VQA heuristic
        presence_prompt = f"Is there a {label} visible in this image?"
        presence_text, lat1 = await self._chat_with_image(
            image_path, f"Answer with only 'yes' or 'no'. {presence_prompt}",
            max_tokens=16,
            temperature=0.0,
        )
        answer, conf = self._parse_yes_no(presence_text)
        if answer != "yes":
            return VisionDetectResult(detections=[], latency_ms=lat1)

        position_prompt = (
            f"Where is the {label} in the image? Reply with only one of: "
            "top-left, top-center, top-right, center-left, center, center-right, "
            "bottom-left, bottom-center, bottom-right."
        )
        position_text, lat2 = await self._chat_with_image(
            image_path, position_prompt, max_tokens=16, temperature=0.0
        )
        region_key = self._match_position(position_text)
        if region_key is None:
            return VisionDetectResult(detections=[], latency_ms=lat1 + lat2)

        bbox = _POSITION_REGIONS[region_key]
        detection = VisionDetection(
            label=label,
            bbox_xywh_norm=bbox,
            confidence=conf * 0.7,
        )
        return VisionDetectResult(detections=[detection], latency_ms=lat1 + lat2)

    @staticmethod
    def _match_position(text: str) -> str | None:
        lower = text.strip().lower()
        for key in _POSITION_REGIONS:
            if key in lower:
                return key
        return None

    async def health(self) -> VisionHealthStatus:
        """Lightweight health — не грузит модель. Проверяет доступность файлов."""
        try:
            import llama_cpp  # noqa: F401 — availability check
        except ImportError as exc:
            return VisionHealthStatus(
                available=False,
                model_loaded=False,
                backend="unavailable",
                error=f"llama-cpp-python not importable: {exc}",
            )

        backend: Literal["metal", "cpu", "unavailable"] = (
            "metal" if self._cfg.vision_n_gpu_layers != 0 else "cpu"
        )

        model_path_str: str | None = None
        if self._model_paths is not None:
            model_path_str = str(self._model_paths.text_model_path)
        elif self._manager.is_cached():
            model_path_str = str(self._manager.expected_text_model_path())

        return VisionHealthStatus(
            available=True,
            model_loaded=self._llm is not None,
            backend=backend,
            latency_ms=0.0,
            model_path=model_path_str,
            error=None,
        )

    async def close(self) -> None:
        """Освобождает llama.cpp ресурсы. Следующий query() заново загрузит модель."""
        if self._llm is None:
            return
        async with self._load_lock:
            llm = self._llm
            self._llm = None
            self._chat_handler = None
            try:
                close_fn = getattr(llm, "close", None)
                if callable(close_fn):
                    await asyncio.to_thread(close_fn)
            except Exception as exc:
                log.warning("vision_model_close_error", error=str(exc))
            log.info("vision_model_closed")


class MoondreamLocalFactory:
    """Provider-фабрика для локальной Moondream 2 GGUF.

    Регистрируется в `VISION_REGISTRY` из `services/vision/__init__.py`
    под именем `"moondream_local"`. Каждый вызов `build(cfg)` создаёт
    свежий `MoondreamLocalClient` с новым `VisionModelManager` — singleton-
    семантика живёт в `build_vision_client`, не здесь (разделение concerns).
    """

    name: str = "moondream_local"

    def build(self, cfg: Settings) -> MoondreamLocalClient:
        manager = VisionModelManager(cfg)
        return MoondreamLocalClient(cfg, manager)
