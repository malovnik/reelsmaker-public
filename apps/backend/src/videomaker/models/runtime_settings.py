"""Runtime-tunable performance settings.

Все поля можно менять через UI (`/settings/performance`) без рестарта.
Env-defaults в `core/config.py` служат seed для первой записи.
"""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class _SettingsLike(Protocol):
    """Структурный подтип ``core.config.Settings`` нужный ``from_settings``.

    Декуплим model-слой от core.config: вместо прямого импорта описываем
    минимальный duck-type контракт. Callers передают полный Settings,
    Pyright проверяет наличие нужных полей через структурную типизацию.
    """

    app_proxy_enabled: bool
    app_proxy_max_dim: int
    app_proxy_video_crf: int
    app_proxy_video_maxrate_kbps: int
    app_proxy_audio_bitrate_kbps: int
    app_proxy_cache_max_gb: int
    app_proxy_lock_timeout_sec: int
    app_proxy_skip_height_le: int
    app_proxy_skip_duration_lt_sec: int
    app_proxy_skip_bitrate_lt_kbps: int

CoherenceMode = Literal["off", "reject", "resort"]
JLCutMode = Literal["role_change", "all_transitions"]
LLMTierProfile = Literal["fast", "legacy"]
LLMLiteVariant = Literal["2_5", "3_1"]
PipelineLLMProvider = Literal["gemini", "zhipu"]

#: T10.2 — параллельные стратегии snap'а:
#: - "beat": legacy T2.5 — ±max_shift к librosa.beat beats (подходит для music)
#: - "onset": T10.2 — ±max_shift к librosa.onset speech onsets (talking-head)
#: - "both": onset сперва, fallback beat если onset не найден
#: - "off": без snap (hard cuts по исходным timestamp'ам)
SnapStrategy = Literal["beat", "onset", "both", "off"]

#: T11 pipeline mode: Manual = текущие runtime_settings;
#: Automatic = auto_config_advisor выставляет настройки per-video.
PipelineMode = Literal["manual", "automatic"]

#: Narrative pipeline mode (см. docs/top-down-architecture-roadmap.md,
#: docs/opusclip-2026-research.md):
#: - "bottom_up": legacy 9-stage extraction→reducer→story_doctor→composer (default)
#: - "chaptered": Phase 1-6 top-down per-chapter (broken на монологах, legacy)
#: - "map_reduce": Phase 8 OpusClip-parity (chunks→scorer→reducer, production target)
NarrativeMode = Literal["bottom_up", "chaptered", "map_reduce", "viral_2026"]


