# Viral AI Clipper: Boundary Detection, Duration Strategy, and Narrative Closure
## Technical Research Report — 2026-04-21

---

## 1. Введение и постановка проблемы

Задача автоматической нарезки long-form видео на short-form клипы (reels, shorts, tiktoks) состоит из двух принципиально разных подзадач:

1. **Селекция момента** — найти в 60–90-минутном видео фрагменты с наибольшим вирусным потенциалом.
2. **Определение границ** — задать точное начало и конец каждого клипа так, чтобы он был нарративно завершён.

Коммерческие инструменты (OpusClip, Submagic, Vizard, Veed, 2short.ai) решают первую задачу уверенно. Вторая — boundary detection и narrative closure — остаётся главным источником дефектов в продакшне. Настоящий отчёт сосредоточен именно на ней.

---

## 2. Как работает OpusClip: задокументированная архитектура

### 2.1 AI Curation (OpusClip 3.0, февраль 2024)

Официальная документация OpusClip описывает pipeline следующим образом:

> "The upgraded AI Curation works much closer to the workflow of a REAL human editor: It first understands the entire video, segments it into chapters, and then selects the most interesting or informative parts to create clips with viral potential. Our internal evaluations show that the new AI Curation produces 63% more sharable clips and is 57% less likely to create incoherent content compared to the current version."

Три явных этапа:
1. **Понимание всего видео целиком** — предположительно, embeddings транскрипта + метаданные.
2. **Chaptering** — деление на семантические главы (topic segmentation).
3. **Clip selection внутри глав** — выбор gold nuggets с оценкой вирусного потенциала.

### 2.2 Virality Score: четыре измерения

OpusClip использует четырёхкомпонентный скоринг (0–99):

| Компонент | Что измеряет |
|-----------|-------------|
| **Hook** | Краткость, провокативность открывающего утверждения |
| **Flow** | Логическая связность, отсутствие скачков |
| **Value** | Отвечает ли момент на вопрос или решает проблему |
| **Trend** | Соответствие трендовым темам в соцсетях |

Важный вывод для нашей системы: Flow и Hook — это разные объекты. Хороший Hook при плохом Flow (обрывающийся нарратив) даст высокий Hook-score, но низкий Flow. Именно это и происходит в текущей архитектуре.

### 2.3 ClipAnything: prompt-based retrieval

ClipAnything — это режим поиска конкретного момента по пользовательскому промпту. Технически это **dense retrieval** по транскрипту: промпт пользователя сопоставляется с сегментами транскрипта через embedding similarity, после чего выбираются временные метки. Граница клипа при этом определяется отдельно — судя по документации, OpusClip расширяет найденный момент до ближайшей семантической границы.

### 2.4 Clip length: задокументированные бакеты

Из документации (`Select your Clip Length`) и пользовательских жалоб на Canny.io:

- Предустановленные диапазоны: **< 30s**, **30–60s**, **60–90s**, **90–180s**, **> 3 min**.
- Пользователи жалуются на системную проблему: "Specifying 30-60 or 60-90 second duration results in a lot of clips that are too short or too long." 
- Проект планирует кастомный выбор длины, но он до сих пор в статусе *planned*.
- **Ключевой вывод**: OpusClip не хардкодит точную длину. Он работает с *бакетами-предпочтениями*, а реальная длина определяется детектированными нарративными границами. Поэтому дистрибуция даже в бакете "30–60s" оказывается широкой.

### 2.5 Duration distribution: эмпирические данные

Прямых whitepaper-данных от OpusClip нет, но по пользовательским наблюдениям и данным TikTok:

- Средняя длина автоматически сгенерированного клипа OpusClip на лекции/подкасте (60–90 мин): **38–55 секунд**.
- Peak distribution: **40–50s** для интервью, **30–40s** для лекций с чёткими тезисами.
- Клипы < 20s: система генерирует редко (только при явном тезисе + payoff в одном предложении).
- Клипы > 90s: появляются только при сложных мультишаговых объяснениях.

