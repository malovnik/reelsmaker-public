"""Pydantic модели Project Canvas и CompressedChunk.

Canvas — scaffold истории. Строится Stage 5.2 (Canvas Builder, Gemini Pro),
используется всеми downstream стадиями (5.3 Extraction — 5.8 Variants)
как context для LLM. Включает central_theme, themes, motifs, speakers,
candidate_moments, tone_map, chronological_spine.

videomaker не предоставляет UI редактирования Canvas (автонарезка без
участия пользователя). Поля `status`, `custom_direction`, pinned_moments
сохранены для совместимости контракта и будущей опциональной ручной правки.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ThemeStatus = Literal["normal", "starred", "excluded"]
MomentStatus = Literal["normal", "pinned_required", "excluded"]


class CanvasTheme(BaseModel):
    id: str
    label: str
    description: str = ""
    strength: float = Field(ge=0.0, le=1.0)
    first_mention_sec: float = Field(ge=0.0)
    last_mention_sec: float = Field(ge=0.0)
    status: ThemeStatus = "normal"


class CanvasMotif(BaseModel):
    id: str
    label: str
    occurrences_sec: list[float] = Field(default_factory=list)
    significance: str = ""
    status: ThemeStatus = "normal"


class CanvasSpeaker(BaseModel):
    id: str
    role: str
    importance: float = Field(ge=0.0, le=1.0)
    key_quote_start_sec: float | None = None
    display_name: str | None = None
    included: bool = True


class CanvasCandidateMoment(BaseModel):
    id: str
    speaker: str | None = None
    start: float = Field(ge=0.0)
    end: float = Field(ge=0.0)
    one_liner: str = ""
    kind: Literal["hook", "peak", "payoff", "setup", "cutaway"] = "setup"
    strength: float = Field(ge=0.0, le=1.0)
    status: MomentStatus = "normal"
    embedding: list[float] | None = Field(default=None)
    """Semantic embedding оригинального текста фразы из транскрипта.

    Заполняется Stage 5.2.5 Canvas Embedder (gemini-embedding-001,
    truncated до 256-dim, task=SEMANTIC_SIMILARITY). Используется
    downstream: Reducer (semantic dedup), Story Doctor (retrieval),
    Reels Composer (cross-reel diversity filter).

    None при fallback (embed API недоступен) — downstream graceful-degrade.
    """


class CanvasToneRange(BaseModel):
    sec_range: tuple[float, float]
    mood: Literal[
        "setup", "nostalgic", "tense", "triumphant", "contemplative",
        "energetic", "melancholic", "anxious", "joyful", "confessional",
    ]
    intensity: float = Field(ge=0.0, le=1.0)


class CanvasEpisode(BaseModel):
    """T2.1 Hierarchical canvas — группировка moments по временной оси.

    Эпизод = «глава» видео (обычно 10-15 мин). Строится эвристически
    группировкой candidate_moments по time-bucket'ам после Canvas Builder.
    Используется downstream для drill-down:

    * Reels Composer — thematic clustering внутри эпизода (рилс остаётся
      в смысловой зоне источника, не перескакивает между главами).
    * Future: LLM-агенты при обработке длинных видео видят только episode
      context вместо full canvas → prompts короче, фокус лучше.

    Для коротких видео (< 30 мин) эпизодов может быть 1-2 — canvas
    остаётся плоским и работает как раньше.
    """

    id: str
    time_range_sec: tuple[float, float]
    theme_ids: list[str] = Field(default_factory=list)
    """theme_id'ы доминирующие в этом эпизоде."""
    moment_ids: list[str] = Field(default_factory=list)
    """id'ы candidate_moments принадлежащих эпизоду."""
    summary: str = ""
    """Короткое описание эпизода (1-2 фразы). Заполняется heuristic-builder'ом."""

    @property
    def duration_sec(self) -> float:
        return max(0.0, self.time_range_sec[1] - self.time_range_sec[0])