class PerformanceSettings(BaseModel):
    """Per-installation runtime config для proxy + render pipeline."""

    model_config = ConfigDict(extra="forbid")

    # Render
    render_concurrency: int = Field(default=2, ge=1, le=8)

    # LLM tier profile — глобальный переключатель модели.
    # Применяется в build_llm_for_tier() без рестарта (см. _tier_profiles).
    # Только Lite-варианты: более дорогие модели запрещены по user constraint.
    #   - fast: всё на выбранном Lite-варианте (см. llm_lite_variant)
    #   - legacy: всё на 3.1-flash-lite-preview (историческая совместимость)
    llm_tier_profile: LLMTierProfile = "fast"

    # Какую Lite-модель использовать в профиле ``fast``:
    # - "2_5": gemini-2.5-flash-lite (стабильная structured output, default)
    # - "3_1": gemini-3.1-flash-lite-preview (дешевле, preview-статус)
    # Legacy всегда использует 3.1 независимо от этого поля.
    llm_lite_variant: LLMLiteVariant = "2_5"

    # Hard switch LLM provider для Kartoziya pipeline.
    # - "gemini" (дефолт) — Gemini с tier-матрицей (llm_tier_profile).
    # - "zhipu" — весь pipeline на Zhipu GLM-5.1 (требует ZHIPU_API_KEY).
    # Меняется без рестарта через PUT /api/v1/settings/performance.
    # Защита от регрессии: дефолт "gemini" — пайплайн работает как раньше
    # если пользователь не менял поле.
    pipeline_llm_provider: PipelineLLMProvider = "gemini"

    # Arc-coherence validation (Stage 5.9) — следит, чтобы hook/body/payoff
    # рилса звучали как единая мысль. Нужно после Task #28 cross-group pull,
    # который может подтянуть payoff из другой части сюжета.
    coherence_mode: CoherenceMode = "resort"
    coherence_threshold: float = Field(default=0.5, ge=0.0, le=1.0)

    # Fix 5 — тяжёлые стадии pipeline как togglable фичи.
    # variants_generator_enabled: Stage 5.7 (generate_variants) — Gemini Pro
    # строит 4 формата (long_philosophical/package_of_shorts/punchy_summary/
    # deep_dive). Если выключено, pipeline собирает одиночный fallback variant
    # (копия base arc как long_philosophical), это уменьшает LLM-нагрузку
    # ~15-20% за счёт одного тяжёлого Pro-вызова. Composer по-прежнему работает
    # с VariantKind=long_philosophical — behaviour остаётся совместимым.
    variants_generator_enabled: bool = Field(
        default=True,
        description=(
            "Включает Stage 5.7 Variants Generator (Gemini Pro, 4 варианта рилса). "
            "Выключение ускоряет pipeline ~15-20%: используется одиночный "
            "long_philosophical вариант-копия исходной арки."
        ),
    )

    # rhythm_critique_loop_enabled: Stage 5.5 iterative critique
    # (_compose_with_rhythm_loop). LLM может переписать story до 3 раз, пока
    # rhythm_score не пройдёт порог. Выключение оставляет только первый проход
    # compose_story_script + single rhythm check — дешевле и даёт больше
    # вариабельности между рилсами (без схождения в локальный «правильный»
    # ритм). По умолчанию включено — это эталонный режим.
    rhythm_critique_loop_enabled: bool = Field(
        default=True,
        description=(
            "Включает rhythm critique loop в Stage 5.5 Story Doctor. При False "
            "используется один проход compose_story_script без повторного "
            "переписывания. Быстрее ~10-15% на длинных видео, даёт больше "
            "вариабельности между рилсами."
        ),
    )

    # Fix 3 UI override: reel_target_* уже есть в Settings (env defaults),
    # дублируем в PerformanceSettings чтобы юзер мог менять через UI без
    # рестарта. Composer читает сперва PerformanceSettings (UI override),
    # затем Settings (env fallback) — см. reels_composer._get_target_*.
    reel_target_duration_sec: float = Field(
        default=62.0,
        ge=45.0,
        le=80.0,
        description=(
            "Целевая длительность рилса для conditional Pass 3 в composer. "
            "Range 45-80 (iteration 2026-04-22 — сдвинуто в сторону более "
            "длинных рилсов с бoльшим emotional buildup). 62=середина диапазона."
        ),
    )
    reel_target_pull_strength: Literal["off", "soft", "hard"] = Field(
        default="soft",
        description=(
            "Сила подтягивания к target в composer. off=без pull, "
            "soft=только thin arcs (< 2 development), hard=все группы (legacy). "
            "soft — рекомендованный default, не ломает богатые арки."
        ),
    )
    skip_complete_short_arcs: bool = Field(
        default=True,
        description=(
            "Защищать короткие закрытые арки (hook+payoff под REEL_MIN) "
            "от мёрджа с соседями в Pass 1. True (default) = punchy 30-40s "
            "рилсы живут как отдельные единицы. False = сливаются с "
            "соседями для более длинных рилсов в диапазоне 45-80s."
        ),
    )

    # Proxy generation toggle
    proxy_enabled: bool = True

    # Proxy encoder profile
    proxy_max_dim: int = Field(default=1920, ge=720, le=3840)
    proxy_video_crf: int = Field(default=23, ge=18, le=30)
    proxy_video_maxrate_kbps: int = Field(default=6000, ge=1000, le=20000)
    proxy_audio_bitrate_kbps: int = Field(default=128, ge=64, le=320)

    # Proxy cache
    proxy_cache_max_gb: int = Field(default=50, ge=5, le=500)
    proxy_lock_timeout_sec: int = Field(default=1800, ge=60, le=14400)

    # Proxy skip heuristic (когда source уже "лёгкий" — не делаем proxy)
    proxy_skip_height_le: int = Field(default=1080, ge=240, le=4320)
    proxy_skip_duration_lt_sec: int = Field(default=300, ge=10, le=3600)
    proxy_skip_bitrate_lt_kbps: int = Field(default=8000, ge=500, le=200000)

    # Defaults для UI чекбоксов на /upload
    default_use_source_for_render: bool = False

    # TIER2-#14: Micro-pause compression (сжатие пауз в речи).
    # Silero VAD находит паузы длиннее ``pause_compression_threshold_sec``
    # и укорачивает их до ``pause_compression_keep_sec`` (по половине с
    # каждой стороны). Результат — речь звучит плотнее без потери смысла,
    # рилс умещает больше информации за 30-60 секунд.
    pause_compression_enabled: bool = False
    pause_compression_threshold_sec: float = Field(default=0.4, ge=0.2, le=2.0)
    pause_compression_keep_sec: float = Field(default=0.2, ge=0.05, le=1.0)

    # T2.7: breath/inhale compression (второй проход после pause_compression).
    # Ловит короткие non-speech промежутки (0.20-0.40 сек) которые обычно
    # содержат межфразовые вдохи. Сокращает до ``breath_keep_sec`` чтобы
    # речь звучала ещё плотнее. Запускается ПОСЛЕ pause_compression в том
    # же pipeline — двойной проход по уже-сжатым cuts.
    # Отдельный feature flag чтобы пользователь мог иметь pause_compression
    # без breath (умеренная плотность) или оба (максимальная плотность).
    breath_compression_enabled: bool = False
    breath_compression_threshold_sec: float = Field(default=0.25, ge=0.15, le=0.5)
    breath_compression_keep_sec: float = Field(default=0.08, ge=0.03, le=0.2)

    # T2.5: rhythm-aware cutting — прилепляет cut-границы к beat'ам
    # детектированным librosa. Полезно для видео с фоновой музыкой
    # (fashion, travel). Для talking_head без музыки detect_beats
    # возвращает []- snap превращается в no-op.
    rhythm_aware_cuts_enabled: bool = False
    rhythm_aware_max_shift_sec: float = Field(default=0.15, ge=0.05, le=0.3)

    # TIER2-#13: Filler removal (удаление «эм/ну/вот/um/uh»).
    # Использует ``TranscribedWord.is_filler`` (TIER1-#3 лексикон) и,
    # опционально в aggressive, ``confidence < filler_confidence_threshold``.
    # edge_buffer_sec даёт ±30ms вокруг filler'а — чтобы срез был чистым.
    filler_removal_enabled: bool = False
    filler_removal_aggressive: bool = False
    filler_confidence_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    filler_edge_buffer_sec: float = Field(default=0.03, ge=0.0, le=0.15)

    # TIER2-#12: 5x ensemble judge для reduce_and_rank.
    # N параллельных LLM-вызовов с разной температурой → median composite_score
    # + minority veto. +7-10 pp scoring accuracy (research Q4, RewardBench 2).
    # Cost: в N раз больше input+output токенов на reducer-стадии.
    reducer_ensemble_size: int = Field(default=1, ge=1, le=5)
    reducer_ensemble_veto: int = Field(default=2, ge=1, le=5)

    # TIER2-#15: J/L-cut planner (сглаженные переходы в рилсах).
    # L-cut: аудио текущей сцены продолжает играть поверх видео следующей.
    # J-cut: аудио следующей сцены начинает играть до переключения видео.
    # Применяется только на ролевых границах (hook↔development↔peak↔payoff)
    # или на всех переходах — в зависимости от ``jl_cut_mode``. Сохраняет
    # суммарную длительность (инвариант planner'а).
    jl_cut_enabled: bool = False
    jl_cut_mode: JLCutMode = "role_change"
    jl_cut_max_offset_sec: float = Field(default=0.4, ge=0.1, le=1.0)

    # TIER2-#11: Semantic boundary chunking (смысловые границы чанков вместо
    # фиксированных окон). Эмбеддинг предложений + cosine-similarity границы.
    # +8-12% boundary F1 (Chapter-Llama CVPR 2025). Fallback на fixed-window
    # если backend недоступен.
    semantic_chunking_enabled: bool = False
    semantic_chunk_target_duration_sec: int = Field(default=600, ge=120, le=1800)
    semantic_chunk_min_duration_sec: int = Field(default=180, ge=60, le=900)
    semantic_chunk_similarity_threshold: float = Field(default=0.35, ge=0.05, le=0.8)

    # TIER2-#16: Cross-chunk coherence reducer (после reducer-а доп. проход
    # Flash Lite разрешает противоречия между chunk'ами).
    # LLM×MapReduce pattern: каждый кандидат имеет context_assumptions,
    # reducer сводит их в глобальный контекст и отфильтровывает несогласующиеся.
    cross_chunk_reducer_enabled: bool = False
    cross_chunk_reducer_strictness: Literal["soft", "strict"] = "soft"

    # FEAT-#E: Word-aware cut snapping. Прилепляет границы cut к ближайшему
    # word boundary (±snap_window_sec) через stable-ts word-timestamps.
    # Убирает click-артефакты на срезах из середины слова.
    cut_snap_enabled: bool = True
    cut_snap_window_sec: float = Field(default=0.03, ge=0.01, le=0.1)

    # T11: Pipeline mode. "automatic" → auto_config_advisor сам решает все
    # параметры ниже по audio features. "manual" → используются текущие
    # значения runtime_settings (user control). Default = manual пока T11.3
    # UI не готов; когда запустим — default станет automatic.
    pipeline_mode: PipelineMode = "manual"

    # Narrative pipeline mode (top-down refactor, 2026-04-21).
    # - "bottom_up" (legacy): extraction agents → reducer → story_doctor →
    #   composer с padding до MIN. Даёт узкое распределение длин 32-43s
    #   без закрытой narrative arc (research: docs/viral-clipper-research-
    #   2026-04-21.md).
    # - "top_down": chapter_builder → hook_detector → arc_finder →
    #   boundary_extender → cross_chapter_ranker. Длительность — следствие
    #   payoff'а, не цель padding'а. OpusClip-style.
    # Default = bottom_up до завершения Phase 7 validation. После verify
    # default станет top_down (legacy останется доступен через UI toggle).
    narrative_mode: NarrativeMode = Field(
        default="bottom_up",
        description=(
            "Архитектура сборки рилсов. "
            "bottom_up (legacy) собирает из 2-13с evidence с padding до MIN. "
            "chaptered (Phase 1-6 top-down, broken на монологах) — "
            "embedding-based chaptering + per-chapter arc_finder. "
            "map_reduce (Phase 8, OpusClip-parity) — chunks 20K chars в "
            "parallel, затем LLM reducer. Production target. "
            "viral_2026 (Phase 9, simple OpusClip-style) — один LLM call per "
            "chunk 20K знаков эмиттит готовые рилсы по 5-block структуре "
            "Hook→Context→Payoff→Re-hook→CTA + манифест Живого Кадра. ~10-15 "
            "LLM calls на 90 мин видео вместо 80-120. "
            "Default bottom_up — zero regression. Для тестов map_reduce/viral_2026."
        ),
    )

    # Phase 8 (2026-04-21) — Map-Reduce chunk-based clip extraction.
    # Research basis: docs/opusclip-2026-research.md. OpusClip density данные
    # (30мин → 12-18 clips, 3h→40-45 single pass vs 90-120 разбитое) показали
    # optimal chunking: ~20K chars с target 12-18 clips per chunk.
    # Применяется когда narrative_mode="top_down" — chunk_scorer.py.
    narrative_chunk_size_chars: int = Field(
        default=20_000,
        ge=5_000,
        le=50_000,
        description=(
            "Размер одного chunk'а транскрипта для parallel LLM scoring. "
            "20K chars ≈ 20 минут talking-head речи. Ниже — теряется контекст "
            "арки, выше — Flash Lite context rot и satisficing."
        ),
    )
    narrative_chunk_overlap_chars: int = Field(
        default=2_000,
        ge=500,
        le=5_000,
        description=(
            "Overlap между соседними chunks (в символах). Нужен чтобы ловить "
            "clips с hook/payoff на границе. Dedup по timestamps downstream."
        ),
    )
    narrative_clips_per_chunk_target: int = Field(
        default=15,
        ge=5,
        le=30,
        description=(
            "Density-prior для chunk_scorer: сколько clips LLM должен искать "
            "в одном chunk'е. Based on OpusClip 30-min density (12-18). "
            "Параметр передаётся в prompt как floor, не cap."
        ),
    )
    narrative_chunk_parallel_max: int = Field(
        default=10,
        ge=1,
        le=20,
        description=(
            "Максимум concurrent chunk LLM calls (rate limit guard). "
            "Gemini Tier 1 = 300 RPM → 10 parallel × 3 videos/min fits."
        ),
    )

    # Multi-arc variant A (2026-04-21) — per-canvas-moment arcs вместо
    # единой глобальной арки. Для каждого candidate_moment из Canvas
    # строится отдельный arc по evidence в временном окне ±window_sec.
    # Когда multi_arc_enabled=False — работает legacy single-arc flow
    # (zero regression). Fields потребляются downstream задачами M2-M7.
    multi_arc_enabled: bool = Field(
        default=False,
        description=(
            "Включает построение отдельного arc per canvas moment "
            "(variant A). Когда выключено — legacy single-arc flow."
        ),
    )
    multi_arc_window_sec: float = Field(
        default=60.0,
        ge=20.0,
        le=180.0,
        description=(
            "Полуокно в секундах вокруг центра candidate_moment для "
            "фильтрации evidence."
        ),
    )
    multi_arc_window_fallback_sec: float = Field(
        default=120.0,
        ge=30.0,
        le=300.0,
        description=(
            "Расширенное полуокно если при основном окне найдено меньше "
            "multi_arc_min_evidence_per_moment evidence."
        ),
    )
    multi_arc_min_evidence_per_moment: int = Field(
        default=5,
        ge=2,
        le=30,
        description=(
            "Минимум evidence items в окне вокруг moment чтобы строить arc. "
            "Меньше — moment пропускается."
        ),
    )

    # T10.5 — pacing_profile template (dynamic/balanced/mkbhd_clean/documentary).
    # Используется composer для scoring bias. Auto Mode выставляет его по
    # WPS × pitch_std матрице, Manual — пользователь сам выбирает через UI.
    pacing_profile: str = "balanced"

    # T10.1: Punchline pause detection via Parselmouth pitch final lowering.
    # На фразах где pitch падает >= threshold_hz_drop в последние 0.3 сек
    # сегмента — удерживаем паузу ``punchline_hold_after_sec`` перед cut'ом.
    # Компенсирует агрессивный pause_compression для драматургически
    # важных моментов.
    punchline_pause_enabled: bool = False
    punchline_pitch_drop_hz: float = Field(default=20.0, ge=5.0, le=60.0)
    punchline_hold_after_sec: float = Field(default=0.45, ge=0.1, le=1.0)

    # T10.2: Snap strategy. Parallel с T2.5 (rhythm_aware_cuts_enabled).
    # "onset" рекомендуется для talking-head, "beat" для видео с музыкой.
    # Beats (T2.5) не удалены — доступны через snap_strategy="beat" или "both".
    snap_strategy: SnapStrategy = "off"
    onset_snap_max_shift_sec: float = Field(default=0.08, ge=0.02, le=0.2)

    # T10.3: Punch-in zoom on stressed syllables.
    # 1.00x → 1.06x за ~5 кадров (167мс @ 30fps, ease-out) → hold 500мс →
    # 1.06x → 1.00x за ~10 кадров (333мс ease-in). Вероятность на emphasis-
    # moment из Parselmouth intensity peaks.
    punch_in_zoom_enabled: bool = False
    punch_in_zoom_scale: float = Field(default=1.06, ge=1.0, le=1.15)
    punch_in_zoom_probability: float = Field(default=0.3, ge=0.0, le=1.0)
    punch_in_zoom_hold_ms: int = Field(default=500, ge=200, le=1500)

    # Phase 9 (2026-04-22): Face tracker toggle. MediaPipe face detection
    # используется для face-centered base crop (fit_mode=fill). Default OFF —
    # 95% случаев не нуждаются: letterbox / manual / split+main_transform
    # работают без face-keyframes. Риск зависания на Apple Silicon M-series
    # (mediapipe GL context + asyncio.to_thread blocking). Включай только
    # когда глобальный fit_mode=fill и важна композиция по лицу спикера.
    face_tracker_enabled: bool = Field(
        default=False,
        description=(
            "MediaPipe face tracking для face-centered base crop. "
            "Default OFF. Включай только при fit_mode=fill когда важна "
            "композиция по лицу. Известный риск зависания на M-series."
        ),
    )

    # T10.7: Ken Burns drift на статичных шотах.
    # Медленный zoom 0.3% scale per second, max 1.025x за 8+ сек шота.
    # Центрирование на лице (T2.1 face tracking) если доступно.
    ken_burns_drift_enabled: bool = False
    ken_burns_scale_per_sec: float = Field(default=0.003, ge=0.001, le=0.01)
    ken_burns_max_scale: float = Field(default=1.025, ge=1.005, le=1.05)

    # Predictable reel count (floor/ceiling + Jaccard dedup post-ranking).
    # Применяется после основного ранжирования в reels_composer.compose_reels.
    # Ceiling по длительности видео: 10-15min → 15, 15-30min → 20,
    # 30-60min → 25, 60+min → 30 рилсов. Floor не раздуваем — если после
    # dedup осталось меньше target, новые рилсы не создаём.
    reel_count_enforce_floor_ceiling: bool = Field(
        default=True,
        description="Принудительно держать target count по длительности: "
        "10-15min → 10-15 reels, 15-30min → 12-20, 30-60min → 15-25, 60+min → 20-30.",
    )
    reel_count_dedup_jaccard_threshold: float = Field(
        default=0.7,
        ge=0.4,
        le=0.95,
        description="Максимальный token-overlap (Jaccard) между двумя принятыми "
        "рилсами. Больше → меньше уникальности, меньше → жёстче dedup.",
    )

    # T6.1 — Preference retrieval mode (ML на лайках).
    # cosine: top-5 семантически ближайших лайкнутых рилсов к текущему
    #   Canvas (по 256-dim Gemini embeddings). Требует embedding_json
    #   на лайкнутых артефактах (fill-in only после T6.1; для
    #   исторических лайков caller делает fallback).
    # top_by_date: legacy — топ-8 свежих лайков по дате без семантики.
    preference_retrieval_mode: Literal["cosine", "top_by_date"] = Field(
        default="cosine",
        description="cosine = семантическое retrieval по Gemini embeddings "
        "(требует сохранённые embeddings); top_by_date = legacy топ-8 по дате.",
    )

    # T8.1-T8.3 Adaptive audio editing
    mouth_sound_removal_enabled: bool = Field(
        default=False,
        description="T8.1 — снимать lip smacks/clicks в render (FFmpeg afade на зонах).",
    )
    breath_classifier_enabled: bool = Field(
        default=False,
        description="T8.2 — отличать breath от silence. Breath-зоны не сжимаются агрессивно.",
    )
    context_aware_keep_sec_enabled: bool = Field(
        default=True,
        description="T8.3 — keep_sec паузы зависит от punctuation: точка 0.25s, вопрос 0.35s, запятая 0.12s.",
    )

    # T8.4-T8.5 Smart J/L chooser + adaptive leveller
    smart_jl_chooser_enabled: bool = Field(
        default=False,
        description="T8.4 — выбор J/L-cut и offset на основе контекста "
        "(speaker change, punctuation, emotion) вместо фиксированного mode.",
    )
    adaptive_leveller_enabled: bool = Field(
        default=False,
        description="T8.5 — per-window EBU R128 gain (pyloudnorm) вместо "
        "глобального loudnorm. Ровняет тихие и громкие места ±1 LU.",
    )

    # T2.8 Screencast auto-zoom + deictic trigger layer
    screencast_cursor_zoom_enabled: bool = Field(
        default=False,
        description="T2.8 — для profile=screencast: auto-zoom по курсору с "
        "spring smoothing (damped harmonic oscillator).",
    )
    screencast_damping_profile: Literal[
        "underdamped", "critically_damped", "overdamped"
    ] = Field(
        default="critically_damped",
        description="Demo — underdamped, стандарт — critically_damped, "
        "tutorial — overdamped.",
    )
    screencast_zoom_max_factor: float = Field(
        default=2.0,
        ge=1.2,
        le=3.0,
        description="Максимальный zoom factor для курсорного auto-zoom.",
    )
    deictic_zoom_enabled: bool = Field(
        default=False,
        description="Zoom на deictic words (вот/смотри/здесь) — работает на "
        "всех профилях, не только screencast.",
    )

    @classmethod
    def from_settings(cls, settings: _SettingsLike) -> PerformanceSettings:
        """Конструирует начальные значения из env (seed)."""

        return cls(
            render_concurrency=2,
            proxy_enabled=settings.app_proxy_enabled,
            proxy_max_dim=settings.app_proxy_max_dim,
            proxy_video_crf=settings.app_proxy_video_crf,
            proxy_video_maxrate_kbps=settings.app_proxy_video_maxrate_kbps,
            proxy_audio_bitrate_kbps=settings.app_proxy_audio_bitrate_kbps,
            proxy_cache_max_gb=settings.app_proxy_cache_max_gb,
            proxy_lock_timeout_sec=settings.app_proxy_lock_timeout_sec,
            proxy_skip_height_le=settings.app_proxy_skip_height_le,
            proxy_skip_duration_lt_sec=settings.app_proxy_skip_duration_lt_sec,
            proxy_skip_bitrate_lt_kbps=settings.app_proxy_skip_bitrate_lt_kbps,
            default_use_source_for_render=False,
        )