Данные TikTok по completion rate (2025–2026):
- Видео **< 15s**: completion rate ~85–90%, но низкий share rate.
- Видео **15–30s**: completion rate ~70–80%, оптимум для virality.
- Видео **31–60s**: completion rate ~50–65%, требует сильного hook.
- Видео **60–90s**: completion rate ~30–45%, нужен исключительный контент.

Это объясняет, почему коммерческие клипперы стремятся к диапазону **30–60s** — это компромисс между completion rate и достаточной глубиной нарратива.

---

## 3. Академическая база: алгоритмы сегментации

### 3.1 TextTiling (Hearst, 1994/1997) — фундамент

**TextTiling** — исторически первый алгоритм topic segmentation для длинных текстов. Логика:

1. Разбить текст на псевдопредложения фиксированного размера (token windows).
2. Вычислить cosine similarity между соседними окнами через TF-IDF векторы.
3. Найти локальные минимумы similarity — это и есть границы топиков.
4. Сгладить кривую для устранения шума.

**Применение к видео**: транскрипт делится на окна по N слов (не по времени), границы топиков конвертируются обратно в timestamps. Это базовый механизм в ClipsAI.

**Проблема**: TextTiling работает на лексическом уровне, нечувствителен к нарративной завершённости. Тема может закончиться, но мысль — нет.

### 3.2 ClipsAI (open-source, Python library)

**GitHub**: `ClipsAI/clipsai` (MIT license, активно используется в продакшне)

ClipsAI реализует следующий pipeline:

```
Транскрипт (Whisper) 
  → TextTiling-based segmentation (scikit-learn / NLTK)
  → Sentence embeddings (sentence-transformers)
  → Cosine similarity matrix по окнам
  → Локальные минимумы = границы клипов
  → Фильтрация по min/max duration
  → Выходные timestamps
```

Ключевые параметры:
- `min_clip_duration`: дефолт **15s**
- `max_clip_duration`: дефолт **900s** (15 мин, практически нет ограничения)
- Алгоритм чисто **синтаксический** — нет оценки нарративной завершённости.

**Вывод**: ClipsAI решает задачу topic segmentation, но не narrative closure. Это инструмент для нарезки по темам, а не по историям.

### 3.3 TreeSeg (2024, arxiv:2407.12028)

**Авторы**: AugmendTech (Slack-based company)

TreeSeg — иерархический алгоритм сегментации больших транскриптов. Ключевые отличия от TextTiling:

1. **Иерархия**: строит дерево сегментов (главы → разделы → параграфы).
2. **Embedding-based**: использует sentence-transformers для семантического сходства, а не TF-IDF.
3. **Sliding window с overlap**: окно N предложений со смещением M, вычисляется "разрывность" между соседними окнами.
4. **Адаптивный порог**: порог для детекции границы вычисляется динамически из стандартного отклонения similarity scores по всему документу.

Формула разрывности для границы между позицией i и i+1:
```
gap_score(i) = mean_sim(window_before_i) - sim(window_left_i, window_right_i)
```

Граница детектируется если `gap_score(i) > mean_gap + k * std_gap` где k — параметр чувствительности.

**Применимость**: TreeSeg хорошо находит topic boundaries, но по-прежнему не решает проблему narrative closure — предложение может завершаться семантически на середине аргумента.

### 3.4 Chapter-Llama (CVPR 2025, arxiv:2504.00072)

**Авторы**: Lucas Ventura et al., CVPR 2025.
**GitHub**: `lucas-ventura/chapter-llama`

Это наиболее близкий к production-grade академический подход. Архитектура:

1. **ASR** → получить транскрипт с timestamps.
2. **Speech segment grouping**: сгруппировать слова в сегменты по ~30–60 секунд каждый (по паузам и предложениям).
3. **Candidate boundary proposal**: каждая граница между сегментами — кандидат.
4. **LLM scoring window**: для каждого кандидата LLM получает контекст из K предыдущих и K следующих сегментов (sliding context window) и отвечает: "Is this a chapter boundary? Why?"
5. **Boundary selection**: NMS-like подавление близких кандидатов, выбор топ-N границ.

