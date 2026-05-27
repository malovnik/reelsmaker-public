"""Unit-тесты reels_composer — NEW-сервис.

Покрывает target_count по длительности, split arc на мини-истории,
Jaccard-uniqueness фильтр, обработку edge cases (empty ranked/variants).
"""

from __future__ import annotations

import pytest

from videomaker.models.canvas import ProjectCanvas
from videomaker.models.evidence import RankedEvidence, RankedEvidenceItem
from videomaker.models.story_script import (
    StoryScript,
    StorySegment,
    StoryVariant,
    StoryVariants,
)
from videomaker.services.reels_composer import (
    REEL_MAX_DURATION_SEC,
    REEL_MIN_DURATION_SEC,
    UNIQUENESS_JACCARD_THRESHOLD,
    USER_TARGET_REEL_COUNT_MAX,
    USER_TARGET_REEL_COUNT_MIN,
    _Candidate,
    _compute_target_range,
    _greedy_uniqueness_filter,
    _jaccard,
    _merge_short_groups,
    _normalize_segment_bounds,
    _pull_closure_from_arc,
    _safe_reel_id,
    _split_arc_into_shorts,
    _tokenize,
    compose_reels,
)

# ---------------------------------------------------------------------------
# _compute_target_range
# ---------------------------------------------------------------------------


def test_target_range_short_video_floor_3() -> None:
    # 5 мин → blocks=0.25, target=round(3)=3, tolerance=3 → (3, 1, 6).
    target, lo, hi = _compute_target_range(5 * 60)
    assert (target, lo, hi) == (3, 1, 6)


def test_target_range_10min_video() -> None:
    # 10 мин → blocks=0.5, target=6, tolerance=3 → (6, 3, 9).
    target, lo, hi = _compute_target_range(10 * 60)
    assert (target, lo, hi) == (6, 3, 9)


def test_target_range_20min_video() -> None:
    # 20 мин → blocks=1, target=12, tolerance=3 → (12, 9, 15).
    target, lo, hi = _compute_target_range(20 * 60)
    assert (target, lo, hi) == (12, 9, 15)


def test_target_range_40min_video() -> None:
    # 40 мин → blocks=2, target=24, tolerance=6 → (24, 18, 30).
    target, lo, hi = _compute_target_range(40 * 60)
    assert (target, lo, hi) == (24, 18, 30)


def test_target_range_60min_video() -> None:
    # 60 мин → blocks=3, target=36, tolerance=9 → (36, 27, 45).
    target, lo, hi = _compute_target_range(60 * 60)
    assert (target, lo, hi) == (36, 27, 45)


def test_target_range_120min_video() -> None:
    # 120 мин → blocks=6, target=72, tolerance=18 → (72, 54, 90).
    target, lo, hi = _compute_target_range(120 * 60)
    assert (target, lo, hi) == (72, 54, 90)


def test_target_range_5hours_video() -> None:
    # 300 мин (5 ч) → blocks=15, target=180, tolerance=45 → (180, 135, 225).
    target, lo, hi = _compute_target_range(300 * 60)
    assert (target, lo, hi) == (180, 135, 225)


def test_target_range_zero_duration_floor() -> None:
    # Edge case: 0 сек → target floor 3, tolerance floor 3 → (3, 1, 6).
    target, lo, hi = _compute_target_range(0.0)
    assert (target, lo, hi) == (3, 1, 6)


# ---------------------------------------------------------------------------
# _tokenize / _jaccard
# ---------------------------------------------------------------------------


def test_tokenize_lowercase_and_removes_short() -> None:
    tokens = _tokenize("А ты знаешь BIG секрет?")
    assert "знаешь" in tokens
    assert "big" in tokens
    assert "секрет" in tokens
    assert "ты" not in tokens  # < 3 символов


def test_jaccard_identical() -> None:
    s = {"a", "b", "c"}
    assert _jaccard(s, s) == 1.0


def test_jaccard_empty() -> None:
    assert _jaccard(set(), {"a"}) == 0.0


def test_jaccard_partial() -> None:
    a = {"hello", "world", "abc"}
    b = {"hello", "world", "xyz"}
    # ∩=2, ∪=4 → 0.5
    assert _jaccard(a, b) == 0.5


