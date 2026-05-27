# Editing quality research — рабочие заметки

**Дата:** 2026-04-19
**Контекст:** постановка задачи от пользователя по общему качеству монтажа (НЕ только аудио)
**Статус:** собирает research (два параллельных агента)

---

## Постановка задачи от пользователя (цитата переосмыслена)

> Очень сложно угадать, где-то чётче микрофон ловил звуки, где-то слабее, где-то я сглатывал концовки, где-то не сглатывал. Каждый раз чуть-чуть, но по-другому.

> Есть уже на рынке какая-то ML или не ML оценивающая анализирующая звуковую дорожку? И делать сделать автоматический анализ и автоматическую настройку, чтобы были прям супер гладкие.

> Я хочу добиться, как будто человек сидел, резал, накладывал. То есть гибкие J-cuts, L-cuts где-то 0.2 секунды, где-то 0.5 секунды, где-то 0.3 секунды. Гибкие срезки слов, гибкие настройки воздуха, пауз между словами, сколько оставлять там.

> Короче сделать не только алгоритмическую действительно такую умную систему анализа, которая нам будет выдавать не только идеальные по контенту рилс (сейчас они неплохие) но и давать нам максимально гладкую картинку. Потому что сейчас как бы не настраивался он — где-то слово съел, где-то тыкнула, где-то цыкнула, где-то наслоение какое-то лишнее произошло.

> И вот что сейчас я увидел — он стал хуже работать в плане того что он стал вырезать из разных частей куски, но части сами по себе уже тем это разные были. То есть он работать стал как телевизионщик — вот знаешь как на телевидении отсюда контекста вырезал отсюда слепил получился скандал.

**Уточнение после моего узкого ответа:**

> Смотри у меня такое ощущение что ты чисто про качество аудио а я говорю вообще про качество монтажа и качество нарезок.

> Это мы уже сменили тему с машинного обучения. Это у нас другая тема — консистентность, гладкость, профессиональность. Как смотрится рилс — что это профессиональный монтажёр делал или машина просто нарезал алгоритм. Гибкость — в одном рилсе где-то такая длина переходов, где-то такая длина переходов.

---

## Два направления (уточнено 2026-04-19)

### A) Editing craft (широкое) — главное

Вопрос «профессиональный монтажёр vs машина». Включает:

- **Pacing в рамках одного рилса** — не фиксированный cut-rhythm, а dramaturgically variable: hook punchy, развитие спокойнее, climax снова быстрее
- **Длина планов (shot duration)** — разные в зависимости от content density
- **Visual transitions** — hard cut vs J/L-cut vs dissolve vs dip-to-black vs match-cut (T2.6 уже есть инфра)
- **Breathing room** — где удержать кадр после фразы, где резко оборвать
- **Emphasis zoom / scale / pan** — тонкие motion-effects на ключевых словах
- **Cut continuity** — eye-trace, motion continuity между кадрами
- **Rhythm matching** — под beat аудио (T2.5 уже есть) + под prosody (интонация)
- **Consistency signature** — все рилсы из одного job должны ощущаться как один монтажёр делал, не раздрай в стилях

### B) Audio cleanup (узкое подмножество A)

То что я написал в первой итерации:
- Adaptive pause/breath/filler thresholds
- Mouth sound detection
- Context-aware keep_sec
- Loudness levelling

Это ВАЖНАЯ часть, но не полная картина. Audio cleanup ≈ 30% от общего «как будто человек резал». Остальные 70% — visual pacing / rhythm / transitions / emphasis.

---

## Мои заметки из предыдущих ответов (сохраняю чтобы не забыть)

### Что уже знаю про audio (базовые ответы)

**iZotope RX 11** — индустриальный стандарт ручной резки (Mouth De-click, De-ess, Dialog Isolate, Breath Control). GUI, не API.

**Open-source 2026:**
- `noisereduce` (Python, spectral gating) — постоянный шум
- DeepFilterNet 3 (MIT, 2024) — real-time neural denoiser
- Facebook Denoiser / demucs — тяжелее, качество выше
- auto-editor (MIT, Python) — автоматическая нарезка по VAD (reference)

