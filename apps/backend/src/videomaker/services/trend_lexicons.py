"""T2.4 — Trend-score lexicons per profile.

Replacement для placeholder ``trend_pct = 70`` в `_populate_reel_scoring`.
Считает hit-rate по per-profile виральным ключевым словам и universal
viral-markers (числовые паттерны, суперлативы, hook-слова).

ТРИЗ «универсальность»: разные словари для разных профилей, но единый
интерфейс `compute_trend_score(text, profile) -> float`. Возвращает 0-1.

Не использует LLM — чистая лексическая проверка, O(слова × лексикон).
Детерминистично, дёшево, расширяемо (добавил слово — пересчитался).

Лексиконы намеренно компактные: ~15-25 маркеров на профиль, чтобы
hit-rate был осмысленным. Слишком большой словарь превращает метрику
в «все рилсы 100%».
"""

from __future__ import annotations

import re

from videomaker.models.job import VisionProfile

_TOKENIZER = re.compile(r"[а-яёa-z0-9]+", re.IGNORECASE)


#: Universal viral markers (работают для любого профиля).
_UNIVERSAL_MARKERS: frozenset[str] = frozenset({
    # Числовые hook'и
    "секрет", "правило", "причина", "способ", "приём", "правила", "приёма",
    "причины", "шаг", "шага", "шагов", "ошибка", "ошибки", "ошибок",
    # Contrarian / провокация
    "почему", "зачем", "никогда", "всегда", "перестал", "перестала",
    "бросил", "бросила", "обман", "миф", "правда", "парадокс",
    # Intensifiers
    "самый", "самая", "самое", "единственный", "единственная", "впервые",
    "главный", "главная", "главное", "настоящий", "настоящая",
    # Personal revelation
    "заметил", "понял", "поняла", "открыл", "открыла", "осознал", "осознала",
})


#: Per-profile trend lexicons.
_PROFILE_LEXICONS: dict[VisionProfile, frozenset[str]] = {
    VisionProfile.talking_head: frozenset({
        "мысль", "идея", "взгляд", "мнение", "урок", "опыт", "история",
        "случай", "совет", "практика", "подход", "метод", "фраза",
        "разговор", "беседа", "диалог", "монолог",
    }),
    VisionProfile.fashion: frozenset({
        "стиль", "образ", "лук", "капсула", "базовый", "базовая",
        "тренд", "микро", "aesthetic", "силуэт", "фасон", "детали",
        "акцент", "палитра", "актуально", "must", "винтаж", "архив",
        "коллекция", "сезон", "подиум", "показ", "лукбук", "кэжуал",
        "офис", "классика", "нью", "норм", "квай",
    }),
    VisionProfile.travel: frozenset({
        "маршрут", "локация", "спот", "место", "город", "остров", "страна",
        "виза", "бюджет", "билет", "жильё", "отель", "перелёт", "дорога",
        "приключение", "поездка", "путешествие", "путь", "открытие",
        "скрытый", "скрытая", "нетуристический", "аутентичный", "закат",
        "природа", "храм", "рынок",
    }),
    VisionProfile.screencast: frozenset({
        "туториал", "лайфхак", "трюк", "функция", "фича", "настройка",
        "параметр", "ярлык", "шорткат", "хоткей", "команда", "скрипт",
        "плагин", "расширение", "автоматизация", "workflow", "пайплайн",
        "продуктивность", "эффективность", "ускорить", "упростить",
        "копипаст", "клик", "меню",
    }),
    VisionProfile.custom: frozenset(),
}


def compute_trend_score(
    reel_text: str,
    profile: VisionProfile,
) -> float:
    """Возвращает 0-1 trend-score для текста рилса.

    Формула: взвешенная сумма hit-rate по universal + profile lexicon.
    Universal markers весят 40%, profile-specific 60% (профиль лучше
    понимает свою нишу).

    Пустой текст / custom профиль без лексикона → baseline 0.5
    (нейтрально, не штрафуем и не бустим).
    """
    if not reel_text:
        return 0.5

    tokens = [t.lower() for t in _TOKENIZER.findall(reel_text)]
    if not tokens:
        return 0.5
    token_set = set(tokens)

    universal_hits = len(token_set & _UNIVERSAL_MARKERS)
    universal_rate = min(1.0, universal_hits / 5.0)
    # 5 hits = cap 100%. 0 hits = 0%. Линейно между.

    profile_lex = _PROFILE_LEXICONS.get(profile, frozenset())
    if not profile_lex:
        # custom / пустой лексикон — возвращаем только universal с boost
        # чтобы не занижать custom-профиль из-за отсутствия словаря.
        return max(0.5, universal_rate)

    profile_hits = len(token_set & profile_lex)
    profile_rate = min(1.0, profile_hits / 4.0)
    # 4 hits = cap (профиль-лексикон короче universal'а).

    weighted = 0.4 * universal_rate + 0.6 * profile_rate
    return max(0.0, min(1.0, weighted))


__all__ = [
    "compute_trend_score",
]