# ---------------------------------------------------------------------------
# _safe_reel_id
# ---------------------------------------------------------------------------


def test_safe_reel_id_preserves_valid() -> None:
    assert _safe_reel_id("r1") == "r1"


def test_safe_reel_id_sanitises() -> None:
    # "package — 123!" = 7(package) + 3(space,em-dash,space) + 3(123) + 1(!)
    assert _safe_reel_id("package — 123!") == "package---123-"


def test_safe_reel_id_truncates() -> None:
    long_id = "a" * 100
    assert len(_safe_reel_id(long_id)) == 32


# ---------------------------------------------------------------------------
# _split_arc_into_shorts
# ---------------------------------------------------------------------------


def _seg(role: str, start: float, end: float, ev: str = "e") -> StorySegment:
    return StorySegment(
        role=role,  # type: ignore[arg-type]
        evidence_id=ev,
        source_start_sec=start,
        source_end_sec=end,
    )


def test_split_arc_empty_returns_empty() -> None:
    assert _split_arc_into_shorts([]) == []


def test_split_arc_single_group_no_hooks() -> None:
    arc = [
        _seg("hook", 0, 10),
        _seg("setup", 10, 20),
        _seg("payoff", 20, 30),
    ]
    groups = _split_arc_into_shorts(arc)
    assert len(groups) == 1


def test_split_arc_breaks_on_new_hook() -> None:
    arc = [
        _seg("hook", 0, 10),
        _seg("setup", 10, 20),
        _seg("hook", 100, 110),  # новая мини-история
        _seg("payoff", 110, 120),
    ]
    groups = _split_arc_into_shorts(arc)
    assert len(groups) == 2
    assert groups[0][0].role == "hook" and groups[0][0].source_start_sec == 0
    assert groups[1][0].role == "hook" and groups[1][0].source_start_sec == 100


def test_split_arc_breaks_on_overflow() -> None:
    """Сумма длительностей > REEL_MAX (89s) → разбиение."""
    arc = [
        _seg("hook", 0, 50),
        _seg("development", 50, 110),  # 50+60=110 > 89 → новая группа перед этим seg
    ]
    groups = _split_arc_into_shorts(arc)
    assert len(groups) == 2


# ---------------------------------------------------------------------------
# _merge_short_groups
# ---------------------------------------------------------------------------


def test_merge_short_groups_empty() -> None:
    assert _merge_short_groups([]) == []


def test_merge_short_groups_all_fit_within_max() -> None:
    """Две группы по 20s (каждая <MIN=31) мёрджатся в одну (40s)."""
    g1 = [_seg("hook", 0, 20)]
    g2 = [_seg("development", 100, 120)]
    merged = _merge_short_groups([g1, g2])
    assert len(merged) == 1
    assert len(merged[0]) == 2


def test_merge_short_groups_respects_max() -> None:
    """Если мёрдж превысит REEL_MAX (89s) — не объединяем."""
    g1 = [_seg("hook", 0, 50)]  # 50s
    g2 = [_seg("development", 60, 110)]  # 50s → 50+50=100 > 89 → не мёрдж
    merged = _merge_short_groups([g1, g2])
    assert len(merged) == 2


def test_merge_short_groups_tail_merged_backwards() -> None:
    """Последняя короткая группа приклеивается к предыдущей."""
    g1 = [_seg("hook", 0, 40)]  # 40s — валидная
    g2 = [_seg("development", 100, 110)]  # 10s — короткая хвостовая
    merged = _merge_short_groups([g1, g2])
    assert len(merged) == 1
    assert len(merged[0]) == 2


def test_merge_short_groups_pulls_closure_from_next_group() -> None:
    """Группа заканчивается на development → тянем следующую до payoff."""
    # g1: hook+setup+development, 45s (ok по длительности но БЕЗ closure)
    g1 = [_seg("hook", 0, 15), _seg("setup", 15, 30), _seg("development", 30, 45)]
    # g2: hook+payoff, 30s — closure-даёт payoff.
    g2 = [_seg("hook", 50, 65), _seg("payoff", 65, 80)]
    merged = _merge_short_groups([g1, g2])
    assert len(merged) == 1  # зацепили payoff
    roles = [s.role for s in merged[0]]
    assert "payoff" in roles


