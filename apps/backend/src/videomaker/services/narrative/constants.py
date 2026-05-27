"""Константы top-down narrative pipeline.

Research basis: docs/viral-clipper-research-2026-04-21.md

Numbers из EMNLP 2025 Industry "Human-Inspired Video Editing" + OpusClip
observational data + TikTok completion-rate telemetry.
"""

from __future__ import annotations

# ─── Reel duration bounds ────────────────────────────────────────────────
REEL_MIN_DURATION_SEC: float = 28.0
"""Минимальная длительность рилса. Ниже — теряется нарративная глубина
(research: < 28s = single-claim highlight, не narrative). Ранее 30/37s."""

REEL_TARGET_DURATION_SEC: float = 42.0
"""Целевая длительность — пик completion-rate по TikTok телеметрии.
Используется для fit-scoring в cross-chapter ranker (boost около target,
пенальти на краях). НЕ для padding — reel's длина задаётся payoff'ом."""

REEL_MAX_DURATION_SEC: float = 75.0
"""Максимальная длительность. Выше — completion-rate резко падает
(TikTok algorithm пессимизирует). Ranker режет arcs > 75s: либо
находит ранний intermediate closure, либо отклоняет."""

# ─── Boundary extension ──────────────────────────────────────────────────
MAX_CLOSURE_EXTENSION_SEC: float = 35.0
"""Сколько секунд boundary_extender может искать natural closure после
arc.clip_end_sec. Покрывает long-form anecdote payoffs ("круглый или
квадратный" case из r2 — payoff через +30s)."""

SILENCE_THRESHOLD_SEC: float = 0.8
"""Post-sentence pause ≥ 0.8s = strong boundary signal.

Research: < 0.5s = мид-мысль, 0.5-0.8s = размытая граница, > 0.8s =
speaker явно закрыл утверждение."""

DISCOURSE_MARKER_FORWARD_SEC: float = 15.0
"""Окно forward search для discourse closure markers (поэтому, таким
образом, в итоге). Regex-пасс детерминистичен, дешевле LLM."""

# ─── Chaptering ──────────────────────────────────────────────────────────
MIN_CHAPTER_DURATION_SEC: float = 60.0
"""Главы короче 60s мержатся с соседней (chapter_builder post-processing).
Слишком короткая глава = ложное topic boundary."""

MAX_CHAPTER_DURATION_SEC: float = 300.0
"""Главы длиннее 5мин режутся пополам (chapter_builder post-processing).
Топ-ранг content-aware split: ищем лучшую internal boundary через
embedding local minimum."""

CHAPTER_BUILDER_LLM_WINDOW_SEC: float = 90.0
"""Для LLM topic-shift scoring: передаём prev 90s + next 90s вокруг
candidate boundary. Source: Chapter-Llama (CVPR 2025) sliding-window."""

CHAPTER_BUILDER_SIMILARITY_THRESHOLD: float = 0.35
"""Semantic similarity threshold для candidate boundary из
semantic_chunker. Local minimum < threshold → LLM verify."""

# ─── Hook detection ──────────────────────────────────────────────────────
HOOK_MIN_DURATION_SEC: float = 2.0
HOOK_MAX_DURATION_SEC: float = 8.0
"""Research: hook < 2s = не успевает зацепить, > 8s = теряет hook-характер."""

HOOK_POSITION_WINDOW_RATIO: float = 0.4
"""Hook должен быть в первых 40% главы. Далее — это уже development.
Hook_detector пенализирует hooks позже этого window."""

# ─── Arc finding ─────────────────────────────────────────────────────────
ARC_DEVELOPMENT_MIN_SENTENCES: int = 1
ARC_DEVELOPMENT_MAX_SENTENCES: int = 5
"""Кол-во sentence'ов между hook и payoff. < 1 = skip payoff нет
развития (reject), > 5 = arc плывёт, ранний payoff лучше."""

ARC_COHERENCE_MIN: float = 0.5
"""Минимальная hook↔payoff coherence. Arcs ниже отклоняются."""

# ─── Cross-chapter ranker ────────────────────────────────────────────────
NOVELTY_COSINE_THRESHOLD: float = 0.72
"""Если cosine similarity с уже принятым рилсом > threshold → reject
(topic dup). Research: 0.7-0.75 optimal balance."""

CLOSURE_TYPE_MAX_PER_RANK: int = 2
"""Не более 2 рилсов с одинаковым closure_type в топ-N. Diversity
constraint — dashboard показывает разнообразие."""