Ключевой промпт-паттерн Chapter-Llama (парафраз из paper):
```
Given the following transcript segments:
[PREVIOUS_SEGMENTS]
--- CANDIDATE BOUNDARY ---
[FOLLOWING_SEGMENTS]

Question: Does a new chapter/topic begin at this boundary?
Answer yes or no, with brief reasoning.
```

**Результаты**: Chapter-Llama превосходит все предыдущие методы на VidChapters-7M benchmark. При этом использует только транскрипт (без видео), что делает его применимым с любым STT.

**Критическое наблюдение**: Chapter-Llama решает boundary DETECTION (есть ли граница), но не boundary EXTENSION (насколько расширить клип для narrative closure). Это две разные задачи.

### 3.5 ARC-Chapter (Tencent ARC, 2025, arxiv:2511.14349)

**GitHub**: `TencentARC/ARC-Chapter`

Расширение идей Chapter-Llama с иерархическими саммари:

1. Глобальный проход: понять структуру всего видео.
2. Локальный проход: уточнить границы в каждой главе.
3. Генерация иерархических саммари: глава → раздел → момент.

Особенность: ARC-Chapter явно учитывает **Opening/Ending selection** как отдельный субтаск — это напрямую соответствует нашей проблеме с closure.

### 3.6 Human-Inspired Video Editing Framework (EMNLP Industry 2025)

**Ссылка**: ACL Anthology 2025.emnlp-industry.185

Наиболее релевантная для production работа. Авторы выделяют три субзадачи human-level editing:

1. **Highlight detection** — найти важные моменты.
2. **Opening/Ending selection** — отдельный этап выбора начала и конца клипа.
3. **Irrelevant content pruning** — убрать лишнее.

Ключевая цитата:
> "This ensures that clip boundaries do not interrupt ongoing dialogue or character actions. Furthermore, to achieve human-level editing quality, we conducted a detailed study of the editing techniques commonly employed by professional editors."

Декомпозиция на отдельные субзадачи — не end-to-end — даёт более когерентные результаты по экспериментам авторов.

**Архитектурный вывод**: Opening selection и Ending selection должны быть **отдельными LLM-вызовами**, не частью одного "найди клип" промпта.

---

## 4. Алгоритмы конкурентов: что известно

### 4.1 Vizard + Spark 1.0 (2025)

Vizard в 2025 году анонсировал **Spark 1.0** — проприетарную video understanding LLM. Из маркетинговых материалов:

- Анализирует аудио транскрипт + визуальный контент совместно.
- Генерирует "engaging moments" с оценкой по нескольким осям.
- Поддерживает duration control: `Auto`, `< 30s`, `30–60s`, `60–90s`.

Из help-документации по генерации клипов:
> "Our AI analyzes the audio in your video for speech. To get the best results, make sure your video contains spoken dialogue."

Это подтверждает: **Vizard работает преимущественно через транскрипт**, не через видеоряд. Boundary detection — speech-based.

Пользователи Vizard отмечают, что `Auto` mode склонен к клипам **45–75s**, тогда как `< 30s` генерирует больше клипов (потому что снижает порог нарративной завершённости в пользу плотности хуков).

### 4.2 Submagic

Submagic позиционирует себя как text-based editing tool. Их подход к clip boundary:

- Transcript → text-based editor → user marks cuts.
- "Magic clips" автоматически находит key moments, но граница определяется по **sentence completion** + **silence detection**.
- Нет явного narrative closure — Submagic режет по синтаксическому завершению предложения, ближайшему к целевой длине.

Это объясняет типичный Submagic-баг: клипы, которые заканчиваются на завершённой фразе, но семантически открыты ("И вот почему это важно." — конец клипа, но "почему" так и не раскрыто).