# ---------------------------------------------------------------------------
# _pull_closure_from_arc (cross-group assembly)
# ---------------------------------------------------------------------------


def _seg_with_closure(
    role: str, start: float, end: float, closure: str | None = None
) -> StorySegment:
    return StorySegment(
        role=role,  # type: ignore[arg-type]
        evidence_id=f"ev-{int(start)}",
        source_start_sec=start,
        source_end_sec=end,
        payoff_conclusion=closure,
    )


def test_pull_closure_from_arc_adds_payoff_when_missing() -> None:
    """Группа без peak/payoff → притягиваем payoff с payoff_conclusion из arc."""
    group = [
        _seg_with_closure("hook", 0, 10),
        _seg_with_closure("setup", 10, 25),
        _seg_with_closure("development", 25, 40),
    ]
    full_arc = [
        *group,
        _seg_with_closure("hook", 100, 110),
        _seg_with_closure("payoff", 110, 125, closure="и поэтому это работает"),
    ]
    result = _pull_closure_from_arc(group, full_arc)
    assert len(result) == 4
    assert result[-1].role == "payoff"
    assert result[-1].payoff_conclusion == "и поэтому это работает"


def test_pull_closure_from_arc_no_op_when_group_has_closure() -> None:
    """Если group уже имеет peak/payoff — не трогаем."""
    group = [
        _seg_with_closure("hook", 0, 10),
        _seg_with_closure("peak", 10, 25),
    ]
    full_arc = [*group, _seg_with_closure("payoff", 100, 115, closure="closure text")]
    result = _pull_closure_from_arc(group, full_arc)
    assert result == group


def test_pull_closure_from_arc_respects_max_duration() -> None:
    """Если sum group + payoff > REEL_MAX — не тянем."""
    group = [
        _seg_with_closure("hook", 0, 30),
        _seg_with_closure("development", 30, 75),  # 75s, near REEL_MAX=89
    ]
    full_arc = [
        *group,
        _seg_with_closure("payoff", 200, 230, closure="closure"),  # 30s → sum 105 > 89
    ]
    result = _pull_closure_from_arc(group, full_arc)
    assert result == group


def test_pull_closure_from_arc_prefers_payoff_with_conclusion() -> None:
    """Выбираем payoff с payoff_conclusion поверх payoff без closure."""
    group = [_seg_with_closure("hook", 0, 10), _seg_with_closure("development", 10, 25)]
    full_arc = [
        *group,
        _seg_with_closure("payoff", 40, 50),  # без closure
        _seg_with_closure("payoff", 100, 110, closure="и тут разрешение"),
    ]
    result = _pull_closure_from_arc(group, full_arc)
    assert len(result) == 3
    assert result[-1].payoff_conclusion == "и тут разрешение"


def test_pull_closure_from_arc_falls_back_to_peak() -> None:
    """Нет payoff → берём peak как closure."""
    group = [_seg_with_closure("hook", 0, 10), _seg_with_closure("setup", 10, 25)]
    full_arc = [*group, _seg_with_closure("peak", 80, 95)]
    result = _pull_closure_from_arc(group, full_arc)
    assert len(result) == 3
    assert result[-1].role == "peak"


def test_pull_closure_from_arc_empty_inputs() -> None:
    assert _pull_closure_from_arc([], []) == []
    seg = [_seg_with_closure("hook", 0, 10)]
    assert _pull_closure_from_arc(seg, []) == seg


def test_merge_short_groups_opportunistic_to_target() -> None:
    """Pass-2: две группы по 20s + 20s мёрджатся в 40s (ниже MIN=31 после 1-го
    прохода → объединяются, даёт 40s)."""
    g1 = [_seg("hook", 0, 20)]  # 20s < MIN — обязательный мёрдж
    g2 = [_seg("peak", 30, 50)]  # 20s
    g3 = [_seg("payoff", 60, 80)]  # 20s
    merged = _merge_short_groups([g1, g2, g3])
    # После pass-1 (обязательный под MIN=31): 20+20=40s, 20s. После pass-2
    # (к TARGET=45s): 40s + 20s → 60s (<= 89 MAX) → один merge.
    assert len(merged) == 1
    total = sum(s.duration_sec for s in merged[0])
    assert total == pytest.approx(60.0)


