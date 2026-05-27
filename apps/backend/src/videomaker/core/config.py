"""Настройки приложения. Загружаются из .env в корне репозитория."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(DEFAULT_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM providers
    gemini_api_key: str | None = None
    # Gemini tier-матрица жёстко ограничена Flash-Lite вариантами
    # (gemini-2.5-flash-lite / gemini-3.1-flash-lite-preview). Любые более
    # дорогие модели (Flash, Pro, *-preview кроме Lite) запрещены по user
    # constraint — pipeline физически не может их вызвать. Runtime override
    # через PerformanceSettings.llm_tier_profile (fast | legacy).
    gemini_default_model: str = "gemini-2.5-flash-lite"
    gemini_rate_limit_rpm: int = Field(default=60, ge=1, le=10000)
    # Gemini модели, которые можно выбрать в UploadWizard / Settings.
    # Только Lite-варианты: более дорогие модели запрещены по user constraint.
    gemini_available_models: tuple[str, ...] = (
        "gemini-3.1-flash-lite-preview",  # $0.25/$1.50 — cheapest, preview
        "gemini-2.5-flash-lite",           # stable Lite поколения 2.5 — надёжный JSON schema
    )

    anthropic_api_key: str | None = None
    anthropic_default_model: str = "claude-sonnet-4-5-20250929"

    openai_api_key: str | None = None
    openai_default_model: str = "gpt-5"

    # Zhipu Z.AI — GLM-5.1 и семейство GLM-4.x. API-ключ формата "<id>.<secret>".
    # Два разных endpoint в зависимости от плана:
    #   - GLM Coding Plan ($18/мес подписка):
    #     https://api.z.ai/api/coding/paas/v4  (дефолт)
    #     Доступны модели: glm-5.1, glm-5-turbo, glm-4.7, glm-4.5-air.
    #   - General pay-as-you-go API:
    #     https://open.bigmodel.cn/api/paas/v4
    #     Весь ассортимент, требует предоплату.
    # Docs: https://docs.z.ai/devpack/faq
    zhipu_api_key: str | None = None
    zhipu_base_url: str = "https://api.z.ai/api/coding/paas/v4"
    zhipu_default_model: str = "glm-5.1"
    zhipu_pro_model: str = "glm-5.1"
    zhipu_flash_model: str = "glm-5.1"
    zhipu_flash_lite_model: str = "glm-5.1"
    # Max output tokens для GLM-5.1 — до 32K согласно docs. Храним явно
    # чтобы не смешивать с DEFAULT_MAX_OUTPUT_TOKENS=16000 в llm_client.
    zhipu_max_output_tokens: int = Field(default=16000, ge=512, le=32768)
    # Coding Plan Lite: ~80 prompts/5h × (15-20 invocations) ≈ 5 RPM. Pro и
    # Max выше, но точные числа не документированы. Дефолт — конservative.
    zhipu_rate_limit_rpm: int = Field(default=6, ge=1, le=1000)
    # Coding Plan имеет concurrency=1 (один in-flight запрос). Pipeline,
    # который шлёт 6 агентов × N chunks параллельно — упирается в 429
    # code 1302. Семафор в get_zhipu_concurrency_gate() сериализует запросы.
    # Для Pro/Max плана можно поднять до 2-3.
    zhipu_max_concurrency: int = Field(default=1, ge=1, le=10)

    # STT
    mlx_whisper_model: str = "mlx-community/whisper-large-v3-turbo"
    deepgram_api_key: str | None = None
    deepgram_model: str = "nova-3"

    # App
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    app_db_path: Path = REPO_ROOT / "data" / "videomaker.db"
    app_artifacts_dir: Path = REPO_ROOT / "data" / "artifacts"
    app_upload_dir: Path = REPO_ROOT / "data" / "uploads"
    app_fonts_cache_path: Path = REPO_ROOT / "data" / "fonts_cache.json"
    app_post_production_assets_dir: Path = (
        REPO_ROOT / "data" / "post_production_assets"
    )
    app_face_cache_dir: Path = REPO_ROOT / "data" / "face_cache"
    app_models_dir: Path = REPO_ROOT / "data" / "models"
    app_max_upload_size_mb: int = Field(default=30720, ge=1, le=32768)
    app_max_asset_size_mb: int = Field(default=2048, ge=1, le=16384)

    # Proxy pipeline (v0.5). Эти env-значения служат **seed** для
    # `runtime_settings` БД (Cycle 4.5) — конечный pipeline-код читает
    # эффективные значения через `runtime_settings_store.get_performance(...)`.
    app_proxy_enabled: bool = True
    app_proxies_dir: Path = REPO_ROOT / "data" / "proxies"
    app_proxy_max_dim: int = Field(default=1920, ge=720, le=3840)
    app_proxy_video_crf: int = Field(default=23, ge=18, le=30)
    app_proxy_video_maxrate_kbps: int = Field(default=6000, ge=1000, le=20000)
    app_proxy_audio_bitrate_kbps: int = Field(default=128, ge=64, le=320)
    app_proxy_cache_max_gb: int = Field(default=50, ge=5, le=500)
    app_proxy_skip_height_le: int = Field(default=1080, ge=240, le=4320)
    app_proxy_skip_duration_lt_sec: int = Field(default=300, ge=10, le=3600)
    app_proxy_skip_bitrate_lt_kbps: int = Field(default=8000, ge=500, le=200000)
    app_proxy_lock_timeout_sec: int = Field(default=1800, ge=60, le=14400)

    # CORS
    frontend_origin: str = "http://localhost:3000"

    # Chunking (см. раздел "Chunking strategy" плана)
    chunk_token_threshold: int = Field(default=20000, ge=1000)
    chunk_window_tokens: int = Field(default=15000, ge=500)
    chunk_overlap_tokens: int = Field(default=1500, ge=0)
    llm_max_concurrency: int = Field(default=10, ge=1, le=64)

    # Vision layer (Moondream 2 local GGUF — Phase 1 of vision rollout).
    # По умолчанию OFF — пайплайн работает байтово идентично aудио-only
    # baseline когда vision_enabled=False. Runtime-override через
    # runtime_settings_store / /settings/vision API.
    vision_enabled: bool = False
    vision_gguf_repo: str = "moondream/moondream2-gguf"
    vision_gguf_file: str = "moondream2-text-model-f16.gguf"
    vision_mmproj_file: str = "moondream2-mmproj-f16.gguf"
    vision_cache_dir: Path = REPO_ROOT / "data" / "vision_cache"
    vision_frame_sample_rate_sec: float = Field(default=10.0, ge=0.5, le=60.0)

    # Transcript cache — SHA256-keyed persistent store (PHASE 1 of profiles
    # rollout). Повторный прогон того же видеофайла возвращает кэшированный
    # TranscriptResult без повторного STT. Инвалидация — через
    # force_reingest flag на Project или явный delete.
    transcript_cache_dir: Path = REPO_ROOT / "data" / "transcripts"

    # Thumbnail cache — первый кадр source.mp4 через ffmpeg. Используется UI
    # на dashboard для превью-карточек jobs. Cache key = job_id (immutable).
    app_thumbnails_dir: Path = REPO_ROOT / "data" / "thumbnails"

    vision_max_concurrency: int = Field(default=2, ge=1, le=8)
    vision_n_gpu_layers: int = Field(default=-1, ge=-1, le=999)
    vision_n_ctx: int = Field(default=2048, ge=512, le=8192)

    # Face tracker (mediapipe). Dense sampling 0.3s (3.3Hz) нужен для
    # плавного dynamic anchor tracking в base_crop_plan (v0.7) и
    # zoom_planner (v0.6). Кэш на диске идемпотентен по SHA256 + interval.
    # min_confidence=0.5 — стандартный порог mediapipe face detection.
    face_tracker_sample_interval_sec: float = Field(default=0.3, gt=0.0, le=5.0)
    face_tracker_min_confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    # Reducer (Stage 5.4) LLM call params. max_tokens=16000 эмпирически
    # достаточно для ranked_cap=60 items (средний размер ответа ~8-12K).
    # temperature=0.1 — single-mode; ensemble mode разбрасывает 0.1..0.3
    # вокруг этого значения (см. reducer._run_ensemble_reduce).
    reducer_max_tokens: int = Field(default=16000, ge=1024, le=65536)
    reducer_temperature: float = Field(default=0.1, ge=0.0, le=1.0)

    # LLM retry policy (tenacity). 3 попытки с экспоненциальной задержкой
    # 2s → 4s → 8s (clamped to max 30s) покрывают transient 429/503 без
    # избыточных delays. Применяется во всех LLM-вызовах через _retry().
    llm_retry_max_attempts: int = Field(default=3, ge=1, le=10)
    llm_retry_min_wait_sec: int = Field(default=2, ge=1, le=60)
    llm_retry_max_wait_sec: int = Field(default=30, ge=1, le=600)

    # Reel duration targeting (Fix 3, Phase Reels-quality 2026-04-21).
    # Управляет conditional Pass 3 в reels_composer._merge_short_groups:
    # короткие группы без development-сегментов ("тонкий arc") подтягиваются
    # к reel_target_duration_sec через merge с соседями. Группы с >=2
    # development сегментами не трогаются — считается что arc уже богат.
    # Это возвращает полноту для 37-45s рилсов БЕЗ усреднения всех к одной
    # длительности (проблема, из-за которой Pass 3 был удалён в 3c139c4).
    reel_target_duration_sec: float = Field(
        default=62.0,
        ge=45.0,
        le=80.0,
        description=(
            "Целевая длительность рилса в секундах для умного Pass 3. "
            "Композер тянет к target группы где < 2 development-сегментов. "
            "Range 45-80 соответствует обновлённым REEL_MIN/REEL_MAX."
        ),
    )
    reel_target_pull_strength: Literal["off", "soft", "hard"] = Field(
        default="soft",
        description=(
            "Сила подтягивания к target. off=без pull (поведение после 3c139c4), "
            "soft=только thin arcs (< 2 development сегментов), "
            "hard=все группы подтягиваются (старое поведение до 3c139c4)."
        ),
    )
    skip_complete_short_arcs: bool = Field(
        default=True,
        description=(
            "Env default для PerformanceSettings.skip_complete_short_arcs. "
            "См. runtime_settings.py для семантики."
        ),
    )

    # Publer Business API v1 — интеграция шедулера (Instagram Reels / YouTube
    # Shorts). API-ключ выдаётся в Publer workspace settings, workspace_id
    # вытаскивается из /api/v1/workspaces. Timezone используется как дефолт
    # для UploadWizard-полей scheduled_at (юзер в Азии).
    publer_api_key: str = Field(default="", alias="PUBLER_API_KEY")
    publer_workspace_id: str = Field(default="", alias="PUBLER_WORKSPACE_ID")
    publer_scheduler_tz: str = Field(default="Asia/Ho_Chi_Minh", alias="PUBLER_SCHEDULER_TZ")
    publer_base_url: str = Field(
        default="https://app.publer.com/api/v1", alias="PUBLER_BASE_URL"
    )
    publer_request_timeout_sec: float = Field(
        default=30.0, alias="PUBLER_REQUEST_TIMEOUT_SEC"
    )

    @field_validator(
        "app_db_path",
        "app_artifacts_dir",
        "app_upload_dir",
        "app_fonts_cache_path",
        "app_post_production_assets_dir",
        "app_face_cache_dir",
        "app_models_dir",
        "app_proxies_dir",
        "vision_cache_dir",
        "transcript_cache_dir",
        "app_thumbnails_dir",
        mode="before",
    )
    @classmethod
    def resolve_paths(cls, value: str | Path) -> Path:
        path = Path(value) if isinstance(value, str) else value
        if not path.is_absolute():
            path = (REPO_ROOT / path).resolve()
        return path

    @property
    def max_upload_size_bytes(self) -> int:
        return self.app_max_upload_size_mb * 1024 * 1024

    @property
    def max_asset_size_bytes(self) -> int:
        return self.app_max_asset_size_mb * 1024 * 1024

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.app_db_path}"

    @property
    def available_llm_providers(self) -> list[str]:
        providers: list[str] = []
        if self.gemini_api_key:
            providers.append("gemini")
        if self.anthropic_api_key:
            providers.append("anthropic")
        if self.openai_api_key:
            providers.append("openai")
        if self.zhipu_api_key:
            providers.append("zhipu")
        return providers

    @property
    def available_transcribers(self) -> list[str]:
        # TIER1-#7: stable_ts_mlx — default (±20-30ms word timestamps).
        # mlx_whisper остаётся как fallback для cache hit совместимости.
        return (
            ["stable_ts_mlx", "mlx_whisper"]
            + (["deepgram"] if self.deepgram_api_key else [])
        )

    def ensure_directories(self) -> None:
        for directory in (
            self.app_db_path.parent,
            self.app_artifacts_dir,
            self.app_upload_dir,
            self.app_post_production_assets_dir,
            self.app_face_cache_dir,
            self.app_models_dir,
            self.app_proxies_dir,
            self.vision_cache_dir,
            self.transcript_cache_dir,
            self.app_thumbnails_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
