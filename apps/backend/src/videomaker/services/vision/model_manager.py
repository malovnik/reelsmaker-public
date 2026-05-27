"""VisionModelManager — скачивание и кэш Moondream 2 GGUF через huggingface_hub.

Стратегия:
* Первый вызов `ensure_model_available()` скачивает два файла (text model Q4_K_M
  ~1.7 GB + mmproj-f16 ~850 MB) в `data/models/moondream2/`. Общий размер ~2.5 GB.
* Повторные вызовы no-op — huggingface_hub сам проверяет целостность через ETag.
* Интеграция с llama-cpp-python: модели разделены (text model и vision projector)
  — MoondreamChatHandler принимает оба пути.

Блокировки: скачивание идёт в thread-pool через `asyncio.to_thread`, чтобы не
блокировать event loop. Повторный параллельный вызов ensure_model_available()
кооперируется через asyncio.Lock.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import hf_hub_download
from huggingface_hub.errors import HfHubHTTPError

from videomaker.core.config import Settings
from videomaker.core.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class VisionModelPaths:
    """Результат ensure_model_available — абсолютные пути до GGUF файлов."""

    text_model_path: Path
    mmproj_path: Path


class VisionModelManager:
    """Управляет скачиванием и валидацией Moondream 2 GGUF файлов.

    Thread-safe в рамках одного процесса через asyncio.Lock. Для мульти-процессной
    синхронизации полагаемся на атомарность huggingface_hub (он использует file-lock
    через `.locks/` директорию).
    """

    def __init__(self, cfg: Settings) -> None:
        self._cfg = cfg
        self._lock = asyncio.Lock()
        self._target_dir = cfg.app_models_dir / "moondream2"

    @property
    def target_dir(self) -> Path:
        return self._target_dir

    def expected_text_model_path(self) -> Path:
        return self._target_dir / self._cfg.vision_gguf_file

    def expected_mmproj_path(self) -> Path:
        return self._target_dir / self._cfg.vision_mmproj_file

    def is_cached(self) -> bool:
        """True если оба файла уже скачаны и ненулевого размера."""
        text_ok = self.expected_text_model_path().exists() and (
            self.expected_text_model_path().stat().st_size > 0
        )
        mmproj_ok = self.expected_mmproj_path().exists() and (
            self.expected_mmproj_path().stat().st_size > 0
        )
        return text_ok and mmproj_ok

    async def ensure_model_available(self) -> VisionModelPaths:
        """Гарантирует наличие GGUF файлов локально, скачивает если нужно.

        Идемпотентно: при повторных вызовах не качает заново (HF-кэш).
        Raises: `RuntimeError` если скачивание провалилось после всех retry.
        """
        async with self._lock:
            self._target_dir.mkdir(parents=True, exist_ok=True)
            if self.is_cached():
                log.debug(
                    "vision_model_cache_hit",
                    text=str(self.expected_text_model_path()),
                    mmproj=str(self.expected_mmproj_path()),
                )
                return VisionModelPaths(
                    text_model_path=self.expected_text_model_path(),
                    mmproj_path=self.expected_mmproj_path(),
                )

            log.info(
                "vision_model_download_start",
                repo=self._cfg.vision_gguf_repo,
                text_file=self._cfg.vision_gguf_file,
                mmproj_file=self._cfg.vision_mmproj_file,
                target=str(self._target_dir),
            )

            try:
                text_path = await asyncio.to_thread(
                    hf_hub_download,
                    repo_id=self._cfg.vision_gguf_repo,
                    filename=self._cfg.vision_gguf_file,
                    local_dir=str(self._target_dir),
                )
                mmproj_path = await asyncio.to_thread(
                    hf_hub_download,
                    repo_id=self._cfg.vision_gguf_repo,
                    filename=self._cfg.vision_mmproj_file,
                    local_dir=str(self._target_dir),
                )
            except HfHubHTTPError as exc:
                raise RuntimeError(
                    f"Failed to download Moondream 2 GGUF from "
                    f"{self._cfg.vision_gguf_repo}: {exc}"
                ) from exc

            resolved = VisionModelPaths(
                text_model_path=Path(text_path).resolve(),
                mmproj_path=Path(mmproj_path).resolve(),
            )
            log.info(
                "vision_model_download_done",
                text_mb=round(resolved.text_model_path.stat().st_size / 1_048_576, 1),
                mmproj_mb=round(resolved.mmproj_path.stat().st_size / 1_048_576, 1),
            )
            return resolved
