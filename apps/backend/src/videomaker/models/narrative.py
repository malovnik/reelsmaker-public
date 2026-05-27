"""Pydantic модели top-down narrative pipeline.

Top-down архитектура (OpusClip-style, research 2026-04-21):
    Chaptering → Hook Detection (per chapter) → Narrative Arc Finder →
    Boundary Extension → Cross-Chapter Ranker → ReelCandidate.

Принципиальное отличие от legacy bottom-up pipeline: мы не собираем рилс
из 2-13с evidence-фрагментов с padding'ом до MIN, а находим естественную
главу и внутри неё — hook + body + payoff как единый нарратив. Длительность
рилса — следствие закрытия нарратива, не target, к которому тянем.

Модели используются `services/narrative/*` и интегрируются в
`pipeline_stages/analysis.py` через feature flag ``narrative_mode``.

Research basis: docs/viral-clipper-research-2026-04-21.md
    Chapter-Llama (CVPR 2025), ARC-Chapter (Tencent 2025), TreeSeg (2024),
    EMNLP 2025 Industry "Human-Inspired Video Editing".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ClosureType = Literal[
    "conclusion",  # явный вывод / резюме ("и вот почему...", "в итоге...")
    "punchline",   # шутка / pun / иронический финал
    "revelation",  # неожиданное открытие / твист
    "callback",   # возврат к hook'у, smart symmetry
    "question",   # открытый вопрос, вовлекающий финал
    "emotional",  # эмоциональный пик как closure
]
"""Тип нарративного закрытия рилса.

Используется arc_finder для классификации payoff'а. Cross-chapter ranker
применяет diversity constraint: не более 2 рилсов с одинаковым closure_type
в топ-N, чтобы dashboard показывал разнообразие.
"""

NarrativeMode = Literal["bottom_up", "top_down"]
"""Режим pipeline.

- ``bottom_up`` — legacy: 6 extraction agents → reducer → story_doctor →
  composer. Собирает рилс из evidence-фрагментов через padding.
- ``top_down`` — новая архитектура: chapter_builder → per-chapter hook/arc
  → natural-length reel. Default после Phase 7 validation.
"""


class Chapter(BaseModel):
    """Естественная тематическая глава в транскрипте.

    Построена `chapter_builder` из semantic similarities + LLM topic-shift
    scoring. Минимальная длительность 60s (MIN_CHAPTER_DURATION_SEC),
    максимальная 300s (MAX_CHAPTER_DURATION_SEC).

    `key_claims` — 2-5 bullet-point утверждений главы, используются как
    context для hook_detector и arc_finder (экономит токены: не передаём
    полный текст главы повторно).
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    """Стабильный id главы: ``ch_001``, ``ch_002``, ... По порядку в видео."""

    start_sec: float = Field(ge=0.0)
    end_sec: float = Field(gt=0.0)

    topic_label: str = Field(min_length=1, max_length=120)
    """Короткий тематический ярлык: ``Теория относительности времени``."""

    key_claims: list[str] = Field(default_factory=list, max_length=5)
    """2-5 ключевых утверждений главы (для hook/arc context)."""

    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    """Confidence топик-boundary'а от LLM. Ниже 0.5 — слабая глава."""

    source: Literal["semantic", "llm", "hybrid", "fallback"] = "hybrid"
    """Как получена глава.

    - ``semantic`` — только embedding-based (cold LLM).
    - ``llm`` — только LLM topic-shift scoring.
    - ``hybrid`` — semantic candidates + LLM verify (основной путь).
    - ``fallback`` — транскрипт разбит fixed-window (deg. case).
    """

    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


