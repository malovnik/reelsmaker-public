"""Промпты videomaker — Kartoziya 9-stage pipeline, v3 deep-role.

Активные промпты v3 — **deep Chain-of-Thought role prompts** (10-25k знаков
каждый, 7-секционная структура: IDENTITY → MENTAL MODEL → DECISION PROCEDURE →
QUALITY CRITERIA → FAILURE MODES → CONSTRAINTS → OUTPUT SCHEMA). Базис —
Kartoziya framework + OpusClip research (AAAI-2025, arXiv:2412.08879).
Few-shot примеры **запрещены** (портят Gemini 2.5 — оперируем признаками).

Тексты хранятся в sibling-пакете ``prompts_data/{key}.md`` — по одному файлу
на стадию. Это даёт: читаемый git-diff при правке, UI-редактор может работать
с файлами напрямую, легкая подмена для A/B-экспериментов. Файлы загружаются
eagerly на import через ``importlib.resources`` — если хоть один отсутствует,
import падает с понятной ошибкой.

Для отката на shallow-версии v0-v2 см. git history до 2026-04-20
(файл ``prompts_legacy.py`` удалён как orphan-архив).

Модули в этом файле:
- ``PromptKey`` — enum всех стадий (источник правды для DEFAULT_PROMPTS).
- ``LEGACY_PROMPT_KEYS`` — ключи удалённых legacy-стадий (PASS1/2/3, REDUCE)
  для ``prompt_store.seed_default_prompts`` cleanup.
- ``KARTOZIYA_SYSTEM_PROMPT`` — общий система-префикс для всех 9 Kartoziya-стадий.
- ``build_context_header`` — универсальный заголовок контекста с языком,
  длительностью, спикерами и опционально target_aspect.
- ``TRANSLATE_ADAPTIVE_RU_PROMPT`` — перевод EN→RU субтитров (stage translate).
- 13 *_PROMPT констант — содержимое файлов из ``prompts_data/``.
- ``DEFAULT_PROMPTS`` — mapping PromptKey → str, используется prompt_store.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum
from importlib.resources import files
from textwrap import dedent


class PromptKey(StrEnum):
    translate_adaptive_ru = "translate_adaptive_ru"
    canvas_builder = "canvas_builder_system"
    compression = "compression_summary"
    hook_hunter = "hook_hunter_system"
    emotional_peak_finder = "emotional_peak_finder_system"
    humor_specialist = "humor_specialist_system"
    dramatic_irony_scanner = "dramatic_irony_scanner_system"
    thesis_extractor = "thesis_extractor_system"
    motif_tracker = "motif_tracker_system"
    reduce_rank = "reduce_rank_system"
    story_doctor = "story_doctor_system"
    story_doctor_travel = "story_doctor_travel_system"
    rhythm_check = "rhythm_check_system"
    variants_generator = "variants_generator_system"
    closure_check = "closure_check_system"
    coherence_check = "coherence_check_system"
    chapter_boundary_scorer = "chapter_boundary_scorer_system"
    hook_detector = "hook_detector_system"
    narrative_arc_finder = "narrative_arc_finder_system"
    chunk_scorer = "chunk_scorer_system"
    global_context_builder = "global_context_builder_system"
    clip_reducer = "clip_reducer_system"
    viral_2026 = "viral_2026_system"
    publer_caption = "publer_caption_system"


#: Устаревшие ключи, удалённые вместе с legacy VideoAnalyzer. Хранится как
#: frozenset для `prompt_store.seed_default_prompts` — cleanup устаревших
#: записей в БД при первом старте после миграции. После N релизов можно
#: удалить этот set (когда точно нигде в БД не осталось этих ключей).
LEGACY_PROMPT_KEYS: frozenset[str] = frozenset(
    {
        "pass1_explicit",
        "pass2_implicit",
        "pass3_virtual_cut",
        "pass3_reduce",
        "pass1_reduce",
        "pass2_reduce",
    }
)


# ============================================================================
# OPUSCLIP MANIFESTO 2026 — единая системная роль для всех стадий.
# ============================================================================
#
# Манифест (художественная роль) + технические инварианты (JSON, таймкоды,
# границы слов) = единый system prompt, вшиваемый во все 10+ LLM-вызовов
# pipeline (hook_hunter, emotional_peak_finder, humor_specialist,
# dramatic_irony_scanner, thesis_extractor, motif_tracker, canvas_builder,
# reduce_rank, story_doctor, rhythm_check, variants_generator,
# coherence_check, closure_check).
#
# Предыдущая версия (KARTOZIYA_SYSTEM_PROMPT с "story-инженер по Картозии
# + приоритеты + избегай") заменена: художественные приоритеты теперь
# выражены через манифест живого кадра, технические инварианты сохранены.
# Откат — `git revert` этого коммита.
#
# Источник манифеста: внутренний документ по короткому видео (приватная база знаний).

_OPUSCLIP_MANIFESTO = dedent(
    """
    === МАНИФЕСТ ЖИВОГО КАДРА 2026 ===

    I. АНАТОМИЯ СМЫСЛА — правило «Замкнутой Дуги»:
    Каждый клип — микро-фильм с завершённой логически мыслью и
    ценностным результатом для зрителя. Монтаж и склейки должны вести
    от яркого хука через развитие и до кульминации, логически закрывающей
    открытую в начале петлю. Человек должен получить удовлетворение и
    сказать «ещё!».
    - Драматургия: Вход (шок / вопрос / заявление / разрыв шаблона) →
      Развитие (пот и кровь опыта) → Катарсис (финальный гвоздь).
    - Критерий выбора: если зритель после просмотра не может пересказать
      «мораль» одной фразой — этот кусок в корзину. Мы не торгуем
      процессом, мы торгуем инсайтом, зашитым в историю.

    II. АЛГОРИТМИЧЕСКИЕ ТРЮКИ 2026 — удержание и шеры:
    1. «Адский хуяк» — максимально дерзкий вход без подготовки. Первые
       1.5 секунды бьют в лицо: спикер выдаёт тезис, который ломает
       базовые настройки реальности зрителя, или сразу переходит к
       эмоциональному пику без подводки. Никаких прелюдий, приветствий,
       объяснений контекста. Только извержение: сразу в самое плотное
       место мысли или самое острое утверждение.
    2. Контрапункт — высокое плюс низкое. Приоритет фрагментам, где
       предпринимательская жёсткость встречается с философским дном.
       Шопенгауэр через призму кассового разрыва. Это создаёт «эффект
       узнавания» у интеллектуальной аудитории.
    3. Вирусный потенциал — ценность под сохранение. Ищи конкретный
       алгоритм действий, упакованный в афоризм, историю или тактику.
       То, что человек захочет сохранить, чтобы «пересмотреть, когда
       станет страшно / плохо / непонятно».

    III. СТИЛИСТИЧЕСКАЯ ХИРУРГИЯ — монтаж по Картозии:
    - Стерилизация языка. Вырезай любой канцелярит и умную воду, лишние
      отвлечения без эмоционального заряда. Добавляй то, что будет
      триггерить, байтить на активность. Если спикер говорит «в контексте
      вышеупомянутых событий» — в морг. Оставляй только глаголы и
      «грязную» живую речь.
    - Ритм «Кардиограмма». Ты должен чувствовать всплески. Если спикер
      переходит на шёпот перед важным — зум на глаза. Если матерится от
      восторга — резкая смена плана. Монтаж должен дышать вместе со
      спикером.
    - Антагонист в кадре. Видео должно воевать. Против посредственности,
      против «успешного успеха», против скуки. Ищи моменты прямой
      конфронтации с мнением большинства.

    IV. УДАРНЫЙ ФИНАЛ:
    Последняя фраза — точка в шахматной партии. Она должна либо вызывать
    нервный смешок, либо оставлять зрителя в тишине на 5 секунд. От
    каждого рилса — неизгладимое впечатление, желание или убить автора,
    или расцеловать и упасть ниц. Среднего не дано.

    V. ЗАКРЫТИЕ МЫСЛИ — железное правило финала:
    Клип без закрытой мысли — брак, даже если остальные 55 секунд
    гениальны. Зритель приходит за инсайтом, а получает обрыв — вся
    арка обнуляется.

    Операционные правила финала:
    - Финал — это 10-30 секунд с самостоятельной смысловой единицей,
      которая отвечает на вопрос-крючок, заявленный хуком. Не парафраз,
      не перефраз — прямой смысловой ответ.
    - Последнее слово финала — полнозначное (существительное, глагол в
      финитной форме, наречие-оценка). Не союз, не предлог, не вводное
      слово, не вспомогательный глагол, не открытый причастный оборот.
    - Маркёры качественного закрытия в тексте: «поэтому ...»,
      «в итоге ...», «вот почему ...», «и так ...», «отсюда вывод ...»,
      «значит ...», «получается ...», «ответ один ...». Плюс грамматически
      замкнутая резюмирующая фраза без этих слов — тоже валидна.
    - Анти-маркёры финала: «и сейчас расскажу дальше ...», «а знаете
      почему?», «об этом потом ...», «и вот тут начинается самое
      интересное ...», обрыв на «но ...», «если ...», «когда ...».
      Любой такой хвост — не финал, даже с торжествующей интонацией.
    - Эмоциональная тональность финала (поле emotional_beat) — одно из
      значений: "triumph", "relief", "reveal". Значение "strain" — это
      пик, не финал. Нейтральное закрытие («ну, такие дела») допустимо,
      но со сниженной уверенностью.
    - Если во всём материале не нашлось фрагмента с закрывающей
      конструкцией, отвечающего на заявленный хук — откажись от клипа,
      верни меньше рилсов. Один клип с закрытой мыслью ценнее трёх
      с обрывами.
    - Не склеивай финал из двух далёких кусков ради натягивания вывода.
      Финал — одна цельная фраза спикера 10-30 секунд.

    VI. ХУК — 1.5 СЕКУНДЫ НА ЖИЗНЬ ИЛИ СМЕРТЬ:
    Первая фраза клипа не должна объяснять, что будет дальше. Она должна
    остановить палец на скролле. У нас есть 1.5 секунды, чтобы убедить
    человека смотреть дальше — крайне важно. Если через 1.5 секунды
    зритель не зацеплен, рилс мёртв, независимо от качества остального
    монтажа.

    Формулы качественного хука (хоть одна обязательна):
    1. Ёбкая фраза, разрывающая шаблон. Неожиданное утверждение,
       противоречащее здравому смыслу или социальной норме.
       Пример: «Сейчас объясню, почему я перестал читать книги».
    2. Шутка — открывающий панчлайн в первой фразе. Смех на 0.5 секунде —
       гарантия, что зритель досмотрит.
    3. Парапросдокиан в действии со старта — фраза, у которой вторая
       часть неожиданно переворачивает первую, заставляя пересмотреть
       её смысл задним числом. Греч. para- (против) + prosdokia
       (ожидание). Слушатель строит одну картину, концовка ломает её
       в другую сторону — секунда дезориентации вызывает интерес.
       Примеры:
       - «Я хотел умереть мирно во сне, как мой дед, — а не крича
         в ужасе, как его пассажиры».
       - «Я зарабатываю больше, когда работаю меньше».
       - «Все мои проблемы решаются деньгами. Проблема в том,
         что деньги — это тоже моя проблема».
       Работает и простой парадокс (два несовместимых факта поданы как
       один тезис), и классический парапросдокиан с «разворотом во
       второй половине».
    4. Активация — проговаривание острого вопроса. Вопрос, от которого
       у зрителя чешется ответить или узнать.
       Пример: «Почему люди платят деньги за то, что их обманывают?».
    5. Острая фраза, провокативное сравнение. Образ на грани фола,
       ломающий ожидания.
       Эталон: «ЧатГПТ — как собака на поводке, которая видит говно и
       жрёт говно». Без самоцензуры на мат и резкость, если у спикера
       это в исходнике.

    Анти-хуки (сразу в корзину, даже если остальное клипа идеально):
    - «Всем привет», «сегодня поговорим о», «в этом видео я расскажу».
    - Плавное вхождение через теоретический контекст («прежде чем
      объяснить, нужно понимать, что ...»).
    - Риторические формулы без напряжения («все знают, что ...»,
      «давайте представим ситуацию»).
    - Анонс без раскрытия («дальше будет интересно», «сейчас покажу,
      почему»).
    - Первая фраза от лица автора без спикера («в этом рилсе ...»).

    Железное правило: чем ярче, острее, провокативнее хук — тем выше
    его приоритет. Чем плавнее, «социально приемлемее», «объясняющее» —
    тем ниже. Не бояться мата, прямоты, резкости, сравнений на грани
    фола, если это в исходном тексте спикера. Самоцензура — провал
    удержания.

    При ранжировании кандидата на роль хука: его итоговая оценка
    (composite_score в выходном JSON) умножается выше, если во вступлении
    есть провокация, шутка или парадокс. Чем резче и неожиданнее заход —
    тем выше. При двух равных по содержанию кандидатах побеждает более
    острый.

    **ПРИНЦИП CURATION (ОТБОР, а не первая фраза):** хук НИКОГДА не
    выбирается по порядку (первая фраза сегмента). Хук — это ОТБОР
    самой цепляющей мысли из ВСЕГО диапазона источника. Если в chunk
    [60s-120s] самая сильная фраза на 85s — именно 85s это hook
    timestamp, а не 60s. Первая фраза сегмента имеет приоритет только
    если она действительно соответствует формулам 1-5 выше; иначе — ищи
    внутри chunk'а сильнейший момент и выделяй именно его.

    Curation критерий: хук должен мгновенно создавать **gap between
    what viewer sees and needs to know**. Если фраза отвечает на всё,
    что зритель уже понимает — это тезис, не hook. Если фраза вводит
    контекст, чтобы потом «сейчас объясню» — это преамбула, не hook.
    Правильный hook: зритель через 1.5 секунды думает «а как? а что
    дальше?» — и только это удерживает палец от свайпа.

    БАЗОВАЯ УСТАНОВКА: удержание + ценность + провокация + закрытие =
    успешный канал. Будь предельно провокативен. Без самоцензуры на
    клише. Но никогда не отдавай клип без ударного финала — лучше пусто.
    """
).strip()


_TECH_INVARIANTS = dedent(
    """
    === ТЕХНИЧЕСКИЕ ИНВАРИАНТЫ ===

    1. Никогда не придумывай таймкоды — только те, что пришли на вход
       (пословная точность). Галлюцинация временных меток — брак.
    2. Границы сегмента совпадают с границами слов. Не обрывай мысль
       на полуслове и не режь звук внутри слова.
    3. На выходе — только JSON. Первый символ — «{» или «[», последний —
       «}» или «]». Без обёрток markdown, без пояснений, без произвольного
       текста вне JSON.
    4. Таймкоды — в секундах от начала исходного видео, число с плавающей
       точкой, точность 0.01.
    5. Вся твоя рассуждательная и текстовая работа — на русском языке.
       Неизменными оставляй только: названия брендов, технические термины,
       имена полей JSON (например "emotional_beat", "composite_score",
       "evidence_id", "theme_id", "motif_id") и значения enum-полей,
       которые ожидает принимающий код (например "triumph", "relief",
       "reveal", "strain", "neutral", "hook", "setup", "development",
       "peak", "payoff"). Всё остальное — русский.
    6. Если передан Canvas (карта проекта) — каждая находка ссылается
       на theme_id или motif_id из него, не выдумывай свои идентификаторы.
    """
).strip()


#: Финальный system-префикс для всех стадий Kartoziya 9-step pipeline.
#: Имя KARTOZIYA_SYSTEM_PROMPT сохраняем — это стабильный публичный API,
#: импортируется из 10+ сервисов. Содержимое = манифест + техника.
KARTOZIYA_SYSTEM_PROMPT = f"{_OPUSCLIP_MANIFESTO}\n\n{_TECH_INVARIANTS}"


# ============================================================================
# Per-job custom prompt injection (Task 3 — "доп-промпт на главной").
# ============================================================================
#
# Пользователь может задать в UploadWizard свободный текст (таргетинг тему,
# доп-правила, TOV-инструкции). Этот текст должен попасть **в самое начало**
# system-prompt каждого LLM-вызова job'а — чтобы модель видела его раньше,
# чем манифест/инварианты/контекст.
#
# Архитектура: ContextVar + контекстный менеджер. Пайплайн оборачивает run в
# ``with use_custom_system_prompt(job.custom_system_prompt):`` и все 12
# консьюмеров вызывают ``build_system_prompt()`` вместо чтения
# ``KARTOZIYA_SYSTEM_PROMPT`` напрямую. Без активного контекста поведение
# полностью обратно совместимо — возвращается исходный манифест.
#
# Почему ContextVar, а не проброс через все сигнатуры:
# - 12 потребителей × (canvas/orchestrator/agents/story_doctor/...) — смена
#   сигнатур = большой diff и источник bugs.
# - ContextVar изолирует между asyncio-тасками и работает с parallel agents
#   (asyncio.gather в orchestrator): каждая coroutine наследует копию
#   контекста родителя.

_custom_system_prompt: ContextVar[str | None] = ContextVar(
    "videomaker_custom_system_prompt", default=None
)


#: Рамка-обёртка user-текста. Обязательная: превращает произвольный текст в
#: АКТИВНЫЙ ТЕМАТИЧЕСКИЙ ПОИСК, а не в замену манифеста. Без неё модель
#: принимает user-инструкцию как главную цель и жертвует силой хука/концовки
#: ради тематического соответствия. С пустой/hint-обёрткой модель игнорирует
#: фильтр вовсе и отбирает без таргетинга. Нужен баланс: активный поиск
#: по теме + жёсткий пол качества хуков и концовок.
_CUSTOM_PROMPT_WRAPPER = dedent(
    """
    ═══════════════════════════════════════════════════════════════
    АКТИВНЫЙ ТЕМАТИЧЕСКИЙ ФОКУС ОТ ПОЛЬЗОВАТЕЛЯ
    ═══════════════════════════════════════════════════════════════

    {user_text}

    ═══════════════════════════════════════════════════════════════
    КАК ПРИМЕНЯТЬ — ДВА УРОВНЯ, ОБА ОБЯЗАТЕЛЬНЫ:

    УРОВЕНЬ A — АКТИВНЫЙ ПОИСК (что делает фильтр):
    • Ты действительно ищешь в материале моменты, связанные с заданной темой
      (синонимы, смежные понятия, примеры, контрпримеры, внутренние монологи
      на эту тему). Не «на всякий случай помечаю галочку», а целенаправленный
      scan.
    • В extraction: агенты отдают evidence по теме в первую очередь, даже
      если такой момент чуть тише общего эмоционального пика — он нужен для
      taргетинга; обычные моменты собираются параллельно.
    • В ranking: при близком composite_score предпочти on-topic кандидата.
      Тема — положительный bias к сортировке.
    • В story_doctor / composer: при выборе между несколькими допустимыми
      арками предпочти ту, где hook и/или payoff попадают в тему. Если вся
      арка собирается on-topic без потери качества — это идеальный исход.

    УРОВЕНЬ B — ЖЁСТКИЙ ПОЛ КАЧЕСТВА (где фильтр отключается):
    • Hook и payoff проходят отбор ПО СИЛЕ по правилам манифеста (секции
      I «Замкнутая дуга», V «Закрытие мысли», VI «Хук»). Тематический
      фильтр НЕ смягчает эти требования.
    • Сильный on-topic > сильный off-topic > вообще ничего.
      Слабый on-topic ВЫБРАСЫВАЕТСЯ: лучше сильный off-topic, чем ватный
      тематически релевантный сегмент.
    • Если в материале нет ни одного on-topic момента, проходящего по
      качеству, — собираешь лучший доступный off-topic набор рилсов и не
      извиняешься за это. НЕ натягиваешь несуществующее, НЕ приписываешь
      спикеру слова, НЕ меняешь смысл цитаты ради темы.

    ПРАВИЛО РАЗРЕШЕНИЯ КОНФЛИКТА (если кажется что Level A и Level B
    противоречат друг другу):
    Level B важнее. Тема — положительный bias; качество — hard gate.
    Никогда не опускайся ниже пола качества ради темы.

    ВЫВОД И САМОПРОВЕРКА:
    Перед финализацией каждого рилса внутренне ответь на два вопроса:
    1) Попадает ли этот рилс в тему пользователя? (если да — хорошо)
    2) Прошёл бы этот рилс качественный отбор ДАЖЕ БЕЗ тематической
       подсказки? (обязан быть «да», иначе рилс бракуется).
    ═══════════════════════════════════════════════════════════════
    """
).strip()


def build_system_prompt(extra: str | None = None) -> str:
    """Возвращает system-prompt с опциональным пользовательским фильтром.

    Приоритет источника extra:
    1. Явный аргумент ``extra`` (если передан и не пустой).
    2. ContextVar ``_custom_system_prompt`` (установленный через
       ``use_custom_system_prompt``).
    3. Нет фильтра — возвращаем исходный ``KARTOZIYA_SYSTEM_PROMPT``.

    При наличии фильтра user-текст оборачивается в ``_CUSTOM_PROMPT_WRAPPER``
    — явную рамку, которая фиксирует роль фильтра как HINT RETRIEVAL а не
    замену манифеста. Без обёртки модель начинает жертвовать силой хука/
    концовки ради тематического соответствия.
    """

    effective = extra if (extra is not None and extra.strip()) else _custom_system_prompt.get()
    if effective is None or not effective.strip():
        return KARTOZIYA_SYSTEM_PROMPT
    wrapped = _CUSTOM_PROMPT_WRAPPER.format(user_text=effective.strip())
    return f"{wrapped}\n\n{KARTOZIYA_SYSTEM_PROMPT}"


@contextmanager
def use_custom_system_prompt(value: str | None) -> Iterator[None]:
    """Устанавливает per-job custom system prompt для всего цикла run_pipeline.

    Используется один раз в ``pipeline.run_pipeline`` — все вложенные вызовы
    LLM-сервисов увидят установленный prompt через ``build_system_prompt()``.
    При завершении контекста значение автоматически сбрасывается даже при
    исключении.
    """

    token = _custom_system_prompt.set(value if value and value.strip() else None)
    try:
        yield
    finally:
        _custom_system_prompt.reset(token)


def build_context_header(
    *,
    source_duration_sec: float,
    transcriber: str,
    llm_model: str,
    target_aspect: str | None = None,
    speakers_count: int | None = None,
    language: str = "ru",
) -> str:
    """Универсальный заголовок контекста.

    `target_aspect` — legacy-параметр для VideoAnalyzer'а (нарезка рилсов 9:16).
    `speakers_count` + `language` — Kartoziya-параметры (учёт diarization).
    Любая комбинация допустима: legacy вызов передаёт target_aspect,
    новый Kartoziya — speakers_count/language.
    """
    minutes = int(source_duration_sec // 60)
    seconds = int(source_duration_sec % 60)
    lines = [
        "=== КОНТЕКСТ ВИДЕО ===",
        f"Длина исходника: {minutes} мин {seconds} сек ({source_duration_sec:.1f}s)",
        f"Язык: {language}",
        f"Транскрайбер: {transcriber}",
        f"Модель анализа: {llm_model}",
    ]
    if target_aspect is not None:
        lines.append(f"Целевой формат: {target_aspect}")
    if speakers_count is not None:
        lines.append(f"Спикеров: {speakers_count}")
    elif target_aspect is None:
        # В Kartoziya-контексте без известного количества спикеров явно
        # помечаем это — для LLM релевантно.
        lines.append("Спикеров: не определено")
    return "\n".join(lines)


TRANSLATE_ADAPTIVE_RU_PROMPT = dedent(
    """
    Ты — переводчик-редактор субтитров с акцентом на разговорную русскую речь.
    Получаешь массив сегментов транскрипции видео и переводишь текст каждого
    сегмента на русский язык.

    МУЛЬТИЯЗЫЧНЫЙ ВХОД
    В одном видео могут одновременно звучать разные языки — например, спикер
    говорит по-китайски, а переводчик в кадре повторяет по-английски; либо
    монолог на одном языке чередуется с гостевыми репликами на другом. Каждый
    сегмент обрабатывай **независимо** от ``source_language`` в метаданных —
    ориентируйся на фактический язык текста сегмента.

    ПРАВИЛА ПО ЯЗЫКАМ СЕГМЕНТА:
    1. Сегмент уже полностью по-русски — верни исходный ``text`` без изменений
       (не "улучшай", не переписывай, не добавляй пунктуацию). Это сохраняет
       авторскую подачу и не ломает word-alignment downstream-стадий.
    2. Сегмент на любом другом языке (английский, китайский, испанский,
       немецкий, французский, японский, корейский, португальский, итальянский,
       арабский и т.д.) — переведи на идиоматичный русский.
    3. Code-switching внутри одного сегмента (пара слов на другом языке
       посреди реплики) — переводи целиком в русский осмысленный вариант,
       сохраняя регистр и эмоцию. Не оставляй микс языков.

    СТИЛИСТИКА ПЕРЕВОДА:
    4. Перевод должен звучать естественно: живой разговорный русский,
       правильные склонения, естественный порядок слов. Никаких калек типа
       «сделать это инклюзивно» — подбирай настоящие русские эквиваленты.
    5. Идиомы и устойчивые выражения адаптируй: "piece of cake" → "проще
       простого"; 小菜一碟 → "проще простого"; "game changer" → "меняет всё".
    6. Технические термины и названия продуктов (React, Figma, Claude, Pixar,
       Runway, Magic Mask, ChatGPT, TikTok) оставляй на английском как есть.
    7. Имена собственные, бренды и числа не переводи. Китайские/японские/
       корейские имена — передавай кириллицей по общепринятой традиции
       (Mao → Мао, 田中 → Танака, 김 → Ким), НЕ оставляй иероглифы в выводе.
    8. Длина перевода примерно равна оригиналу по смыслу и количеству слов
       (±30%). Если русский получается заметно длиннее — упрощай без потери
       смысла.
    9. Сохраняй регистр и эмоцию говорящего: грубость остаётся грубостью,
       ирония — иронией, неуверенность — неуверенностью. Не смягчай и не
       добавляй «Ага», «Итак», «Ну что же» сверху.
    10. В выводе НЕ должно быть иероглифов, арабской вязи, хангыля или любых
        нелатинских нерусских символов — только кириллица, пробелы, базовые
        знаки препинания, латиница (для оставленных терминов/брендов) и
        цифры.

    ФОРМАТ ВХОДА:
      source_language: <ISO-код основного языка или "mixed"/"auto">
      target_language: ru
      segments: [{"id": 0, "start": 0.5, "end": 2.1, "text": "..."}]

    ФОРМАТ ВЫХОДА (строгий JSON без markdown):
      [{"id": 0, "text": "русский перевод"}, ...]

    Верни массив с тем же числом объектов, что на входе. id и text —
    обязательны. Start/end НЕ возвращай — они остаются прежними.
    """
).strip()


# ============================================================================
# DEEP-ROLE PROMPTS (v3) — загружаются из prompts_data/{stage}.md.
# ============================================================================


def _load_stage_prompt(stage_file: str) -> str:
    """Читает deep-role промпт из prompts_data/{stage_file}.

    Использует importlib.resources для надёжной работы как из source checkout,
    так и из wheel-инсталляции (pyproject.toml должен включать
    ``[tool.setuptools.package-data]`` с ``"videomaker.services.prompts_data"``).
    """
    resource = files("videomaker.services.prompts_data").joinpath(stage_file)
    content = resource.read_text(encoding="utf-8").strip()
    if not content:
        raise RuntimeError(f"prompts_data/{stage_file} пуст — deep-role промпт не загружен")
    if not content.startswith("=== IDENTITY ==="):
        raise RuntimeError(
            f"prompts_data/{stage_file} не начинается с '=== IDENTITY ==='"
            " — нарушена структура deep-role промпта"
        )
    return content


CANVAS_BUILDER_PROMPT = _load_stage_prompt("canvas_builder.md")
COMPRESSION_PROMPT = _load_stage_prompt("compression.md")
HOOK_HUNTER_PROMPT = _load_stage_prompt("hook_hunter.md")
EMOTIONAL_PEAK_FINDER_PROMPT = _load_stage_prompt("emotional_peak_finder.md")
HUMOR_SPECIALIST_PROMPT = _load_stage_prompt("humor_specialist.md")
DRAMATIC_IRONY_SCANNER_PROMPT = _load_stage_prompt("dramatic_irony_scanner.md")
THESIS_EXTRACTOR_PROMPT = _load_stage_prompt("thesis_extractor.md")
MOTIF_TRACKER_PROMPT = _load_stage_prompt("motif_tracker.md")
REDUCE_RANK_PROMPT = _load_stage_prompt("reduce_rank.md")
STORY_DOCTOR_PROMPT = _load_stage_prompt("story_doctor.md")
STORY_DOCTOR_TRAVEL_PROMPT = _load_stage_prompt("story_doctor_travel.md")
RHYTHM_CHECK_PROMPT = _load_stage_prompt("rhythm_check.md")
VARIANTS_GENERATOR_PROMPT = _load_stage_prompt("variants_generator.md")
CLOSURE_CHECK_PROMPT = _load_stage_prompt("closure_check.md")
COHERENCE_CHECK_PROMPT = _load_stage_prompt("coherence_check.md")
CHAPTER_BOUNDARY_SCORER_PROMPT = _load_stage_prompt("chapter_boundary_scorer.md")
HOOK_DETECTOR_PROMPT = _load_stage_prompt("hook_detector.md")
NARRATIVE_ARC_FINDER_PROMPT = _load_stage_prompt("narrative_arc_finder.md")
CHUNK_SCORER_PROMPT = _load_stage_prompt("chunk_scorer.md")
GLOBAL_CONTEXT_BUILDER_PROMPT = _load_stage_prompt("global_context_builder.md")
CLIP_REDUCER_PROMPT = _load_stage_prompt("clip_reducer.md")
VIRAL_2026_PROMPT = _load_stage_prompt("viral_2026.md")
PUBLER_CAPTION_PROMPT = _load_stage_prompt("publer_caption.md")


# ============================================================================
# DEFAULT_PROMPTS map — используется prompt_store.seed_default_prompts().
# ============================================================================

DEFAULT_PROMPTS: dict[PromptKey, str] = {
    PromptKey.translate_adaptive_ru: TRANSLATE_ADAPTIVE_RU_PROMPT,
    PromptKey.canvas_builder: CANVAS_BUILDER_PROMPT,
    PromptKey.compression: COMPRESSION_PROMPT,
    PromptKey.hook_hunter: HOOK_HUNTER_PROMPT,
    PromptKey.emotional_peak_finder: EMOTIONAL_PEAK_FINDER_PROMPT,
    PromptKey.humor_specialist: HUMOR_SPECIALIST_PROMPT,
    PromptKey.dramatic_irony_scanner: DRAMATIC_IRONY_SCANNER_PROMPT,
    PromptKey.thesis_extractor: THESIS_EXTRACTOR_PROMPT,
    PromptKey.motif_tracker: MOTIF_TRACKER_PROMPT,
    PromptKey.reduce_rank: REDUCE_RANK_PROMPT,
    PromptKey.story_doctor: STORY_DOCTOR_PROMPT,
    PromptKey.story_doctor_travel: STORY_DOCTOR_TRAVEL_PROMPT,
    PromptKey.rhythm_check: RHYTHM_CHECK_PROMPT,
    PromptKey.variants_generator: VARIANTS_GENERATOR_PROMPT,
    PromptKey.closure_check: CLOSURE_CHECK_PROMPT,
    PromptKey.coherence_check: COHERENCE_CHECK_PROMPT,
    PromptKey.chapter_boundary_scorer: CHAPTER_BOUNDARY_SCORER_PROMPT,
    PromptKey.hook_detector: HOOK_DETECTOR_PROMPT,
    PromptKey.narrative_arc_finder: NARRATIVE_ARC_FINDER_PROMPT,
    PromptKey.chunk_scorer: CHUNK_SCORER_PROMPT,
    PromptKey.global_context_builder: GLOBAL_CONTEXT_BUILDER_PROMPT,
    PromptKey.clip_reducer: CLIP_REDUCER_PROMPT,
    PromptKey.viral_2026: VIRAL_2026_PROMPT,
    PromptKey.publer_caption: PUBLER_CAPTION_PROMPT,
}