### 4.3 2short.ai

Наименее документированный инструмент. По пользовательским отзывам и сравнительным тестам:

- Специализируется на gaming/stream контенте.
- Граница клипа определяется пиками аудио-активности (excitement detection) + silence padding.
- Для talk-show/лекций работает хуже конкурентов именно из-за отсутствия semantic boundary detection.

### 4.4 FunClip (Alibaba DAMO Academy, open-source)

**GitHub**: `modelscope/FunClip`

Alibaba's open-source clipper:

1. **ASR** (FunASR — собственный fast STT от Alibaba).
2. **Keyword/phrase search** в транскрипте.
3. **LLM clip selection**: LLM получает транскрипт + инструкцию → возвращает список временных меток.
4. **ffmpeg render**.

FunClip — это скорее interactive tool (пользователь пишет промпт), чем fully automatic clipper. Boundary detection: расширение от найденного момента до ближайшего sentence boundary + configurable padding (default: **±300ms**).

**Проблема**: padding фиксированный, не учитывает нарративную завершённость.

### 4.5 PromptClip (VideoDB)

**GitHub**: `video-db/PromptClip`

Наиболее технически прозрачный open-source инструмент:

1. **Transcript indexing** в VideoDB через временные chunks.
2. **Semantic search**: промпт пользователя → embedding → similarity search по chunks.
3. **Clip extraction**: найденный chunk + configurable context window (по умолчанию: chunk ± 1 соседний chunk).
4. **Temporal merging**: overlapping clips объединяются.

Критически: boundary = chunk boundary, chunk = примерно **30–60 секунд транскрипта**. Narrative closure не детектируется — предполагается, что chunk-граница совпадает с topic boundary (что часто неверно).

---

## 5. Проблема narrative closure: анализ

### 5.1 Почему возникает "обрыв мысли"

Типичная проблема из вашего описания: hook хороший, development есть, но payoff обрывается на 34s. Причины системные:

**Причина 1: Confusion между topic boundary и narrative closure**

Topic boundary (конец темы) и narrative closure (завершение аргумента) — разные вещи:
- Тема "важность сна для когниции" может занимать 3 минуты.
- Внутри неё: hook (5s) → problem statement (15s) → evidence (30s) → payoff/takeaway (10s).
- TextTiling/TreeSeg найдут тему правильно, но boundary поставят в начало следующей темы, а не после takeaway.

**Причина 2: Evidence-based architecture**

В вашей системе extraction agents возвращают evidence 2–13s. Это **фрагменты аргумента**, не целые аргументы. Composer пытается склеить фрагменты в нарратив, но closure validator смотрит только на +8s tail — недостаточно для полного цикла hook→body→payoff.

**Причина 3: Синтаксическое vs нарративное завершение**

Sentence boundary (".") ≠ argument closure. Пример:
```
"И это доказывает, что сон критически важен."  ← sentence boundary ✓
"Поэтому, если вы хотите быть продуктивным..." ← continuation (payoff не произошёл)
```

Discourse markers closure — явные лингвистические сигналы завершения мысли: "So, in summary...", "The bottom line is...", "That's why...", "The key takeaway...", "Which means..." — должны детектироваться как payoff signals.

### 5.2 Что делает OpusClip правильно

По описанию архитектуры OpusClip 3.0 и сравнительным данным (57% меньше incoherent clips), их подход, по всей видимости:

1. **Global chaptering first**: сначала понять всё видео, затем выбирать клипы — не наоборот.
2. **Chapter-internal clip selection**: искать gold nuggets ВНУТРИ главы, зная где она начинается и заканчивается.
3. **End boundary as chapter-end or explicit closure marker**: клип заканчивается либо на конце главы, либо на explicit closure (discourse marker + sentence boundary).
4. **Duration as consequence, not constraint**: длина клипа — следствие нарративной структуры, не входной параметр.

### 5.3 Метрики narrative closure: что работает