class HookCandidate(BaseModel):
    """Кандидат на hook (2-8с стоппер скролла) внутри главы.

    Hook_detector возвращает top-3 hook'ов на главу. Cross-chapter ranker
    выбирает 1 лучший (по score × novelty с уже принятыми рилсами).
    """

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    hook_start_sec: float = Field(ge=0.0)
    hook_end_sec: float = Field(gt=0.0)

    text: str = Field(min_length=1)
    """Транскрипт hook'а (слова из этого слайса)."""

    score: float = Field(ge=0.0, le=1.0)
    """Hook strength 0..1 от LLM.

    Критерии оценки (см. prompt):
    - контр-интуитивность / провокация
    - bold claim / разрыв ожиданий
    - эмоциональный триггер
    - вопрос, который требует ответа
    """

    why: str = Field(default="", max_length=300)
    """Почему это hook (LLM reasoning, дебаг-поле)."""

    hook_kind: Literal[
        "question", "bold_claim", "counter_intuitive",
        "emotional_trigger", "pattern_break", "stat_shock",
    ] = "bold_claim"
    """Тип hook'а для diversity constraint в ranker."""

    def duration_sec(self) -> float:
        return self.hook_end_sec - self.hook_start_sec


class NarrativeArc(BaseModel):
    """Полная narrative arc внутри главы: hook → development → payoff.

    Arc_finder принимает Chapter + HookCandidate → возвращает NarrativeArc.
    Длительность определяется payoff'ом (не target'ом!): arc может быть
    30-75s в зависимости от того, где в главе закрывается нарратив.

    `clip_end_sec` = точка payoff'а, после которой mental-model зрителя
    закрывается. Не padding, не target — реальная точка закрытия.
    """

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    hook: HookCandidate

    clip_start_sec: float = Field(ge=0.0)
    """Начало рилса (обычно = hook_start_sec, иногда на 1-2с раньше для breath)."""

    clip_end_sec: float = Field(gt=0.0)
    """Payoff — точка закрытия нарратива."""

    closure_type: ClosureType
    """Тип closure'а для diversity constraint и UI label."""

    development_sentences: list[str] = Field(default_factory=list)
    """Sentences из development-части (1-3 штуки). Для observability
    и валидации — узнать можно ли доверять arc'у (если < 1, arc слишком
    короткий, revert to chapter fallback)."""

    payoff_text: str = ""
    """Текст payoff-момента (для dashboard и coherence validator)."""

    coherence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    """Hook↔payoff coherence. < 0.5 → arc непоследовательный, reject."""

    arc_score: float = Field(default=0.0, ge=0.0, le=1.0)
    """Overall quality от arc_finder: hook × coherence × payoff strength."""

    def duration_sec(self) -> float:
        return self.clip_end_sec - self.clip_start_sec


class ExtendedArc(BaseModel):
    """Arc после boundary_extender: границы прилеплены к natural boundaries.

    Boundary_extender применяет:
    1. Tail trim до sentence end (нет mid-sentence cuts).
    2. Silence boundary extension (post-sentence pause > 0.8s).
    3. Discourse marker regex fallback (CLOSURE_MARKERS).

    Никаких LLM calls — детерминистично, дешёво, быстро.
    """

    model_config = ConfigDict(extra="forbid")

    arc: NarrativeArc

    adjusted_start_sec: float = Field(ge=0.0)
    """Final start после boundary snap. Может быть arc.clip_start_sec ± 2s."""

    adjusted_end_sec: float = Field(gt=0.0)
    """Final end после boundary snap. Может быть arc.clip_end_sec + 0..35s."""

    applied_adjustments: list[str] = Field(default_factory=list)
    """Log применённых правок: ["tail_trim_sentence", "extend_silence",
    "extend_closure_marker"]. Используется для observability."""

    def duration_sec(self) -> float:
        return self.adjusted_end_sec - self.adjusted_start_sec


class ReelCandidate(BaseModel):
    """Финальный кандидат на рилс после cross-chapter ranking.

    Совместим по контракту с existing `reel_plan.py` — render stage не
    меняется. Композер в top_down режиме превращает ReelCandidate 1-в-1
    в render task без padding logic.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    """Стабильный id: ``reel_001``, ``reel_002``, ..."""

    source_arc: ExtendedArc

    rank: int = Field(ge=1)
    """Позиция в топе (1 = best). Используется UI для сортировки."""

    final_score: float = Field(ge=0.0, le=1.0)
    """Composite score: hook × arc × novelty_penalty."""

    novelty_score: float = Field(ge=0.0, le=1.0)
    """1 - max(cosine с уже принятыми). 1.0 = полностью уникальный."""

    selection_reason: str = Field(default="", max_length=200)
    """Почему выбран (для observability и debug): ``high hook + unique
    topic`` / ``fallback — chapter without strong alternative``."""