# ---------------------------------------------------------------------------
# _normalize_segment_bounds
# ---------------------------------------------------------------------------


def test_normalize_bounds_target_or_longer_passthrough() -> None:
    """Длительность >= REEL_TARGET (52s) — не трогаем."""
    start, end = _normalize_segment_bounds(10.0, 70.0, source_duration_sec=600.0)
    assert (start, end) == (10.0, 70.0)


def test_normalize_bounds_extends_short_to_target() -> None:
    """10s→52s target. Центр сохраняется только если границы позволяют."""
    # 100-110 (10s) в source=600 — обе стороны с запасом → симметричное расширение.
    start, end = _normalize_segment_bounds(100.0, 110.0, source_duration_sec=600.0)
    assert start is not None and end is not None
    assert end - start >= 52.0 - 0.01
    assert abs(((start + end) / 2.0) - 105.0) < 0.5  # центр ~ сохранён


def test_normalize_bounds_extends_up_to_source_boundary() -> None:
    """Начало у 0 → всё расширение вправо, достигаем REEL_TARGET."""
    start, end = _normalize_segment_bounds(0.0, 10.0, source_duration_sec=600.0)
    assert start == 0.0
    assert end is not None and end >= 52.0 - 0.01


def test_normalize_bounds_truncates_too_long() -> None:
    start, end = _normalize_segment_bounds(0.0, 200.0, source_duration_sec=600.0)
    assert start is not None and end is not None
    assert end - start <= REEL_MAX_DURATION_SEC + 0.01


def test_normalize_bounds_rejects_when_source_too_short() -> None:
    # Source = 10s, target MIN = 31s → дотянуться невозможно.
    start, end = _normalize_segment_bounds(0.0, 5.0, source_duration_sec=10.0)
    assert (start, end) == (None, None)


def test_normalize_bounds_rejects_zero_length() -> None:
    start, end = _normalize_segment_bounds(50.0, 50.0, source_duration_sec=600.0)
    assert (start, end) == (None, None)


# ---------------------------------------------------------------------------
# _greedy_uniqueness_filter
# ---------------------------------------------------------------------------


_CANDIDATE_COUNTER = {"n": 0}


def _make_candidate(score: float, tokens: set[str]) -> _Candidate:
    """Фабрика тестовых кандидатов.

    Каждый вызов возвращает кандидата с уникальным source-range, чтобы
    cross-reel segment-overlap фильтр (BUG-#J, 2026-04-18) не отбрасывал
    кандидатов из-за совпавшего диапазона — этот тест проверяет логику
    Jaccard и semantic, а не overlap.
    """
    from videomaker.models.reel_plan import ReelPlan, ReelSegment

    _CANDIDATE_COUNTER["n"] += 1
    offset = _CANDIDATE_COUNTER["n"] * 100.0

    plan = ReelPlan(
        reel_id=f"r{_CANDIDATE_COUNTER['n']}",
        hook="x",
        predicted_duration_sec=30.0,
        target_audience="",
        segments=[
            ReelSegment(
                source_start=offset,
                source_end=offset + 30.0,
                reasoning="t",
                order_role="hook",
            ),
        ],
    )
    return _Candidate(score=score, plan=plan, tokens=tokens, source="test")


def test_uniqueness_rejects_near_duplicate() -> None:
    big_set = {f"tok{i}" for i in range(10)}
    near_dup = big_set | {"extra1", "extra2"}  # 10/12 = 0.83 > 0.65 → dup
    candidates = [
        _make_candidate(0.9, big_set),
        _make_candidate(0.85, near_dup),
    ]
    result = _greedy_uniqueness_filter(candidates, max_count=10)
    assert len(result) == 1
    # первый (высокий score) принят


def test_uniqueness_accepts_distinct() -> None:
    a = {f"a{i}" for i in range(12)}
    b = {f"b{i}" for i in range(12)}
    result = _greedy_uniqueness_filter(
        [_make_candidate(0.9, a), _make_candidate(0.8, b)],
        max_count=10,
    )
    assert len(result) == 2


