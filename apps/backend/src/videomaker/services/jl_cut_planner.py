"""TIER2-#15: J/L-cut planner.

Назначает audio-окна для cuts на основе эвристик, чтобы сгладить переходы:

* **L-cut**: аудио текущего cut'а продолжает играть поверх видео следующего.
  Достигается расширением ``audio_end`` текущего вперёд и задержкой
  ``audio_start`` следующего на столько же — суммарная длительность аудио
  сохраняется равной видео.
* **J-cut**: аудио следующего cut'а начинает играть до того, как переключается
  видео. ``audio_end`` текущего сокращается, а ``audio_start`` следующего
  отодвигается назад на ту же величину.

Где применяем:

* **mode="role_change"** (по умолчанию) — только на границах ролевых
  переходов (hook→development, development→peak, peak→payoff). Там L/J-cuts
  звучат наиболее естественно (классика editing: смена сцены/мысли
  сглаживается аудио-слиянием).
* **mode="all_transitions"** — между всеми соседними cuts одного рилса.

Тип (J vs L) определяется role-парой:

* hook → development: **L-cut** (hook-аудио дотягивается в development —
  как будто продолжается мысль).
* development → peak: **J-cut** (аудио peak'а уже звучит на хвосте
  development — build-up).
* peak → payoff: **L-cut** (аудио peak'а докатывается в payoff — echo).
* остальные: **L-cut** по умолчанию.

Offset ограничен ``max_offset_sec`` И безопасными границами:

* Не может превышать 20% длительности соседнего cut'а (чтоб не съесть половину).
* Не может выйти за source-bounds (``audio_start - offset >= 0``,
  ``audio_end + offset <= source_duration``).

Возвращает новый ``tuple[CutSpec, ...]`` + статистику.

Тесты не пишем (по правилу feedback_no_extra_tests для videomaker).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from videomaker.core.logging import get_logger
from videomaker.services.project_graph import CutSpec

log = get_logger(__name__)

TransitionKind = Literal["hard", "j_cut", "l_cut"]
PlannerMode = Literal["role_change", "all_transitions"]


@dataclass(frozen=True)
class JLCutStats:
    """Статистика по одному прогону planner'а."""

    transitions_total: int
    j_cuts_applied: int
    l_cuts_applied: int
    skipped_no_room: int
    """Переходы, где offset урезали до нуля из-за границ (<5ms)."""

    @property
    def any_applied(self) -> bool:
        return self.j_cuts_applied + self.l_cuts_applied > 0


def plan_jl_cuts(
    cuts: list[CutSpec],
    *,
    segment_roles: list[str] | None = None,
    source_duration_sec: float | None = None,
    max_offset_sec: float = 0.4,
    mode: PlannerMode = "role_change",
    min_offset_sec: float = 0.08,
) -> tuple[list[CutSpec], JLCutStats]:
    """Применяет J/L-cuts к списку cuts.

    Args:
        cuts: текущие cuts рилса (сохраняются видеограницы; меняются audio-границы).
        segment_roles: роли ("hook" / "development" / "peak" / "payoff") длиной ==
            len(cuts). None → все "development" (mode "all_transitions" всё равно
            сработает).
        source_duration_sec: длительность source-видео в секундах (ограничивает
            экстраполяцию audio-окна назад/вперёд). None → не ограничиваем
            (риск выйти за bounds, но ffmpeg сам обрежет).
        max_offset_sec: максимальное смещение (сек) для одного перехода.
        mode: "role_change" (только на ролевых границах) или "all_transitions".
        min_offset_sec: минимальная длительность, ниже которой эффект не виден.

    Returns:
        (new_cuts, stats). new_cuts имеют обновлённые ``audio_source_*``.
    """

    if len(cuts) < 2 or max_offset_sec <= 0:
        return cuts, JLCutStats(0, 0, 0, 0)

    # Работаем над копией: audio поля держим как мутируемые floats (не None
    # здесь — в финале приведём к None, если совпадает с видео).
    audio_starts = [c.audio_start_sec for c in cuts]
    audio_ends = [c.audio_end_sec for c in cuts]

    j_count = 0
    l_count = 0
    skipped = 0
    transitions = 0

    for i in range(len(cuts) - 1):
        cur = cuts[i]
        nxt = cuts[i + 1]

        cur_role = (segment_roles or [""] * len(cuts))[i]
        nxt_role = (segment_roles or [""] * len(cuts))[i + 1]

        kind = _decide_transition_kind(cur_role, nxt_role, mode=mode)
        if kind == "hard":
            continue
        transitions += 1

        # Безопасный offset = min(max, 20% длительности соседа, bounds)
        cap_cur = cur.duration_sec * 0.2
        cap_nxt = nxt.duration_sec * 0.2
        offset = min(max_offset_sec, cap_cur, cap_nxt)

        if kind == "l_cut":
            # cur audio extends forward; nxt audio starts later
            # cur.audio_end += offset — но не за source_duration
            headroom_cur = (
                (source_duration_sec - audio_ends[i])
                if source_duration_sec is not None
                else offset
            )
            # nxt.audio_start += offset — но не за audio_end[i+1]
            headroom_nxt = audio_ends[i + 1] - audio_starts[i + 1] - 0.1
            offset = min(offset, max(0.0, headroom_cur), max(0.0, headroom_nxt))
        elif kind == "j_cut":
            # nxt audio begins earlier; cur audio ends earlier
            # nxt.audio_start -= offset — но не ниже нуля
            headroom_nxt = audio_starts[i + 1]
            # cur.audio_end -= offset — не меньше cur.audio_start + 0.1
            headroom_cur = audio_ends[i] - audio_starts[i] - 0.1
            offset = min(offset, max(0.0, headroom_nxt), max(0.0, headroom_cur))

        if offset < min_offset_sec:
            skipped += 1
            continue

        if kind == "l_cut":
            audio_ends[i] = audio_ends[i] + offset
            audio_starts[i + 1] = audio_starts[i + 1] + offset
            l_count += 1
        else:  # j_cut
            audio_ends[i] = audio_ends[i] - offset
            audio_starts[i + 1] = audio_starts[i + 1] - offset
            j_count += 1

    new_cuts: list[CutSpec] = []
    for i, c in enumerate(cuts):
        a_s = audio_starts[i]
        a_e = audio_ends[i]
        if abs(a_s - c.source_start_sec) < 1e-4 and abs(a_e - c.source_end_sec) < 1e-4:
            new_cuts.append(c)
            continue
        new_cuts.append(
            CutSpec(
                source_start_sec=c.source_start_sec,
                source_end_sec=c.source_end_sec,
                audio_source_start_sec=round(a_s, 3),
                audio_source_end_sec=round(a_e, 3),
            )
        )

    stats = JLCutStats(
        transitions_total=transitions,
        j_cuts_applied=j_count,
        l_cuts_applied=l_count,
        skipped_no_room=skipped,
    )
    return new_cuts, stats


