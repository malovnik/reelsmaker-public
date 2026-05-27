"""T10.9 — Cross-Context Risk Score для thematic composer.

Оценивает риск что рилс собран из далёких/несоответствующих контексту
сегментов — становится «как телевизионщик вырезал из контекста».

Три independent signal:
1. Semantic similarity < threshold — соседние сегменты тематически далёкие
2. Temporal gap > threshold — сегменты из разных частей оригинала (>5 мин)
3. Sentiment shift — один speaker меняет эмоциональный тон резко

Возвращает CrossContextRisk dataclass с score 0..1 и human-readable
reasons для UI warning badge. Рилс с score > 0.5 помечается badge'ом
«Cross-context detected».

Это НЕ hard block — composer balanced mode использует этот score как
penalty в ranking (а не exclude). Пользователь видит результат, может
переизбрать.

Интерфейс:
    from videomaker.services.cross_context_risk import assess_cross_context_risk
    risk = assess_cross_context_risk(
        segments=[SegmentRiskInput(...), ...],
    )
    # → CrossContextRisk(score, reasons, signals)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from videomaker.core.logging import get_logger

log = get_logger(__name__)


#: Пороги риска (research editing-craft-2026.md §3.2):
_SEMANTIC_SIMILARITY_MIN = 0.4  # ниже → context manipulation risk
_TEMPORAL_GAP_RISK_SEC = 300.0  # >5 мин → требует проверки
_SENTIMENT_SHIFT_THRESHOLD = 0.5  # delta sentiment → risk


@dataclass(slots=True, frozen=True)
class SegmentRiskInput:
    """Данные для оценки одного сегмента рилса."""

    source_start_sec: float
    """Где сегмент был в оригинальном видео."""

    source_end_sec: float

    embedding: list[float] | None
    """Gemini embedding (256-dim) или None если недоступен."""

    sentiment_score: float | None
    """-1..1 (отрицательный/положительный), None если не размечен."""

    text_preview: str
    """Первые ~100 символов текста сегмента (для debug reasons)."""


@dataclass(slots=True, frozen=True)
class RiskSignal:
    """Один сигнал риска из трёх."""

    name: str
    score: float  # 0..1
    reason: str


@dataclass(slots=True, frozen=True)
class CrossContextRisk:
    """Aggregated risk score для всего рилса."""

    score: float
    """Overall 0..1 — max из всех signals."""

    reasons: list[str] = field(default_factory=list)
    """Human-readable reasons для UI badge."""

    signals: list[RiskSignal] = field(default_factory=list)
    """Detailed signals для debug."""


def assess_cross_context_risk(
    segments: list[SegmentRiskInput],
) -> CrossContextRisk:
    """Оценивает риск для рилса из N сегментов.

    Для рилсов из 1 сегмента — всегда score 0.0 (cross-context невозможен).
    """
    if len(segments) < 2:
        return CrossContextRisk(score=0.0)

    signals: list[RiskSignal] = []
    reasons: list[str] = []

    # Signal 1: Semantic similarity между соседними сегментами
    sim_signal = _assess_semantic_similarity(segments)
    if sim_signal is not None:
        signals.append(sim_signal)
        if sim_signal.score > 0.3:
            reasons.append(sim_signal.reason)

    # Signal 2: Temporal gap в оригинале
    gap_signal = _assess_temporal_gap(segments)
    if gap_signal is not None:
        signals.append(gap_signal)
        if gap_signal.score > 0.3:
            reasons.append(gap_signal.reason)

    # Signal 3: Sentiment shift
    sent_signal = _assess_sentiment_shift(segments)
    if sent_signal is not None:
        signals.append(sent_signal)
        if sent_signal.score > 0.3:
            reasons.append(sent_signal.reason)

    # Overall = max (пессимистичная оценка — один сильный сигнал = риск)
    overall = max((s.score for s in signals), default=0.0)

    log.info(
        "cross_context_risk_assessed",
        segments=len(segments),
        score=round(overall, 3),
        signals_count=len(signals),
    )

    return CrossContextRisk(
        score=round(overall, 3),
        reasons=reasons,
        signals=signals,
    )


def _assess_semantic_similarity(
    segments: list[SegmentRiskInput],
) -> RiskSignal | None:
    pairs_with_embed = [
        (segments[i].embedding, segments[i + 1].embedding)
        for i in range(len(segments) - 1)
        if segments[i].embedding and segments[i + 1].embedding
    ]
    if not pairs_with_embed:
        return None

    min_sim = 1.0
    for a, b in pairs_with_embed:
        assert a is not None and b is not None
        sim = _cosine_similarity(a, b)
        if sim < min_sim:
            min_sim = sim

    if min_sim >= _SEMANTIC_SIMILARITY_MIN:
        return RiskSignal(
            name="semantic_similarity",
            score=0.0,
            reason=f"semantic similarity OK (min {min_sim:.2f})",
        )

    # Mapping: sim 0.0 → risk 1.0, sim 0.4 → risk 0.0
    risk = (
        (_SEMANTIC_SIMILARITY_MIN - min_sim) / _SEMANTIC_SIMILARITY_MIN
    )
    return RiskSignal(
        name="semantic_similarity",
        score=round(min(1.0, risk), 3),
        reason=f"сегменты тематически далёкие (min similarity {min_sim:.2f})",
    )


def _assess_temporal_gap(
    segments: list[SegmentRiskInput],
) -> RiskSignal | None:
    max_gap = 0.0
    for i in range(len(segments) - 1):
        # Прыжок = расстояние между КОНЦОМ segment[i] и НАЧАЛОМ segment[i+1]
        gap = abs(segments[i + 1].source_start_sec - segments[i].source_end_sec)
        if gap > max_gap:
            max_gap = gap

    if max_gap <= _TEMPORAL_GAP_RISK_SEC:
        return RiskSignal(
            name="temporal_gap",
            score=0.0,
            reason=f"temporal gap OK (max {max_gap:.0f} sec)",
        )

    # Mapping: gap 300 → 0.0, gap 900 → 1.0 (saturates at 15 min)
    risk = min(1.0, (max_gap - _TEMPORAL_GAP_RISK_SEC) / 600.0)
    return RiskSignal(
        name="temporal_gap",
        score=round(risk, 3),
        reason=f"сегменты из разных частей видео (прыжок {max_gap / 60:.1f} мин)",
    )


def _assess_sentiment_shift(
    segments: list[SegmentRiskInput],
) -> RiskSignal | None:
    sentiments = [
        s.sentiment_score for s in segments if s.sentiment_score is not None
    ]
    if len(sentiments) < 2:
        return None

    max_shift = 0.0
    for i in range(len(sentiments) - 1):
        delta = abs(sentiments[i + 1] - sentiments[i])
        if delta > max_shift:
            max_shift = delta

    if max_shift <= _SENTIMENT_SHIFT_THRESHOLD:
        return RiskSignal(
            name="sentiment_shift",
            score=0.0,
            reason=f"sentiment shift OK (max {max_shift:.2f})",
        )

    risk = min(1.0, (max_shift - _SENTIMENT_SHIFT_THRESHOLD) / 0.8)
    return RiskSignal(
        name="sentiment_shift",
        score=round(risk, 3),
        reason=f"резкая смена тона speaker'а (delta {max_shift:.2f})",
    )


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


__all__ = [
    "CrossContextRisk",
    "RiskSignal",
    "SegmentRiskInput",
    "assess_cross_context_risk",
]