def test_uniqueness_respects_max_count() -> None:
    candidates = [
        _make_candidate(0.9 - i * 0.01, {f"topic{i}_{j}" for j in range(10)}) for i in range(20)
    ]
    result = _greedy_uniqueness_filter(candidates, max_count=5)
    assert len(result) == 5


def test_uniqueness_short_tokens_bypass_jaccard() -> None:
    """Тексты <8 токенов идут как есть (Jaccard недостоверен)."""
    short_a = {"a", "b", "c"}  # 3 токена
    short_b = {"a", "b", "c"}  # идентичные но мало
    result = _greedy_uniqueness_filter(
        [_make_candidate(0.9, short_a), _make_candidate(0.8, short_b)],
        max_count=10,
    )
    assert len(result) == 2  # оба приняты — нет фильтрации


# ---------------------------------------------------------------------------
# compose_reels happy path
# ---------------------------------------------------------------------------


def _sample_evidence() -> RankedEvidence:
    return RankedEvidence(
        deduped_count=3,
        items=[
            RankedEvidenceItem(
                id="r1",
                source_agent="hook_hunter",
                start=10,
                end=40,
                text="парадокс открывает интересный взгляд на успех",
                category="hook_candidate",
                composite_score=0.95,
            ),
            RankedEvidenceItem(
                id="r2",
                source_agent="emotional_peak_finder",
                start=200,
                end=230,
                text="признание героя о пережитой боли и преодолении",
                category="peak_candidate",
                composite_score=0.88,
            ),
            RankedEvidenceItem(
                id="r3",
                source_agent="motif_tracker",
                start=900,
                end=920,
                text="финальный аккорд возвращает читателя к началу истории",
                category="payoff_candidate",
                composite_score=0.82,
            ),
        ],
    )


def _sample_base_script() -> StoryScript:
    return StoryScript(
        central_theme="Трансформация через парадокс",
        bookend_motif_id="m1",
        arc=[
            StorySegment(
                role="hook",
                evidence_id="r1",
                source_start_sec=10,
                source_end_sec=40,
                text_preview="парадокс открывает взгляд",
            ),
            StorySegment(
                role="peak",
                evidence_id="r2",
                source_start_sec=200,
                source_end_sec=230,
                text_preview="признание боли",
            ),
            StorySegment(
                role="payoff",
                evidence_id="r3",
                source_start_sec=900,
                source_end_sec=920,
                text_preview="финальный аккорд",
            ),
        ],
    )


def _sample_variants() -> StoryVariants:
    return StoryVariants(
        variants=[
            StoryVariant(
                id="variant_package_of_shorts",
                kind="package_of_shorts",
                label="Package",
                target_duration_sec=300,
                predicted_duration_sec=280,
                central_theme="Трансформация через парадокс",
                arc=[
                    StorySegment(
                        role="hook",
                        evidence_id="r1",
                        source_start_sec=10,
                        source_end_sec=40,
                    ),
                    StorySegment(
                        role="payoff",
                        evidence_id="r3",
                        source_start_sec=900,
                        source_end_sec=920,
                    ),
                    StorySegment(
                        role="hook",
                        evidence_id="r2",
                        source_start_sec=200,
                        source_end_sec=230,
                    ),
                    StorySegment(
                        role="payoff",
                        evidence_id="r3",
                        source_start_sec=900,
                        source_end_sec=920,
                    ),
                ],
            ),
        ]
    )


def test_compose_reels_produces_reel_plans() -> None:
    result = compose_reels(
        ProjectCanvas(central_theme="Трансформация через парадокс"),
        _sample_evidence(),
        _sample_base_script(),
        _sample_variants(),
        source_duration_sec=20 * 60,
        llm_model="gemini-2.5-pro",
    )
    assert len(result.reels) > 0
    assert all(r.reel_id.startswith("r") for r in result.reels)
    # reel_id последовательный: r1, r2, ...
    assert result.reels[0].reel_id == "r1"
    # stats заполнены
    # 20 мин → target=12 по линейной формуле (12 рилсов на 20 мин).
    assert result.stats["target_reel_count"] == 12
    assert result.stats["ranked_evidence_count"] == 3
    assert result.stats["actual_reel_count"] == len(result.reels)