**Коммерческий компромисс:** Auphonic API ($10-30/мес, Python client) — Adaptive Leveler + Filter + Cougher. Может быть проще звать их чем портировать.

**Ключевое открытие:** у нас уже есть whisper word-level timestamps + confidence + punctuation. Значит можно:
- Per-word confidence как сигнал «articulation cut vs bad mic»
- `avg_logprob` → маркировка «сглатанного» endings
- Punctuation → context-aware keep_sec (точка > запятая > внутри предложения)

Это **не требует новых моделей**. Только логика на existing data.

### 4 дополнения которые я обещал добавить

1. **Crossfade 20-40мс** на границах cut через `acrossfade` FFmpeg — убирает «click» на стыке
2. **Transient preservation** — обрезать по zero-crossing на согласных (к/т/п/с), не по timestamp
3. **Speaker continuity check** — pitch-continuity через librosa между сегментами рилса → warning для cross-context
4. **Dynamic noise floor calibration** — первые 0.5 сек каждого chunk замерять ambient noise, подстраивать VAD threshold локально

### Про composer mode (T9)

Opus Clip: «ClipAnything» vs «Long-to-Shorts». Descript: «Timeline edit» vs «Story mode». Индустрия называет по-разному, но паттерн общий — user выбирает уровень свободы composer'а.

У нас уже инфраструктура:
- `_candidate_scoring` в `reels_composer.py` — добавить `context_distance_penalty`
- `runtime_settings.py` — enum `composer_strategy: tight_context | balanced | thematic_free`
- UI — toggle в UploadWizard

1-2 дня работы, no research required — архитектурная задача.

---

## Что research агенты изучают (запущено 2026-04-19)

### Агент 1 (запущен первым — узкий scope на audio)
`a364748cc5bec5395` — ищет библиотеки 2026 по audio:
- Click/pop/lip-smack detection (Demucs, DeepFilterNet, `noisereduce`)
- Adaptive breath classification (AEBSR, wav2vec2)
- Adaptive loudness levelling (open-source Auphonic альтернативы)
- Dropped word endings detection
- Context-aware pause retention
- J/L-cut rules из индустрии

Работает в фоне, результат положим в `docs/research/adaptive-audio-editing-2026.md`.

### Агент 2 (будет запущен сейчас — широкий scope на editing craft)
Будет искать:
- Pacing/rhythm analysis в AI-editors (Opus Clip, Gling, Descript, Pictory)
- Shot duration decision models
- Visual transition AI (когда hard cut vs J/L vs dissolve vs match-cut)
- Emphasis motion effects (Ken Burns, punch-in zoom, pan) — автоматические rules
- Eye-trace и motion continuity analysis
- Librosa/MIR для rhythm matching с prosody
- Industry references (MKBHD, Casey Neistat, Vox, Kurzgesagt — разные editing signatures)
- Консистентность стиля между рилсами одного job

Результат попадёт в `docs/research/editing-craft-2026.md`.

---

## План черновой (перепишется после обоих research)

- **T8 — Audio cleanup** (узкий, ~30% проблемы): mouth-sound detector, adaptive breath, context-aware keep_sec, adaptive loudness, dynamic noise floor
- **T9 — Composer context mode** (архитектурный, no research): tight/balanced/thematic_free
- **T10 — Editing craft system** (НОВЫЙ, широкий): variable pacing, smart transitions, emphasis motion, rhythm matching, consistency signature

T10 будет главной темой после research-отчёта агента 2.

---

## Итог

Пользователь хочет НЕ «чистый звук», а **monteur-grade output**. Это ремесло, а не processing. Research должен дать:

1. Какие библиотеки/модели/правила существуют для auto-pacing
2. Как AI-editors делают variable cut-rhythm
3. Где граница между «алгоритм нарезал» и «человек резал»
4. Что можно реально автоматизировать в 2026, что нельзя

После research — единый план T8+T9+T10 с приоритизацией по effort/impact.
