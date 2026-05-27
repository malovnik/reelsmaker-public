"""T1.2 slice 2 — Extraction Coverage Summary (детерминистический reducer).

Строит сводку evidence волны 1 (reaction-extractors: hook/emotion/humor)
для инъекции в промпты волны 2 (meaning-extractors: irony/thesis/motif).

Цель: волна 2 видит какие чанки уже насыщены находками, где волна 1
пробежала впустую, и какие текстовые фрагменты уже захвачены.
Получив эту карту, волна 2 концентрируется на непокрытом материале
(gaps) и ищет meaning-слой в уже найденных эмоциональных пиках,
вместо того чтобы переоткрывать то же через parallel-поиск.

ТРИЗ «использовать уже имеющийся ресурс»: summary строится БЕЗ LLM —
чистый python-агрегатор по EvidenceItem'ам. 0 API-calls, O(N) по
wave1 evidence, детерминистичен и проверяем тестами.

Если структура evidence волны 1 меняется, reducer-логика легко
расширяется (добавить новую секцию в summary). Поверх можно построить
LLM-reducer в будущем slice'е, не меняя downstream контракт —
волна 2 потребляет только текстовый summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import EvidenceItem
from videomaker.services.agents.base import AgentResult
from videomaker.services.chunker import TranscriptChunk


@dataclass(slots=True)
class _ChunkCoverage:
    """Покрытие одного chunk'а evidence волны 1."""

    chunk_index: int
    start_sec: float
    end_sec: float
    hook_count: int = 0
    emotion_count: int = 0
    humor_count: int = 0
    top_fragments: list[str] = field(default_factory=list)
    """Самые сильные 1-2 фрагмента text (strength ≥ 0.6), max 120 chars."""

    @property
    def total_count(self) -> int:
        return self.hook_count + self.emotion_count + self.humor_count

    @property
    def is_gap(self) -> bool:
        """True если wave 1 ничего не нашла в этом chunk'е."""
        return self.total_count == 0


@dataclass(slots=True)
class CoverageSummary:
    """Агрегированный результат волны 1 для инъекции в wave 2 промпты."""

    per_chunk: list[_ChunkCoverage] = field(default_factory=list)
    dominant_themes: list[str] = field(default_factory=list)
    """theme_id'ы, встретившиеся в ≥ 3 evidence волны 1 (сильные
    тематические линии — волна 2 знает что они уже покрыты)."""
    gap_chunk_indices: list[int] = field(default_factory=list)
    """Индексы чанков где wave 1 не нашла ничего. Приоритетное внимание
    волны 2 — возможно там meaning-слой (irony, подспудный тезис, мотив)
    без поверхностной эмоциональной зацепки."""
    total_wave1_evidence: int = 0

    def to_prompt_text(self, *, max_chunks_listed: int = 20) -> str:
        """Рендерит summary в plaintext для user-payload волны 2.

        ``max_chunks_listed`` — ограничение per-chunk секции чтобы длинные
        видео (100+ chunks) не раздули промпт. Берём top-по-активности
        chunks + все gap'ы (они информативны сами по себе коротким
        списком индексов).
        """
        lines: list[str] = [
            "=== COVERAGE OT WAVE 1 (reaction-extractors) ===",
            f"Всего находок волны 1: {self.total_wave1_evidence}",
        ]

        if self.dominant_themes:
            lines.append(
                "Доминирующие темы (волна 1 их уже накрыла): "
                + ", ".join(self.dominant_themes[:8])
            )

        if self.gap_chunk_indices:
            lines.append(
                "Пустые chunks (wave 1 ничего не нашла — возможная зона для "
                "meaning-слоя): "
                + ", ".join(str(i) for i in self.gap_chunk_indices[:30])
            )

        active_chunks = sorted(
            [c for c in self.per_chunk if c.total_count > 0],
            key=lambda c: c.total_count,
            reverse=True,
        )[:max_chunks_listed]

        if active_chunks:
            lines.append("")
            lines.append("Активные chunks (что уже взято волной 1):")
            for cov in active_chunks:
                parts: list[str] = []
                if cov.hook_count:
                    parts.append(f"hooks×{cov.hook_count}")
                if cov.emotion_count:
                    parts.append(f"emotions×{cov.emotion_count}")
                if cov.humor_count:
                    parts.append(f"humor×{cov.humor_count}")
                head = (
                    f"  chunk {cov.chunk_index} "
                    f"({cov.start_sec:.0f}–{cov.end_sec:.0f}s): "
                    + ", ".join(parts)
                )
                lines.append(head)
                for frag in cov.top_fragments[:2]:
                    lines.append(f"    > {frag}")

        lines.append("")
        lines.append(
            "ЗАДАЧА ДЛЯ ВОЛНЫ 2: не дублируй находки волны 1. "
            "Фокус — meaning-слой (irony / тезис / motif) в "
            "gap-chunks + deep interpretation уже активных фрагментов "
            "(ищи drama под поверхностной эмоцией)."
        )
        return "\n".join(lines)