def test_compose_reels_duration_within_bounds() -> None:
    result = compose_reels(
        ProjectCanvas(),
        _sample_evidence(),
        _sample_base_script(),
        _sample_variants(),
        source_duration_sec=20 * 60,
    )
    for reel in result.reels:
        assert reel.predicted_duration_sec >= REEL_MIN_DURATION_SEC - 0.05
        assert reel.predicted_duration_sec <= REEL_MAX_DURATION_SEC + 0.05


def test_compose_reels_respects_max_count() -> None:
    """15-30 мин исходника → max 20 рилсов."""
    # Много одинаковых evidence → много кандидатов
    huge_ranked = RankedEvidence(
        items=[
            RankedEvidenceItem(
                id=f"ev{i}",
                source_agent="hook_hunter",
                start=i * 40.0,
                end=i * 40.0 + 20.0,
                text=f"уникальная тема номер {i} со своим контекстом и смыслом про жизнь",
                category="hook_candidate",
                composite_score=0.9 - i * 0.001,
            )
            for i in range(100)
        ]
    )
    result = compose_reels(
        ProjectCanvas(),
        huge_ranked,
        StoryScript(central_theme="x"),
        StoryVariants(),
        source_duration_sec=20 * 60,
    )
    assert len(result.reels) <= 20  # max для 15-30 мин


def test_compose_reels_empty_everything() -> None:
    """Нет evidence, нет variants, нет arc — рилсов нет, но AnalysisResult валидный."""
    result = compose_reels(
        ProjectCanvas(),
        RankedEvidence(),
        StoryScript(central_theme="x"),
        StoryVariants(),
        source_duration_sec=600,
    )
    assert result.reels == []
    assert result.stats["actual_reel_count"] == 0


def test_compose_reels_singles_from_ranked_fallback() -> None:
    """Пустой variants + пустой script → рилсы собираются из single-evidence."""
    result = compose_reels(
        ProjectCanvas(),
        _sample_evidence(),
        StoryScript(central_theme="x"),
        StoryVariants(),
        source_duration_sec=600,
    )
    assert len(result.reels) >= 1


def test_compose_reels_uniqueness_filter_dedups_similar() -> None:
    """Два почти-идентичных evidence (большой overlap tokens) → остаётся один."""
    # Длинные совпадающие тексты для срабатывания Jaccard ≥ threshold
    same = "герой рассказывает историю про детство и первые шаги в профессии огромный путь открытий"
    ranked = RankedEvidence(
        items=[
            RankedEvidenceItem(
                id="e1",
                source_agent="hook_hunter",
                start=10,
                end=40,
                text=same,
                category="hook_candidate",
                composite_score=0.95,
            ),
            RankedEvidenceItem(
                id="e2",
                source_agent="hook_hunter",
                start=50,
                end=80,
                text=same + " дополнение",
                category="hook_candidate",
                composite_score=0.85,
            ),
        ]
    )
    assert (
        _jaccard(_tokenize(ranked.items[0].text), _tokenize(ranked.items[1].text))
        >= UNIQUENESS_JACCARD_THRESHOLD
    )

    result = compose_reels(
        ProjectCanvas(),
        ranked,
        StoryScript(central_theme="x"),
        StoryVariants(),
        source_duration_sec=600,
    )
    # Должен остаться 1 (более сильный)
    assert len(result.reels) == 1


def test_compose_reels_reel_id_pattern_compliant() -> None:
    """reel_id после _renumber_and_finalize обязан быть валидным."""
    import re

    pattern = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
    result = compose_reels(
        ProjectCanvas(),
        _sample_evidence(),
        _sample_base_script(),
        _sample_variants(),
        source_duration_sec=20 * 60,
    )
    for reel in result.reels:
        assert pattern.match(reel.reel_id), f"bad reel_id: {reel.reel_id}"


# ---------------------------------------------------------------------------
# user_target_count override
# ---------------------------------------------------------------------------


