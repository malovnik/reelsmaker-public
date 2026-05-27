# REFACTR-21 — VideoToolbox HEVC encode + software fallback

> **Этап:** 03 — Бэкенд: рендер и безопасность
> **Шаг:** 22 из 67
> **Зависимости:** REFACTR-10 (ADR видеодвижок).
> **Следующий шаг:** REFACTR-22 (VBR/CRF оптимизация)

---

## Роли

### R-RENDER-ENG — Рендер-инженер
**Профессия:** Специалист по ffmpeg, VideoToolbox, h264/hevc-кодекам.
**Soul:** Каждый кадр — ресурс. Hardware encode — не роскошь, а стандарт на Apple Silicon.

### R-BACKEND-SURGEON (консультативно)
**Soul:** Вызовы ffmpeg — через аргументный массив (argv), никакой конкатенации строк, никакого shell-режима.

---

## ТРИЗ-принцип

*Принцип использования ресурсов.* M5 Pro имеет Media Engine. Использовать его — обязательство, не опция. Fallback на software нужен только для случаев headless/CI/отключённого VideoToolbox.

---

## Оркестрация

**Режим:** Sequential + Context7 (ffmpeg docs).

---

## Микрозадачи

### 21.1 Детектор VideoToolbox

Создать модуль `services/render/encoder_detection.py` с асинхронной функцией `detect_videotoolbox() -> bool`. Реализация: запуск `ffmpeg -hide_banner -encoders` через `asyncio.create_subprocess_exec` (argv-массив, без shell), поиск подстроки `hevc_videotoolbox` в stdout. Результат кешируется в `runtime_settings` при первом запуске приложения.

### 21.2 Encoder strategy

Модуль `services/render/encoder_strategy.py`:

- Enum `EncoderChoice` с тремя значениями: `videotoolbox_hevc` (default при наличии), `libx265` (fallback 1), `libx264` (fallback 2, крайний).
- Функция `pick_encoder(settings)` принимает текущие `RuntimeSettings` и возвращает выбор. Приоритет: forced software → `libx265`; VideoToolbox доступен → `videotoolbox_hevc`; иначе `libx265`.

### 21.3 Параметры ffmpeg

Модуль `services/render/ffmpeg_builder.py` — функция `build_ffmpeg_args(input_path, output_path, encoder, bitrate_mbps, fps)`, возвращает `list[str]` (argv).

Для `videotoolbox_hevc`:
- `-c:v hevc_videotoolbox`
- `-b:v {bitrate}M`, `-maxrate {bitrate*1.33}M`, `-bufsize {bitrate*2}M`
- `-tag:v hvc1`, `-pix_fmt yuv420p10le`
- `-colorspace bt709`, `-color_range tv`

Для `libx265`: `-c:v libx265 -crf 23 -preset medium`.
Для `libx264`: `-c:v libx264 -crf 21 -preset medium`.

Аудио — везде: `-c:a aac -b:a 192k`.

### 21.4 Интеграция в рендер

Обновить `services/project_renderer.py` (или `renderer.py` — что используется) так, чтобы он использовал `build_ffmpeg_args`. Убрать любые хардкод ffmpeg-строки. Вызов процесса — через `asyncio.create_subprocess_exec(*args)`, без shell.

### 21.5 Progress streaming

Прогресс парсится из stderr по шаблону `frame=... fps=... time=HH:MM:SS.sss`. Каждая строка → событие в `job_event_bus` → SSE-клиенту.

### 21.6 Тесты

- [ ] `detect_videotoolbox()` на M5 возвращает True.
- [ ] `build_ffmpeg_args` генерирует корректный argv для каждого encoder (сравнить с эталонным списком).
- [ ] Smoke: рендер 5-сек тестового видео через hevc_videotoolbox → output файл валиден (проверка через `ffprobe`).
- [ ] Force software path: установить env-переменную `FORCE_SOFTWARE_ENCODE=1` → используется libx265.

### 21.7 Commit + Serena memory + лог

---

## GATE-чекпоинт

- [ ] Detector работает.
- [ ] Encoder-strategy корректно выбирает.
- [ ] Builder генерирует правильный argv.
- [ ] Smoke-рендер 5-сек даёт валидный HEVC-файл.
- [ ] Все subprocess-вызовы argv-only (подтверждено grep'ом).
- [ ] Tests зелёные.

---

## Артефакт на выходе

Encoder detection + strategy + builder + интеграция в рендер + тесты.