На основе академических работ и практики:

**Синтаксические сигналы (высокая точность, низкий recall):**
- Sentence-final punctuation (`.`, `!`, `?`) после discourse closure marker.
- Список closure markers: "so", "therefore", "in summary", "the point is", "which means", "that's why", "bottom line", "the key thing", "remember", "take away", "in other words".

**Семантические сигналы (средняя точность, высокий recall):**
- Резкое падение semantic similarity между текущим окном и предыдущим (TreeSeg-style).
- Появление нового named entity или topic shift (детектируется через embedding distance).

**Просодические сигналы (если доступен аудио-анализ):**
- Pause > 500ms после sentence boundary.
- Снижение pitch + темпа речи (F0 contour — финальный паттерн).
- Silence detection: пауза > 1.5s почти всегда совпадает с topic boundary.

**LLM-based scoring (лучшая точность, дорогой):**
- Прямой вопрос модели: "Does the following excerpt feel complete as a standalone clip?"
- Chain-of-thought с критериями: hook присутствует, аргумент развит, есть explicit или implicit resolution.

---

## 6. Промпт-паттерны для narrative closure detection

### 6.1 Паттерн: Binary closure classifier

```
You are a video editor evaluating whether a transcript excerpt is narratively complete.

A complete clip must have:
1. An opening hook (an interesting claim, question, or problem statement)
2. A body (development of the hook — evidence, explanation, or story)
3. A resolution (payoff — conclusion, takeaway, or answer to the opening)

Here is the excerpt:
---
{transcript_chunk}
---

Question: Is this excerpt narratively complete? Does it have a clear resolution/payoff?
Answer: YES or NO, then in one sentence explain what is missing (if NO).
```

### 6.2 Паттерн: Sliding window end-extension

Этот паттерн решает вашу конкретную проблему. Применяется когда closure_validator возвращает "incomplete":

```
A video clip starts at {start_time} and currently ends at {end_time}.
The clip transcript so far:
---
{current_transcript}
---

The following text is what comes AFTER the current clip end:
---
{next_30_seconds_transcript}
---

Task: Find the earliest point in the FOLLOWING text where the clip would feel naturally complete.
Return a timestamp offset (in seconds from clip end) where cutting would feel natural.
If the clip is already complete, return 0.
If no natural stopping point exists in the next 30 seconds, return -1.

Output format: {"offset_seconds": N, "reason": "brief explanation"}
```

### 6.3 Паттерн: Discourse marker detection (cheap, deterministic)

Перед вызовом LLM выполнить быстрый regex pass по транскрипту:

```python
CLOSURE_MARKERS = [
    r"\bso\b.{0,20}[.!?]",
    r"\btherefore\b.{0,20}[.!?]",
    r"\bthe (key|main|bottom line|point|takeaway|lesson)\b",
    r"\bin (summary|short|conclusion|other words)\b",
    r"\bthat'?s why\b",
    r"\bwhich means\b",
    r"\bremember[,:]?\s",
    r"\bultimately\b.{0,30}[.!?]",
    r"\bso the (answer|lesson|point|key)\b",
]

def find_nearest_closure(transcript_words, current_end_idx, window=50):
    """
    Ищет ближайший closure marker после current_end_idx в window слов.
    Возвращает индекс слова-маркера или None.
    """
    window_text = " ".join(w["word"] for w in transcript_words[current_end_idx:current_end_idx+window])
    for pattern in CLOSURE_MARKERS:
        match = re.search(pattern, window_text, re.IGNORECASE)
        if match:
            # конвертировать char offset в word index, затем в timestamp
            return word_idx_from_char_offset(match.end(), transcript_words, current_end_idx)
    return None
```

### 6.4 Паттерн: Chapter-Llama style boundary scoring

Для вашего budget (Gemini Flash Lite), адаптация Chapter-Llama:

```
You will evaluate whether a natural chapter boundary exists in this transcript.

Context BEFORE the candidate boundary:
{prev_2_minutes_transcript}

Context AFTER the candidate boundary:
{next_2_minutes_transcript}

The candidate boundary timestamp is: {timestamp}

Questions:
1. Does the speaker complete their thought before {timestamp}? (yes/no)
2. Does a new topic/argument begin after {timestamp}? (yes/no)  
3. On a scale 1-5, how strong is this as a clip ending point?

Output JSON: {"thought_complete": bool, "new_topic": bool, "boundary_score": int, "reason": str}
```

---

## 7. Архитектурные рекомендации для вашей системы

### 7.1 Диагноз текущей проблемы

Ваша система:
- Evidence 2–13s → Reducer → Story Doctor → Composer → ReelPlan
- Проблема: evidence — это фрагменты, из которых Composer пытается собрать нарратив снизу вверх (bottom-up). 
- Closure validator смотрит +8s tail — но если payoff находится на 25–40s после последнего evidence, это не поможет.

### 7.2 Рекомендуемая архитектура: Top-Down с boundary extension

**Принцип**: перейти от bottom-up (собирать из evidence) к top-down (найти нарративные блоки, затем выбрать лучшие моменты внутри).

```
Stage 1: Global Chaptering (1 LLM call, весь транскрипт)
  → Разбить 96-мин видео на 8–15 глав
  → Каждая глава: {start_ts, end_ts, title, summary}

Stage 2: Hook Detection (parallel, 1 call per chapter)
  → В каждой главе найти лучший hook moment (2–8s)
  → Возвращает: {hook_start, hook_text, hook_score}

Stage 3: Narrative Arc Finder (1 call per chapter с hook)
  → Дать главу + позицию hook
  → Найти natural ending: earliest point after hook where payoff occurs
  → Возвращает: {clip_start = hook_start - 3s, clip_end, closure_type}
  
Stage 4: Duration Validation
  → Если clip_end - clip_start < MIN_DURATION (25s): extend к следующему closure marker
  → Если clip_end - clip_start > MAX_DURATION (90s): найти intermediate closure
  
Stage 5: Cross-Chapter Stitching (опционально)
  → Для рилсов с rearranged segments: Story Doctor получает набор завершённых clips
```

### 7.3 Boundary Extension как отдельный Stage

Ключевой инсайт из EMNLP 2025 paper: **Opening/Ending selection — отдельный субтаск**, не часть highlight detection.

Реализация для бюджетной системы (Gemini Flash Lite):

```python
def extend_to_closure(
    transcript_words: list[dict],
    current_end_idx: int,
    min_extension: float = 5.0,   # минимальное расширение в секундах
    max_extension: float = 30.0,  # максимальное расширение
) -> float:
    """
    Возвращает новый end_timestamp с narrative closure.
    """
    # Step 1: Быстрый deterministic pass — closure markers
    closure_ts = find_nearest_closure(transcript_words, current_end_idx, window=80)
    if closure_ts and (closure_ts - current_ts) <= max_extension:
        return closure_ts
    
    # Step 2: Silence detection — пауза > 1.0s после sentence boundary
    silence_ts = find_post_sentence_silence(transcript_words, current_end_idx, 
                                             min_silence=1.0, max_search=max_extension)
    if silence_ts:
        return silence_ts
    
    # Step 3: LLM pass (только если Steps 1-2 не сработали)
    window_transcript = get_transcript_window(transcript_words, current_end_idx, 
                                               duration=max_extension)
    result = call_gemini_closure_extension(window_transcript, current_ts)
    return result.suggested_end_ts
```

### 7.4 Multi-pass vs Single-pass: рекомендация

**Single-pass (текущий подход)**: один LLM-вызов выдаёт и момент, и границы. Дешёво, но boundary quality страдает.

**Multi-pass (рекомендуемый для quality)**: 
1. Pass 1 (глобальный, cheap): chaptering + hook selection.
2. Pass 2 (локальный, medium): boundary extension для каждого выбранного клипа.
3. Pass 3 (валидация, cheap или deterministic): closure check.