def _decide_transition_kind(
    cur_role: str, nxt_role: str, *, mode: PlannerMode
) -> TransitionKind:
    """Определяет тип перехода на границе cur→nxt."""

    if mode == "all_transitions":
        # Лёгкий bias на L-cut — он обычно звучит естественнее.
        return "l_cut"

    # mode == "role_change": только на явных сменах роли
    if cur_role == nxt_role or not cur_role or not nxt_role:
        return "hard"

    pair = (cur_role, nxt_role)
    l_cut_pairs = {
        ("hook", "development"),
        ("peak", "payoff"),
        ("development", "payoff"),
    }
    j_cut_pairs = {
        ("development", "peak"),
        ("hook", "peak"),
    }
    if pair in l_cut_pairs:
        return "l_cut"
    if pair in j_cut_pairs:
        return "j_cut"
    # Смена роли, но не из списка → мягкий L-cut
    return "l_cut"



def choose_jl_offset(
    prev_word: str | None,
    next_word: str | None,
    *,
    is_role_change: bool,
    emotion_level: float | None = None,
) -> tuple[TransitionKind, float]:
    """T8.4 — context-aware выбор transition type + offset.

    Эвристика по research editing-craft-2026.md:

    * **change_of_speaker / role change** → J-cut 0.25-0.35s (28% всех cuts
      профессионалов сидят на смене говорящего).
    * **rhetorical question** (предыдущее слово кончается на "?") → L-cut
      0.20-0.30s — аудио вопроса докатывается в реакцию.
    * **topic shift** (слово-маркер "теперь" / "итак" / "дальше") → J-cut
      0.30-0.45s.
    * **emotional peak** (``emotion_level`` >= 0.7) → L-cut 0.25-0.40s
      (19% acc-к эмоциональных стыков).
    * **sentence end** (prev заканчивается на ".") → hard cut 0.05-0.10s.
    * **default** → hard cut с минимальным offset.

    Args:
        prev_word: последнее слово cur-сегмента (с пунктуацией).
        next_word: первое слово nxt-сегмента.
        is_role_change: True если Kartoziya-роли cur/nxt разные.
        emotion_level: 0.0-1.0 уровень эмоциональности cur-сегмента
            (опционально, из audio_analyzer / opensmile).

    Returns:
        (kind, offset_sec) — готов к передаче в planner как target offset.
    """

    prev = (prev_word or "").strip().lower()
    nxt = (next_word or "").strip().lower()

    topic_markers = {
        "теперь",
        "итак",
        "дальше",
        "кстати",
        "однако",
        "короче",
        "значит",
    }

    if is_role_change:
        return "j_cut", 0.30

    if prev.endswith("?"):
        return "l_cut", 0.25

    if nxt in topic_markers or any(nxt.startswith(m + " ") for m in topic_markers):
        return "j_cut", 0.35

    if emotion_level is not None and emotion_level >= 0.7:
        return "l_cut", 0.30

    if prev.endswith("."):
        return "hard", 0.08

    return "hard", 0.05
