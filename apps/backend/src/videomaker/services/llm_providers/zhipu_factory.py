"""Zhipu GLM provider factory.

GLM-5.1 Coding Plan: все три tier'а мапятся на
``Settings.zhipu_{pro,flash,flash_lite}_model`` (по умолчанию все = ``"glm-5.1"``).
Hard switch задаётся из UI через ``PerformanceSettings.pipeline_llm_provider``.
"""

from __future__ import annotations

from videomaker.core.config import Settings
from videomaker.services.llm_client import GLMClient, LLMClient, LLMError, LLMTier


class ZhipuProviderFactory:
    name = "zhipu"

    def build_client(self, *, settings: Settings, model: str) -> LLMClient:
        if not settings.zhipu_api_key:
            raise LLMError("ZHIPU_API_KEY missing")
        return GLMClient(
            api_key=settings.zhipu_api_key,
            model=model,
            base_url=settings.zhipu_base_url,
        )

    def tier_model(self, settings: Settings, tier: LLMTier) -> str:
        mapping: dict[LLMTier, str] = {
            "pro": settings.zhipu_pro_model,
            "flash": settings.zhipu_flash_model,
            "flash_lite": settings.zhipu_flash_lite_model,
        }
        return mapping[tier]