def test_compose_reels_user_target_overrides_auto_range() -> None:
    """При user_target=10 на 20-мин видео (auto target=16) target = 10, stats фиксируют user request."""
    # Богатый pool evidence для гарантированных кандидатов.
    ranked = RankedEvidence(
        items=[
            RankedEvidenceItem(
                id=f"ev{i}",
                source_agent="hook_hunter",
                start=i * 60.0,
                end=i * 60.0 + 40.0,
                text=f"уникальная тема номер {i} со своим контекстом и смыслом про жизнь",
                category="hook_candidate",
                composite_score=0.9 - i * 0.001,
            )
            for i in range(40)
        ]
    )
    result = compose_reels(
        ProjectCanvas(),
        ranked,
        StoryScript(central_theme="x"),
        StoryVariants(),
        source_duration_sec=20 * 60,
        user_target_count=10,
    )
    assert result.stats["target_reel_count"] == 10
    assert result.stats["min_reel_count"] == 7  # max(1, 10-3)
    assert result.stats["max_reel_count"] == 13  # min(30, 10+3)
    assert result.stats["user_requested_reel_count"] == 10
    assert len(result.reels) <= 13


def test_compose_reels_user_target_none_uses_auto() -> None:
    """Без override работает auto-range (обратная совместимость)."""
    result = compose_reels(
        ProjectCanvas(),
        _sample_evidence(),
        _sample_base_script(),
        _sample_variants(),
        source_duration_sec=20 * 60,
    )
    assert result.stats["user_requested_reel_count"] is None
    # 20 мин → target=12 по линейной формуле 12 рилсов на 20 мин.
    assert result.stats["target_reel_count"] == 12


def test_compose_reels_user_target_below_min_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="user_target_count"):
        compose_reels(
            ProjectCanvas(),
            RankedEvidence(),
            StoryScript(central_theme="x"),
            StoryVariants(),
            source_duration_sec=600.0,
            user_target_count=USER_TARGET_REEL_COUNT_MIN - 1,
        )


def test_compose_reels_user_target_above_max_raises() -> None:
    import pytest

    with pytest.raises(ValueError, match="user_target_count"):
        compose_reels(
            ProjectCanvas(),
            RankedEvidence(),
            StoryScript(central_theme="x"),
            StoryVariants(),
            source_duration_sec=600.0,
            user_target_count=USER_TARGET_REEL_COUNT_MAX + 1,
        )


def test_compose_reels_user_target_small_has_fixed_tolerance() -> None:
    """user_target=10 → tolerance=max(3, round(1.0))=3 → (10, 7, 13)."""
    result = compose_reels(
        ProjectCanvas(),
        _sample_evidence(),
        _sample_base_script(),
        _sample_variants(),
        source_duration_sec=20 * 60,
        user_target_count=10,
    )
    assert result.stats["target_reel_count"] == 10
    assert result.stats["min_reel_count"] == 7
    assert result.stats["max_reel_count"] == 13


def test_compose_reels_user_target_large_scales_tolerance() -> None:
    """user_target=100 → tolerance=10 (10% от N) → (100, 90, 110)."""
    result = compose_reels(
        ProjectCanvas(),
        _sample_evidence(),
        _sample_base_script(),
        _sample_variants(),
        source_duration_sec=60 * 60,
        user_target_count=100,
    )
    assert result.stats["target_reel_count"] == 100
    assert result.stats["min_reel_count"] == 90
    assert result.stats["max_reel_count"] == 110


def test_compose_reels_user_target_at_max_ceiling_clamp() -> None:
    """user_target=225 (absolute MAX) → max clamp 225, tolerance=23 → (225, 202, 225)."""
    result = compose_reels(
        ProjectCanvas(),
        _sample_evidence(),
        _sample_base_script(),
        _sample_variants(),
        source_duration_sec=300 * 60,
        user_target_count=USER_TARGET_REEL_COUNT_MAX,
    )
    assert result.stats["target_reel_count"] == 225
    assert result.stats["max_reel_count"] == 225
    # tolerance = round(225 * 0.1) = 22/23 (зависит от banker's rounding) — проверяем диапазон.
    assert 200 <= result.stats["min_reel_count"] <= 205


def test_compose_reels_segments_have_valid_roles() -> None:
    result = compose_reels(
        ProjectCanvas(),
        _sample_evidence(),
        _sample_base_script(),
        _sample_variants(),
        source_duration_sec=20 * 60,
    )
    valid_roles = {"hook", "development", "peak", "payoff"}
    for reel in result.reels:
        for seg in reel.segments:
            assert seg.order_role in valid_roles