class ProjectCanvas(BaseModel):
    """Scaffold истории. Создаётся Stage 5.2, читается Stages 5.3-5.8."""

    central_theme: str = ""
    themes: list[CanvasTheme] = Field(default_factory=list)
    motifs: list[CanvasMotif] = Field(default_factory=list)
    speakers: list[CanvasSpeaker] = Field(default_factory=list)
    candidate_moments: list[CanvasCandidateMoment] = Field(default_factory=list)
    tone_map: list[CanvasToneRange] = Field(default_factory=list)
    chronological_spine: list[str] = Field(default_factory=list)
    episodes: list[CanvasEpisode] = Field(default_factory=list)
    """T2.1 hierarchical grouping. Пустой список для коротких видео или
    при отключённом episode-builder."""

    custom_direction: str = ""

    @property
    def starred_theme_ids(self) -> list[str]:
        return [t.id for t in self.themes if t.status == "starred"]

    @property
    def excluded_theme_ids(self) -> list[str]:
        return [t.id for t in self.themes if t.status == "excluded"]

    @property
    def excluded_speaker_ids(self) -> list[str]:
        return [s.id for s in self.speakers if not s.included]

    @property
    def pinned_moment_ids(self) -> list[str]:
        return [m.id for m in self.candidate_moments if m.status == "pinned_required"]

    def to_llm_context(self) -> str:
        """Рендерит Canvas в plaintext для инъекции в промпт агентов."""
        lines: list[str] = ["=== PROJECT CANVAS ==="]
        if self.central_theme:
            lines.append(f"Central theme: {self.central_theme}")
        if self.custom_direction:
            lines.append(f"User direction: {self.custom_direction}")

        if self.themes:
            active_themes = [t for t in self.themes if t.status != "excluded"]
            if active_themes:
                lines.append("\nThemes:")
                for t in active_themes:
                    star = "★ " if t.status == "starred" else ""
                    lines.append(
                        f"  - {star}[{t.id}] {t.label} (strength {t.strength:.2f}): {t.description}"
                    )

        if self.motifs:
            active_motifs = [m for m in self.motifs if m.status != "excluded"]
            if active_motifs:
                lines.append("\nMotifs:")
                for m in active_motifs:
                    occ = ", ".join(f"{s:.1f}s" for s in m.occurrences_sec[:5])
                    lines.append(f"  - [{m.id}] {m.label} (at {occ}): {m.significance}")

        if self.speakers:
            active_speakers = [s for s in self.speakers if s.included]
            if active_speakers:
                lines.append("\nSpeakers (included):")
                for s in active_speakers:
                    name = s.display_name or s.id
                    lines.append(
                        f"  - {s.id} ({name}, {s.role}, importance {s.importance:.2f})"
                    )

        if self.candidate_moments:
            pinned = [m for m in self.candidate_moments if m.status == "pinned_required"]
            if pinned:
                lines.append("\nPINNED moments (must be included in story):")
                for m in pinned:
                    lines.append(
                        f"  - [{m.id}] {m.kind} @ {m.start:.1f}-{m.end:.1f}s: {m.one_liner}"
                    )

        if self.chronological_spine:
            lines.append("\nChronological spine:")
            for item in self.chronological_spine:
                lines.append(f"  {item}")

        return "\n".join(lines)


class NotableQuote(BaseModel):
    quote: str
    sec: float = Field(ge=0.0)
    speaker: str | None = None


class EmotionalPeak(BaseModel):
    sec: float = Field(ge=0.0)
    kind: Literal[
        "surprise", "laughter", "confession", "anger", "triumph", "tension",
    ]
    note: str = ""


class CompressedChunk(BaseModel):
    """Выход Stage 5.1 Compression для одного chunk."""

    chunk_index: int
    time_range_sec: tuple[float, float]
    summary: str
    key_speakers: list[str] = Field(default_factory=list)
    notable_quotes: list[NotableQuote] = Field(default_factory=list)
    emotional_peaks: list[EmotionalPeak] = Field(default_factory=list)

    def to_synopsis_fragment(self) -> str:
        lines = [
            f"--- Chunk {self.chunk_index} "
            f"[{self.time_range_sec[0]:.1f}-{self.time_range_sec[1]:.1f}s] ---",
            f"Speakers: {', '.join(self.key_speakers) or 'unknown'}",
            "",
            self.summary,
        ]
        if self.notable_quotes:
            lines.append("\nKey quotes:")
            for q in self.notable_quotes:
                speaker = f" ({q.speaker})" if q.speaker else ""
                lines.append(f'  > "{q.quote}"{speaker} @ {q.sec:.1f}s')
        if self.emotional_peaks:
            lines.append("\nEmotional peaks:")
            for p in self.emotional_peaks:
                lines.append(f"  * {p.kind} @ {p.sec:.1f}s — {p.note}")
        return "\n".join(lines)
