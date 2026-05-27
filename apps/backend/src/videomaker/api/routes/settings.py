"""/api/v1/settings — промпты, провайдеры моделей, runtime-конфигурация."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from videomaker.core.config import Settings, get_settings
from videomaker.models.job import (
    SubtitleStylePresetCreate,
    SubtitleStylePresetRead,
    SubtitleStylePresetUpdate,
    VisionProfile,
)
from videomaker.models.runtime_settings import PerformanceSettings
from videomaker.models.vision_settings import (
    ProfileMaskRead,
    VisionProfileOverride,
    VisionRuntimeSettings,
)
from videomaker.services import profile_masks as profile_masks_svc
from videomaker.services import settings_service, subtitle_store
from videomaker.services.api_keys_store import api_keys_status, set_api_keys
from videomaker.services.font_scanner import (
    FontScannerError,
    load_cache,
    refresh_cache,
)
from videomaker.services.runtime_settings_store import (
    get_performance_settings,
    get_vision_settings,
    set_performance_settings,
    set_vision_settings,
)
from videomaker.services.subtitle_store import (
    BuiltinPresetError,
    DefaultPresetError,
    PresetConflictError,
    PresetNotFoundError,
)
from videomaker.services.subtitle_styles import SYSTEM_FONTS
from videomaker.services.vision import (
    VisionHealthStatus,
    build_vision_client,
    reset_vision_client,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class PromptPayload(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    content: str = Field(min_length=1, max_length=32768)


class PromptList(BaseModel):
    prompts: list[PromptPayload]


class ModelsInfo(BaseModel):
    available_providers: list[str]
    available_transcribers: list[str]
    defaults: dict[str, str]
    # Per-provider список выбираемых моделей. UploadWizard рендерит Select
    # с этими опциями вместо free-text input — чтобы user мог переключаться
    # между дешёвой 3.1-flash-lite и надёжной 3-flash-preview без правки кода.
    available_llm_models: dict[str, list[str]]


@router.get("/performance", response_model=PerformanceSettings)
async def get_performance_settings_endpoint(
    settings: Settings = Depends(get_settings),
) -> PerformanceSettings:
    """Возвращает эффективные runtime-настройки (env defaults + БД overrides)."""

    return await get_performance_settings(settings)


@router.put("/performance", response_model=PerformanceSettings)
async def update_performance_settings(
    payload: PerformanceSettings,
) -> PerformanceSettings:
    """Bulk upsert всех runtime-полей. Cache инвалидируется автоматически."""

    return await set_performance_settings(payload)


class ApiKeysStatus(BaseModel):
    """Маскированный статус ключей — задан/не задан, без самих значений."""

    gemini_api_key: bool
    deepgram_api_key: bool
    publer_api_key: bool
    publer_workspace_id: bool


class ApiKeysUpdate(BaseModel):
    """PATCH-обновление ключей. Передавайте только изменяемые поля.

    Значение "" очищает ключ (возврат к значению из .env, если оно есть).
    """

    gemini_api_key: str | None = None
    deepgram_api_key: str | None = None
    publer_api_key: str | None = None
    publer_workspace_id: str | None = None


@router.get("/api-keys", response_model=ApiKeysStatus)
async def get_api_keys() -> ApiKeysStatus:
    """Какие ключи заданы (runtime или .env). Значения наружу не отдаются."""

    return ApiKeysStatus(**await api_keys_status())


@router.put("/api-keys", response_model=ApiKeysStatus)
async def update_api_keys(payload: ApiKeysUpdate) -> ApiKeysStatus:
    """Сохраняет ключи в runtime-настройки и применяет без рестарта."""

    await set_api_keys(payload.model_dump(exclude_unset=True))
    return ApiKeysStatus(**await api_keys_status())


class VisionSettingsResponse(BaseModel):
    """GET /settings/vision — runtime config + live health."""

    settings: VisionRuntimeSettings
    health: VisionHealthStatus
    gguf_repo: str
    gguf_file: str
    mmproj_file: str


@router.get("/vision", response_model=VisionSettingsResponse)
async def get_vision_settings_endpoint(
    settings: Settings = Depends(get_settings),
) -> VisionSettingsResponse:
    """Runtime vision settings + health status.

    Health вычисляется лениво: не грузит модель в RAM, только проверяет
    импорт llama-cpp-python и локальный кэш GGUF файлов.
    """
    vision = await get_vision_settings(settings)
    client = build_vision_client(settings)
    if client is None:
        health = VisionHealthStatus(
            available=False,
            model_loaded=False,
            backend="unavailable",
            error="vision disabled (cfg.vision_enabled=False)",
        )
    else:
        health = await client.health()
    return VisionSettingsResponse(
        settings=vision,
        health=health,
        gguf_repo=settings.vision_gguf_repo,
        gguf_file=settings.vision_gguf_file,
        mmproj_file=settings.vision_mmproj_file,
    )


@router.put("/vision", response_model=VisionRuntimeSettings)
async def update_vision_settings(
    payload: VisionRuntimeSettings,
) -> VisionRuntimeSettings:
    """Обновляет vision runtime-настройки. Сброс client-singleton если enabled поменялся."""
    current = await get_vision_settings()
    updated = await set_vision_settings(payload)
    if current.enabled != updated.enabled:
        await reset_vision_client()
    return updated


@router.get("/models", response_model=ModelsInfo)
async def models_info(settings: Settings = Depends(get_settings)) -> ModelsInfo:
    return ModelsInfo(
        available_providers=settings.available_llm_providers,
        available_transcribers=settings.available_transcribers,
        defaults={
            "gemini": settings.gemini_default_model,
            "anthropic": settings.anthropic_default_model,
            "openai": settings.openai_default_model,
            "zhipu": settings.zhipu_default_model,
            "mlx_whisper": settings.mlx_whisper_model,
            "deepgram": settings.deepgram_model,
        },
        available_llm_models={
            "gemini": list(settings.gemini_available_models),
            "anthropic": [settings.anthropic_default_model],
            "openai": [settings.openai_default_model],
            "zhipu": [settings.zhipu_default_model],
        },
    )


@router.get("/prompts", response_model=PromptList)
async def list_prompts() -> PromptList:
    records = await settings_service.list_prompt_overrides()
    return PromptList(
        prompts=[PromptPayload(key=r.key, content=r.content) for r in records]
    )


@router.get("/prompts/{key}", response_model=PromptPayload)
async def get_prompt(key: str) -> PromptPayload:
    record = await settings_service.get_prompt_override(key)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"prompt {key!r} not found",
        )
    return PromptPayload(key=record.key, content=record.content)


@router.put("/prompts/{key}", response_model=PromptPayload)
async def upsert_prompt(key: str, body: PromptPayload) -> PromptPayload:
    if body.key != key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="body.key must match URL key",
        )
    record = await settings_service.upsert_prompt_override(
        key=key, content=body.content
    )
    return PromptPayload(key=record.key, content=record.content)


class FontListResponse(BaseModel):
    fonts: list[str]
    scanned_at: str | None = None
    source: str  # "system" | "fallback"


@router.get("/fonts", response_model=FontListResponse)
async def list_fonts(
    settings: Settings = Depends(get_settings),
) -> FontListResponse:
    """Список установленных системных шрифтов.

    Читает закешированный список из `data/fonts_cache.json`. Кеш прогревается
    фоновой задачей при старте приложения — если на первом запросе кеша ещё
    нет, возвращаем fallback (hardcoded популярный набор), чтобы UI не
    блокировался на 6-секундном сканировании.

    Для явного обновления используется `POST /fonts/refresh`.
    """

    cache = load_cache(settings.app_fonts_cache_path)
    if cache is None or not cache.fonts:
        return FontListResponse(
            fonts=list(SYSTEM_FONTS),
            scanned_at=None,
            source="fallback",
        )
    return FontListResponse(
        fonts=list(cache.fonts),
        scanned_at=cache.scanned_at or None,
        source="system",
    )


@router.post("/fonts/refresh", response_model=FontListResponse)
async def refresh_fonts(
    settings: Settings = Depends(get_settings),
) -> FontListResponse:
    """Принудительно пересканирует системные шрифты и обновляет кеш.

    Блокирует вызов пока `system_profiler` не вернёт результат (~6 секунд
    на macOS). UI должен показывать spinner и отключать кнопку на время.
    """

    try:
        cache = await refresh_cache(settings.app_fonts_cache_path)
    except FontScannerError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"font scan failed: {exc}",
        ) from exc
    return FontListResponse(
        fonts=list(cache.fonts),
        scanned_at=cache.scanned_at,
        source="system",
    )


@router.get("/subtitle_presets", response_model=list[SubtitleStylePresetRead])
async def list_subtitle_presets() -> list[SubtitleStylePresetRead]:
    rows = await subtitle_store.list_presets()
    return [SubtitleStylePresetRead.from_row(r) for r in rows]


@router.get(
    "/subtitle_presets/{preset_id}", response_model=SubtitleStylePresetRead
)
async def get_subtitle_preset(preset_id: int) -> SubtitleStylePresetRead:
    row = await subtitle_store.get_preset(preset_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"preset {preset_id} not found",
        )
    return SubtitleStylePresetRead.from_row(row)


@router.post(
    "/subtitle_presets",
    response_model=SubtitleStylePresetRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_subtitle_preset(
    payload: SubtitleStylePresetCreate,
) -> SubtitleStylePresetRead:
    try:
        row = await subtitle_store.create_preset(payload)
    except PresetConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return SubtitleStylePresetRead.from_row(row)


@router.put(
    "/subtitle_presets/{preset_id}", response_model=SubtitleStylePresetRead
)
async def update_subtitle_preset(
    preset_id: int, payload: SubtitleStylePresetUpdate
) -> SubtitleStylePresetRead:
    try:
        row = await subtitle_store.update_preset(preset_id, payload)
    except PresetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except BuiltinPresetError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except PresetConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return SubtitleStylePresetRead.from_row(row)


@router.delete(
    "/subtitle_presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_subtitle_preset(preset_id: int) -> None:
    try:
        await subtitle_store.delete_preset(preset_id)
    except PresetNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except BuiltinPresetError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)
        ) from exc
    except DefaultPresetError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


# ──────────────────────────────────────────────────────────────────────────
# Vision Profile overrides (/settings/profiles)
# ──────────────────────────────────────────────────────────────────────────


@router.get("/profiles", response_model=list[ProfileMaskRead])
async def list_vision_profiles() -> list[ProfileMaskRead]:
    """Все 5 профилей нарезки с эффективной маской + is_customized."""
    return await profile_masks_svc.list_effective_masks()


@router.get("/profiles/{profile}", response_model=ProfileMaskRead)
async def get_vision_profile(profile: VisionProfile) -> ProfileMaskRead:
    return await profile_masks_svc.get_effective_mask_read(profile)


@router.put("/profiles/{profile}", response_model=ProfileMaskRead)
async def upsert_vision_profile(
    profile: VisionProfile, payload: VisionProfileOverride
) -> ProfileMaskRead:
    return await profile_masks_svc.upsert_profile_override(profile, payload)


@router.delete("/profiles/{profile}", response_model=ProfileMaskRead)
async def reset_vision_profile(profile: VisionProfile) -> ProfileMaskRead:
    """Удаляет override — профиль возвращается к дефолтным настройкам."""
    return await profile_masks_svc.reset_profile_override(profile)