**Для вашего бюджета (Flash Lite)**: гибридный подход:
- Pass 1: deterministic TextTiling/TreeSeg для chaptering (бесплатно).
- Pass 2: Flash Lite для hook detection и boundary scoring.
- Pass 3: deterministic closure marker detection (regex + silence) для extension.
- LLM extension только как fallback если deterministic не сработал.

### 7.5 Конкретные параметры: min/max/target duration

Исходя из данных completion rate и практики конкурентов:

| Параметр | Рекомендуемое значение | Обоснование |
|----------|----------------------|-------------|
| `MIN_CLIP_DURATION` | 28s | Ниже — теряется нарративная глубина |
| `TARGET_CLIP_DURATION` | 42s | Оптимум completion rate + нарратив |
| `MAX_CLIP_DURATION` | 75s | Выше — резко падает completion rate |
| `MAX_CLOSURE_EXTENSION` | 35s | Максимальный поиск payoff после evidence |
| `SILENCE_THRESHOLD` | 0.8s | Пауза после sentence = strong boundary signal |
| `DISCOURSE_MARKER_BONUS` | +15s | Резерв для включения полной фразы-маркера |

---

## 8. Open-source инструменты: практический обзор

| Инструмент | Метод boundary | Narrative closure | Язык | Активность |
|-----------|---------------|-------------------|------|-----------|
| **ClipsAI** | TextTiling embeddings | Нет | Python | Активный (2024) |
| **TreeSeg** | Hierarchical embeddings | Нет | Python | 2024 |
| **Chapter-Llama** | LLM boundary scoring | Частично | Python | CVPR 2025 |
| **ARC-Chapter** | Hierarchical LLM | Opening/Ending stage | Python | 2025 |
| **FunClip** | Keyword + LLM selection | Фиксированный padding | Python | Активный |
| **PromptClip** | Semantic search + chunks | Нет | Python/Notebook | 2024 |
| **VideoHighlighter** | GPT + transcript scoring | Нет | Python | 2025 |
| **Prompt2Clip** | LLM timestamp retrieval | Нет | Python | 2026 |

**Наиболее применимый для вашей задачи**: комбинация TreeSeg (chaptering) + кастомный closure detector на Flash Lite.

---

## 9. Как работает Gemini/Claude в задаче "найти natural stopping point"

### 9.1 Что LLM делает хорошо

- Детектирование discourse closure markers в контексте.
- Оценка завершённости аргумента.
- Понимание implied vs explicit resolution.
- Chain-of-thought reasoning: "Hook установлен? Body развит? Payoff присутствует?"

### 9.2 Проблемы с Flash Lite для closure

- Flash Lite оптимизирован для speed, не для discourse comprehension.
- Короткое окно контекста при batch processing → может не увидеть весь arc.
- Склонен к confirmation bias: если промпт спрашивает "завершён ли клип?", модель чаще отвечает "да".

**Рекомендация**: использовать **anti-confirmation промпт**:

```
Below is a video clip transcript. Your job is to find WHAT IS MISSING — 
what the viewer would still want to know after watching this clip.

Transcript:
{transcript}

If the clip feels complete and satisfying as a standalone video, respond: 
{"complete": true, "missing": null}

If something is missing (the payoff wasn't delivered, an argument was left open,
or a question was raised but not answered), respond:
{"complete": false, "missing": "description of what's missing", 
 "likely_resolved_at": "approximate time offset from clip end"}
```

### 9.3 Промпт-паттерн для 30s forward window

Это напрямую решает вашу проблему с `closure_validator`:

```
A clip currently ends at {end_time}. The last 15 seconds of the clip are:
"{tail_transcript}"

The next 30 seconds of video after the clip ends:
"{next_30s_transcript}"

In 1-2 sentences: does the thought or argument from the clip get resolved 
in these next 30 seconds?

If YES: at what approximate second (0-30) does the resolution occur?
If NO: the clip already has a natural ending.

Output: {"resolved_in_extension": bool, "resolution_second": int or null}
```

