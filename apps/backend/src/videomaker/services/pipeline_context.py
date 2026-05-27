"""PipelineContext — shared mutable state для всех pipeline-стадий.

Вводится Phase 2 архитектурной декомпозиции (docs/superpowers/plans/
2026-04-20-architectural-cleanup.md). Каждая стадия (ingest → analysis →
render) принимает контекст, обогащает его промежуточными артефактами и
возвращает обратно. Заменяет 770-строчный scope функции
``_run_pipeline_impl``, где все локальные переменные жили в одной async
функции.

Используется в комбинации с ``pipeline_stages/{ingest,analysis,render}.py``
(будут добавлены в Task 2.2-2.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from videomaker.core.artifacts import ArtifactsManager
from videomaker.core.config import Settings
from videomaker.models.canvas import ProjectCanvas
from videomaker.models.job import SubtitleStyleConfig, VisionProfile
from videomaker.models.post_production import PostProductionConfig
from videomaker.models.reel_plan import AnalysisResult, ReelPlan
from videomaker.models.runtime_settings import PerformanceSettings
from videomaker.models.story_script import RhythmReport, StoryScript, StoryVariants
from videomaker.models.vision_settings import VisionRuntimeSettings
from videomaker.services.agents.orchestrator import ExtractionResult
from videomaker.services.chunker import TranscriptChunk
from videomaker.services.compression import CompressionResult
from videomaker.services.jobs import JobService
from videomaker.services.media import MediaInfo
from videomaker.services.profile_masks import ProfileMask
from videomaker.services.reducer import ReduceResult
from videomaker.services.silence_cutter import CleanedTranscript
from videomaker.services.transcribers.base import (
    TranscribedSegment,
    TranscribedWord,
    TranscriptResult,
)

if TYPE_CHECKING:
    # pipeline.py импортирует pipeline_context — держим forward-references,
    # чтобы не создавать циклические импорты на уровне модулей.
    from videomaker.services.pipeline import PipelineResult, RenderedReel


@dataclass(slots=True)
class PipelineContext:
    """Mutable shared state между стадиями pipeline'а.

    Заполняется постепенно по мере прохождения стадий. Поля, которые
    создаются конкретной стадией, по умолчанию ``None`` или пустая
    коллекция — стадия, создающая артефакт, присваивает значение.
    """

    # ── Входные параметры (immutable по факту, зафиксированы при старте) ──
    job_id: str
    source_path: Path
    transcriber_name: str
    llm_provider: str
    llm_model: str
    target_aspect: str
    fit_mode: str
    source_language: str
    subtitle_style: SubtitleStyleConfig | None
    post_production_config: PostProductionConfig | None
    use_proxy: bool
    use_source_for_render: bool
    target_reel_count: int | None
    force_reingest: bool
    vision_profile: VisionProfile

    # ── Инфраструктура ──
    service: JobService
    artifacts: ArtifactsManager
    settings: Settings
    perf: PerformanceSettings

    # ── Stage 1-2: probe + proxy ──
    media_info: MediaInfo | None = None
    proxy_path: Path | None = None
    # Путь, используемый для декодирования (proxy если сгенерён, иначе source_path).
    # Render-стадия для итогового MP4 может возвращаться к source_path через
    # use_source_for_render; этот путь используется для extract_audio и
    # face-tracking над быстрой копией.
    media_path_for_decode: Path | None = None

    # ── Stage 2-3: transcribe + translate ──
    # Полный TranscriptResult (после translate) нужен downstream для
    # _transcript_from_cleaned, который собирает урезанный транскрипт из
    # cleaned.words, унаследуя transcriber/model/language/raw_metadata.
    transcript: TranscriptResult | None = None
    transcript_segments: list[TranscribedSegment] = field(default_factory=list)
    transcript_words: list[TranscribedWord] = field(default_factory=list)
    detected_language: str | None = None
    needs_translation: bool = False

    # ── Stage 4: silence_cut + fillers ──
    # Полный CleanedTranscript — нужен downstream: .words (для analyze/render),
    # .stats (для analysis_meta), .source_duration_sec (для _transcript_from_cleaned).
    cleaned_transcript: CleanedTranscript | None = None
    cleaned_segments: list[TranscribedSegment] = field(default_factory=list)
    cleaned_words: list[TranscribedWord] = field(default_factory=list)

    # ── Stage 5: analyze (Kartoziya) ──
    # Типы модулей service/* и models/* импортируются напрямую; pipeline.py
    # (PipelineResult/RenderedReel) — через TYPE_CHECKING чтобы избежать
    # циклических импортов (pipeline.py → pipeline_context → pipeline).
    chunks: list[TranscriptChunk] = field(default_factory=list)
    compression: CompressionResult | None = None
    canvas: ProjectCanvas | None = None
    extraction_result: ExtractionResult | None = None
    reduce_result: ReduceResult | None = None
    story_script: StoryScript | None = None
    rhythm_report: RhythmReport | None = None
    variants: StoryVariants | None = None
    analysis_reels: list[ReelPlan] = field(default_factory=list)
    # Финальный ``AnalysisResult`` после Stage 5.8-5.10 (reels composer +
    # coherence + closure + cover selector). Downstream render читает только
    # ``analysis.reels``; внутренние артефакты (chunks, canvas, variants, ...)
    # сохраняются выше для observability и отладки упавших job'ов.
    analysis: AnalysisResult | None = None
    # Эффективная маска профиля (resolved через get_effective_profile_mask).
    # Заполняется analysis-стадией и используется render-стадией для
    # propagation в ProjectGraph.
    profile_mask: ProfileMask | None = None

    # ── Stage 6: render ──
    vision_runtime: VisionRuntimeSettings | None = None
    rendered: list[RenderedReel] = field(default_factory=list)

    # ── Финальные paths артефактов ──
    transcript_path: Path | None = None
    cleaned_path: Path | None = None
    reel_plan_path: Path | None = None
    analysis_summary_path: Path | None = None

    def to_pipeline_result(self) -> PipelineResult:
        """Собирает PipelineResult из заполненного контекста.

        ``PipelineResult`` импортируется локально внутри метода, чтобы не
        создавать циклический импорт на уровне модуля (pipeline.py →
        pipeline_context → pipeline.py). Forward reference через
        TYPE_CHECKING даёт static-типизацию без runtime-импорта.
        """
        from videomaker.services.pipeline import PipelineResult

        if self.media_info is None:
            raise RuntimeError(
                "PipelineContext.to_pipeline_result: media_info not set"
            )
        if self.transcript_path is None or self.cleaned_path is None:
            raise RuntimeError(
                "PipelineContext.to_pipeline_result: transcript/cleaned paths not set"
            )
        if self.reel_plan_path is None or self.analysis_summary_path is None:
            raise RuntimeError(
                "PipelineContext.to_pipeline_result: reel_plan/analysis_summary paths not set"
            )

        return PipelineResult(
            duration_sec=self.media_info.duration_sec,
            transcript_path=self.transcript_path,
            cleaned_path=self.cleaned_path,
            reel_plan_path=self.reel_plan_path,
            analysis_summary_path=self.analysis_summary_path,
            rendered=list(self.rendered),
        )