def build_coverage_summary(
    wave1_results: list[AgentResult],
    chunks: list[TranscriptChunk],
    canvas: ProjectCanvas,
    *,
    strong_evidence_threshold: float = 0.6,
    dominant_theme_min_count: int = 3,
    max_fragments_per_chunk: int = 2,
    max_fragment_chars: int = 120,
) -> CoverageSummary:
    """Строит CoverageSummary без LLM-вызовов.

    ``canvas`` параметр пока используется только для валидации theme_id
    (dominant_themes можно сверять с canvas.themes при желании), но в
    MVP-реализации не требуется. Оставлен для API-расширения в следующих
    slices (LLM reducer может получать canvas для семантической группировки).
    """
    del canvas  # reserved для LLM reducer (будущий slice)

    chunks_by_index: dict[int, TranscriptChunk] = {c.index: c for c in chunks}
    coverage_by_chunk: dict[int, _ChunkCoverage] = {
        c.index: _ChunkCoverage(
            chunk_index=c.index,
            start_sec=c.start_sec,
            end_sec=c.end_sec,
        )
        for c in chunks
    }

    theme_hits: dict[str, int] = {}
    total_evidence = 0

    for result in wave1_results:
        if result.failure_reason:
            continue
        for ev in result.evidence:
            total_evidence += 1
            cov = coverage_by_chunk.get(ev.chunk_index)
            if cov is None:
                continue
            agent = ev.source_agent
            if agent == "hook_hunter":
                cov.hook_count += 1
            elif agent == "emotional_peak_finder":
                cov.emotion_count += 1
            elif agent == "humor_specialist":
                cov.humor_count += 1

            if ev.theme_id:
                theme_hits[ev.theme_id] = theme_hits.get(ev.theme_id, 0) + 1

            if (
                ev.strength >= strong_evidence_threshold
                and len(cov.top_fragments) < max_fragments_per_chunk
            ):
                fragment = _format_fragment(ev, max_fragment_chars)
                if fragment:
                    cov.top_fragments.append(fragment)

    # Сортировка per_chunk по index для детерминированного вывода.
    per_chunk = [coverage_by_chunk[i] for i in sorted(coverage_by_chunk.keys())]

    dominant_themes = [
        theme_id
        for theme_id, count in sorted(
            theme_hits.items(), key=lambda x: x[1], reverse=True
        )
        if count >= dominant_theme_min_count
    ]

    gap_indices = [
        c.chunk_index
        for c in per_chunk
        if c.is_gap and c.chunk_index in chunks_by_index
    ]

    return CoverageSummary(
        per_chunk=per_chunk,
        dominant_themes=dominant_themes,
        gap_chunk_indices=gap_indices,
        total_wave1_evidence=total_evidence,
    )


def _format_fragment(ev: EvidenceItem, max_chars: int) -> str:
    """Готовит одну строку для top_fragments: агент + trimmed text."""
    text = (ev.text or "").strip()
    if not text:
        return ""
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    agent_tag = ev.source_agent.replace("_", "-")
    return f"[{agent_tag}] {text}"


__all__ = [
    "CoverageSummary",
    "build_coverage_summary",
]