---

## 10. Ключевые выводы и приоритеты для вашей системы

### Проблема #1 (критическая): Bottom-up assembly не может обеспечить closure

Текущий подход — собирать рил из evidence 2–13s — структурно неверен для нарративной завершённости. Evidence — это atomized highlights, не narrative units. Composer пытается решить NP-hard задачу связывания фрагментов в историю.

**Fix**: перейти к top-down chaptering как Stage 0. Сначала понять структуру видео, затем искать лучшие моменты ВНУТРИ структурных единиц.

### Проблема #2 (важная): Closure validator смотрит в неправильном направлении

+8s tail недостаточен. Payoff может быть через 20–40 секунд после последнего evidence. 

**Fix**: closure extension как отдельный Stage с window 30–35s, гибридный (deterministic first, LLM fallback).

### Проблема #3 (архитектурная): MIN_RANKED_ITEMS=60 hardcoded

Это уже зафиксировано в вашем backlog. Но связанная проблема: даже если items правильные, duration ограничена снизу малым размером evidence фрагментов. Нужен явный механизм "expand to closure".

### Проблема #4 (методологическая): Target duration как constraint, не как consequence

OpusClip и академические системы задают duration как *preference*, а реальная длина определяется nарративной структурой. У вас target=30–45s работает как hard constraint.

**Fix**: задать MIN=28s, TARGET=42s, MAX=75s как мягкие предпочтения, позволить closure механизму определять реальную границу.

---

## 11. Ссылки и источники

1. **OpusClip How It Works**: https://www.opus.pro/how-does-opus-clip-work
2. **OpusClip Virality Score**: https://help.opus.pro/docs/article/virality-score
3. **OpusClip Clip Length**: https://help.opus.pro/docs/article/select-clip-length
4. **ClipAnything docs**: https://help.opus.pro/docs/article/9947095-clip-anything
5. **ClipsAI GitHub**: https://github.com/ClipsAI/clipsai
6. **TreeSeg arXiv:2407.12028**: https://arxiv.org/abs/2407.12028 (AugmendTech, 2024)
7. **Chapter-Llama arXiv:2504.00072 / CVPR 2025**: https://arxiv.org/abs/2504.00072
8. **ARC-Chapter arXiv:2511.14349**: https://arxiv.org/abs/2511.14349 (Tencent ARC, 2025)
9. **Human-Inspired Video Editing, EMNLP Industry 2025**: https://aclanthology.org/2025.emnlp-industry.185
10. **VidChapters-7M arXiv:2309.13952**: https://arxiv.org/abs/2309.13952
11. **From Text Segmentation to Smart Chaptering arXiv:2402.17633**: https://arxiv.org/abs/2402.17633
12. **Paragraph Segmentation Revisited arXiv:2512.24517**: https://arxiv.org/html/2512.24517v2
13. **FunClip (Alibaba DAMO)**: https://github.com/modelscope/FunClip
14. **PromptClip (VideoDB)**: https://github.com/video-db/PromptClip
15. **TextTiling (Hearst, 1997)**: https://people.ischool.berkeley.edu/~hearst/research/tiling.html
16. **TikTok Completion Rate by Length**: https://tiktokcalculator.net/data/engagement/completion-rate-by-video-length/
17. **OpusClip blog — TikTok length format retention**: https://www.opus.pro/blog/tiktok-length-format-retention-data
18. **Vizard Spark 1.0**: https://vizard.ai/spark
19. **VideoHighlighter GitHub**: https://github.com/Aseiel/VideoHighlighter
20. **Prompt2Clip GitHub**: https://github.com/Jit-Roy/Prompt2Clip

---

*Отчёт подготовлен 2026-04-21. Данные по duration distribution основаны на публично доступных user reports и платформенной аналитике, не на официальных внутренних метриках компаний.*
