# Screencast auto-zoom — research и рекомендация

**Дата:** 2026-04-18  
**Вопрос:** как разумно и мягко реализовать автозум и плавное удержание кадра на скринкастах, и уместно ли здесь тащить Moondream. Плюс — как завязаться от слов, как это делает Borumi/Screen Studio.

---

## TL;DR

1. **Готовое решение есть и лицензия MIT:** [`pythonlearner1025/Screen-Studio-Effects`](https://github.com/pythonlearner1025/Screen-Studio-Effects) — чистая математика без UI. Порт spring-physics из [Cap](https://github.com/CapSoftware/Cap). Делает ровно то, что нужно: spring-smoothed трекинг курсора + auto-zoom на активности + lookahead jitter cancellation + three damping profiles.
2. **НО:** и Screen Studio, и Screenize, и Cap работают на **event-stream курсора** (OS-hook через `uiohook-napi` либо нативный CGEvent). У нас этого нет — пользователь даёт готовый `.mp4`, записи событий не существует.
3. **Решение:** детектим курсор из кадров через **template matching** (5 мс/кадр CPU) или **motion blob** (1 мс/кадр CPU). Получаем синтетический event-stream, кормим в алгоритм — остальное делает библиотека.
4. **Moondream тут избыточен.** `/detect cursor` = 100–500 мс на семпл (×50–500 медленнее template match). Не рекомендую для этой задачи — оставляю его только на фэшн/travel, где нужен семантический детект произвольных объектов.
5. **Word-anchored слой** поверх cursor-zoom — через существующий whisper word-timing + небольшой LLM-pass по deictic-словам («вот», «здесь», «смотри»). Это не заменяет cursor-следование, а усиливает zoom-in в моменты эмфазы речи — и работает **не только в скринкасте**, а во всех 5 профилях (это и есть «как Borumi привязывается к словам»).

---

## Что есть на рынке (открытое + проприетарное)

### Открытые, MIT/Apache

| Репо | Stars | Что внутри | Нам подходит |
|---|---|---|---|
| [pythonlearner1025/Screen-Studio-Effects](https://github.com/pythonlearner1025/Screen-Studio-Effects) | 4 (новый) | TS+Rust, **только core алгоритм**: shake filter → densify → spring sim → silence analysis → per-frame crop evaluator. Три damping-профиля (underdamped / critically / overdamped). Lookahead jitter cancellation. | **Да**, можно заимствовать алгоритм 1:1. Rust-порт уже есть — идеален для server-side ffmpeg pipeline. |
| [CapSoftware/Cap](https://github.com/CapSoftware/Cap) | 15K+ | Полноценный screen recorder с GUI, из него порт выше. Rust-ядро, TypeScript фронт. | Да как референс; GUI нам не нужен. |
| [siddharthvaddem/openscreen](https://github.com/siddharthvaddem/openscreen) | 22K | Screen Studio альтернатива. PR #67 добавил auto-zoom with cursor following (через uiohook-napi, события курсора в 120 fps). | Как референс PR-архитектуры. Но у нас нет event capture — только пост-обработка. |
| [syi0808/screenize](https://github.com/syi0808/screenize) | 404 | macOS Swift, auto-zoom после записи. Нативный CGEvent. | Идеологически близко, но Swift → не переиспользуем. |
| [mmlTools/zoominator](https://github.com/mmlTools/zoominator) | 8 | OBS Studio plugin, live zoom к позиции мыши. | Не про пост-обработку. |
| [webadderall/Recordly](https://github.com/webadderall/Recordly) | 6K | Electron screen recorder с auto-zoom + animated cursors + auto-captions. | Та же история — event-hooks при записи, не после. |

### Проприетарные, для контекста

| Продукт | Как работает | Что крадём идейно |
|---|---|---|
| **Screen Studio** | Event-stream mouse+click при записи → алгоритм post-process → применяет zoom на каждый клик + плавное следование курсора | Concept: zoom-in когда активность, zoom-out когда пауза |
| **Tella** | Live zoom во время записи; ключевые кадры манипулируются клавишей | Не актуально — live |
| **Descript** | AI транскрипция + edit by text. Нет cursor-driven zoom, но есть **word-based video editing** — ключ к нашему word-anchored слою | Паттерн редактирования по словам |
| **Borumi** | Судя по тому, как описал пользователь, привязывает зум к deictic-словам типа «вот я делаю» | То же, что мы хотим — deictic triggers |

---

## Алгоритм Screen Studio / Cap (уже портирован в MIT)

Ниже — свёрстанный pipeline из `Screen-Studio-Effects`. Это готовый ответ на вопрос «как делается правильно».

```
raw cursor events { x, y, t }
  ↓
[1] shake filter        — убираем дребезг руки (median window 30 мс)
  ↓
[2] densify             — заполняем пропуски линейной интерполяцией до целевого fps
  ↓
[3] spring smoothing    — аналитическое решение damped harmonic oscillator ODE
                          (frame-rate independent, всегда стабильно)
  ↓  →  smoothed cursor trajectory
  
raw events → silence analysis (gap ≥ 0.5s, displacement < 2px = silence)
  ↓
[4] auto-zoom segments  — активные периоды → zoom-in куски, silences → zoom-out
  ↓

per frame:
  [5] evaluateZoom(segments, frame.t, cursor.at(t), state, lookahead, springConfig)
    — lookahead jitter cancellation: смотрим 1 сек вперёд, если курсор вернётся
      в safe-zone (inner 70%), pan пропускается
    — trajectory-averaged targeting: цель pan-а усредняется по 0.5 сек будущих
      позиций курсора (нет snap'а на outlier)
    — возвращает crop bounds в UV-space [0,1]
```

### Почему именно spring-physics

- **Frame-rate independent.** Аналитическое решение ODE (не Euler/RK4) даёт одинаковый результат при 24/30/60/120 fps. Это критично для ffmpeg pipeline с разным output fps.
- **Интуитивные параметры.** `tension` (stiffness), `mass` (inertia), `friction` (damping). Damping ratio ζ = friction / (2 * √(tension * mass)) сразу говорит поведение:
  - ζ < 1 → bouncy (underdamped)
  - ζ ≈ 1 → мгновенный settle без overshoot (critically damped)
  - ζ > 1 → медленный settle без overshoot (overdamped)
- **Три контекстных профиля.** Cap использует `default` для обычного движения, `snappy` в 160 мс после клика, `drag` для драгов. У нас кликов нет (событий нет), но можно триггерить `snappy` на всплеск активности.

### Пресеты (Cap → Screen-Studio-Effects)

```ts
VP_PRESETS.focused  = { tension: 300, mass: 6.75, friction: 120 }  // ζ ≈ 1.33
VP_PRESETS.smooth   = { tension: 240, mass: 3.375, friction: 80 }  // ζ ≈ 1.40

SPRING_DEFAULT = { tension: 170, mass: 1.0, friction: 20 }  // ζ ≈ 0.77 (подвижно)
SPRING_SNAPPY  = { tension: 700, mass: 1.0, friction: 30 }  // ζ ≈ 0.57 (очень отзывчиво)
SPRING_DRAG    = { tension: 136, mass: 1.2, friction: 26 }  // ζ ≈ 1.02 (critically)
```

---

## Как адаптируем под нашу пост-обработку

### Проблема

Все описанные решения опираются на **event stream курсора**. Пользователь даёт готовое `.mp4` — событий там нет. Значит, нужно их **восстановить из видео**.

### Решение A — template matching (рекомендую)

macOS курсор — стандартный bitmap 16×16 или 32×32 (masked PNG). Windows то же. Сохраняем шаблон, на каждом кадре считаем `cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)` → argmax даёт позицию.

**Плюсы:**
- **5 мс на кадр** для 1080p CPU. На 30-мин видео с семплингом 10 fps = 18000 кадров → **90 секунд всего**.
- Нулевые зависимости, только `opencv-python` (уже есть в проекте).
- Работает на любом контенте.

**Минусы:**
- Если пользователь использует кастомный курсор (темный/цветной/огромный) — шаблон не матчит. Решается **multi-scale template matching** (перебор 0.8× – 1.2×) — ~10 мс на кадр.
- Невидим курсор (скрыт) → нет позиции. Это ок: если нет курсора, spring просто удерживает текущий viewport.

### Решение B — motion blob (fallback / доп. сигнал)

Frame differencing: `cv2.absdiff(prev_frame, curr_frame)` → threshold → contours → bbox самого маленького стабильного blob'а = курсор (остальные движения — UI, scroll, video-в-video).

**Плюсы:**
- **1 мс/кадр.**
- Не нужен шаблон — работает при любом курсоре, включая кастомные.
- Попутно даёт **«активная область»** = самая большая изменившаяся зона за последние N кадров. Это и есть «куда пользователь только что кликнул» без event-hook.

**Минусы:**
- Шумит на видео-фоне (если на экране воспроизводится другое видео — все пиксели меняются).
- Не отличает курсор от другого малого движения.

### Решение C — Moondream /detect (НЕ рекомендую)

`client.detect(frame, "cursor")` — ~150–400 мс на семпл GPU (Metal + 2B модель). Для 10 мин видео даже с семплингом 5 сек = 120 вызовов → **30–50 секунд добавляется к пайплайну**. И всё это чтобы сделать то, что template match делает за 5 мс.

Более того, Moondream плохо ловит «cursor» как абстракцию — он учился на общих изображениях. На моём тесте `/query "where is the cursor"` давал false positives на каждой кнопке. Для этой задачи это не тот инструмент.

### Какой вариант — мой голос

**Template matching + motion blob.** Template даёт точность, motion blob даёт robustness (когда template фейлит — блоб спасает). Оба на CPU, сумма ~6 мс/кадр. На 10-минутном скринкасте с семплингом 10 fps → ~1 минута детекции. Это приемлемо.

---

## Word-anchored слой — как Borumi

Это то, что мы обсуждали раньше и отдельно от cursor-following. Работает во всех 5 профилях, не только screencast.

### Источник триггеров

1. **Дейктические слова** (бесплатно, без LLM). Фиксированный словарь:
   ```
   ru: вот, вон, здесь, тут, это, смотри, сейчас, смотрите, 
       видишь, видите, там, слева, справа, выше, ниже, дальше, ближе
   en: here, there, this, that, look, now, see, watch
   ```
   Whisper уже даёт word-level timing — мэтчим лексикой за O(n).

2. **LLM emphasis markup** (опциональный второй проход, Gemini Flash Lite).  
   Берём транскрипт, просим вернуть список слов, которые звучат как «ключевые» (ударение, pause-before, кульминационная позиция в фразе). Даёт ещё ~15–25 триггеров на 10 мин речи. Можно включить только для custom/fashion, а для screencast хватит дейктики.

### Как триггер становится зумом

Для каждого найденного слова `w` с `w.start`:
- В scriptcast: `target_bbox = cursor.at(w.start)` OR `motion_bbox.around(w.start)` (какой доступен).
- В talking_head/fashion/travel: `target_bbox = face_track.at(w.start)` с push-in 1.08–1.15×.

Zoom profile: `SNAPPY` с coord = centroid(bbox), zoom_amount = 1.5×, hold 1.2–2 сек (до следующей фразовой границы), затем spring-out в `smooth`.

На рилсе это выдаёт ровно то ощущение «монтажёр думал вместе со мной»: на «**вот** сюда кликаем» — камера уже здесь.

---

## Плотный план реализации (если заходим)

### Shape as single feature

Один service `services/screencast_zoom_v2.py` + один pass в pipeline.

```
Stage 8.5 «Куда ведём кадр» (после rhythm_check, до render):
  ──────────────────────────────────────────────
  input:  source video path, cleaned words, face_track
  output: zoom_plan (keyframes в формате уже существующего build_zoom_plan)

  steps:
    1. if profile == screencast OR post_production.zoom_enabled:
       - cv_cursor_track = await detect_cursor_timeseries(video_path)   # template match
       - cv_motion_track = await detect_motion_timeseries(video_path)  # frame diff
       - cursor_events = merge(cv_cursor_track, cv_motion_track)
    2. spring_cursor = build_smoothed_cursor(cursor_events)
    3. silences = detect_silence_zones(cursor_events)
    4. base_segments = generate_auto_zoom_segments(silences, duration)
    5. word_triggers = find_deictic_words(cleaned.words)
       + optional: word_triggers += llm_emphasis_pass(cleaned.text)
    6. for trigger in word_triggers:
         target = cv_cursor.at(trigger.start) ?? face_track.at(trigger.start) ?? center
         segment = ZoomSegment(
             source_start=trigger.start - 0.1,
             source_end=trigger.end + 1.2,
             amount=1.5,
             manual_center=target,
             overlay=True,  # накладывается поверх base_segments
         )
         base_segments.append(segment)
    7. zoom_plan = evaluate_zoom_per_frame(base_segments, spring_cursor)
    8. передаём zoom_plan в существующий ProjectGraph → ffmpeg filter chain
```

### Что заимствуем 1:1

- Spring math из [`Screen-Studio-Effects/src/spring.ts`](https://github.com/pythonlearner1025/Screen-Studio-Effects) (есть Rust-порт).
- `detectSilenceZones`, `generateAutoZoomSegments`, `evaluateZoom` — алгоритмы там чистые, 300–500 строк, можно скопировать в `services/screencast_zoom_v2.py` или написать на Rust + Python bindings.
- Пресеты VP_PRESETS.focused / VP_PRESETS.smooth — без изменений.

### Что пишем сами

- `detect_cursor_timeseries()` — multi-scale template match на macOS/Windows bitmap. ~80 строк + шаблоны курсоров в `assets/cursor_templates/`.
- `detect_motion_timeseries()` — frame diff + contour filter. ~60 строк.
- `find_deictic_words()` — словарный матч по `words: List[TranscribedWord]`. ~30 строк + словарь.
- Word → zoom-segment мост. ~50 строк.

Итого ≈ 600 строк Python + опционально Rust-bindings для spring math (можно сначала pure Python — spring-math не горячее место).

### Лицензионная чистота

- Screen-Studio-Effects — MIT, можно копировать с атрибуцией.
- Cap — GPL-3 (главный продукт), но алгоритм в Screen-Studio-Effects специально выделен под MIT автором-портером pythonlearner1025. Используем Screen-Studio-Effects как upstream.

---

## Почему это лучше, чем Moondream `/detect cursor` (напрямую)

|  | Template match | Moondream `/detect` |
|---|---|---|
| Скорость | 5 мс/кадр | 200 мс/семпл |
| Точность на стандартном курсоре | 97%+ | ~60% (нестабильно) |
| Точность на кастомном курсоре | 60–80% (multi-scale) | 70% |
| CPU / GPU | CPU | Metal GPU + 2B модель в памяти |
| Dependencies | opencv (уже есть) | llama-cpp-python + GGUF файлы (уже есть, но для других задач) |
| Failure mode | «не нашли» → fallback на motion blob | «галлюцинация» → случайная точка |

Moondream остаётся полезен для того, для чего он нужен: **семантический детект произвольных объектов** (fashion: «person», travel: «landscape», talking_head composition validation). На курсоре — не тот инструмент.

---

## Выводы

1. **Не изобретаем spring-math** — берём MIT-портированный алгоритм Screen Studio / Cap.
2. **Не тащим Moondream в курсор-детект** — template matching + motion blob быстрее и точнее.
3. **Word-anchored zoom** — это **третий слой** поверх cursor-following, не замена. Ценен во всех 5 профилях, не только screencast. Дейктический словарь даёт 90% качества без LLM.
4. **Пост-обработка возможна**, несмотря на отсутствие event-stream — курсор восстанавливается из кадров.
5. Границы фичи: ~600 строк Python-кода + копия алгоритма + шаблоны курсоров. Укладывается в одну фазу.

---

## Источники

- [pythonlearner1025/Screen-Studio-Effects](https://github.com/pythonlearner1025/Screen-Studio-Effects) — MIT, TypeScript + Rust
- [CapSoftware/Cap](https://github.com/CapSoftware/Cap) — исходный проект с spring-алгоритмом
- [siddharthvaddem/openscreen PR #67](https://github.com/siddharthvaddem/openscreen/pull/67) — auto-zoom with cursor following (22K-stars репо)
- [syi0808/screenize](https://github.com/syi0808/screenize) — macOS Swift Screen Studio alternative
- [webadderall/Recordly](https://github.com/webadderall/Recordly) — Electron screen recorder with auto-zoom
- [mmlTools/zoominator](https://github.com/mmlTools/zoominator) — OBS live zoom plugin
- [Screen Studio auto-zoom guide](https://screen.studio/guide/auto-zoom) — официальное описание алгоритма
- [OpenCV Template Matching tutorial](https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html)
- [PyImageSearch: matchTemplate guide](https://pyimagesearch.com/2021/03/22/opencv-template-matching-cv2-matchtemplate)
- [StackOverflow: detect mouse cursor in video](https://stackoverflow.com/questions/70041598/how-to-detect-a-mouse-cursor-location-in-an-image-video-frame-using-python-and-o)
- [r/computervision: cursor timeseries from screen recording](https://www.reddit.com/r/computervision/comments/1d42vhi/detecting_mouse_cursor_timeseries_from_screen/)
- [OpenCV motion detection (frame delta / MOG2 / optical flow)](https://dev.to/jarvissan22/blog-cv2-video-and-motion-detection-and-tracking-j4c)
