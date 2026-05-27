# REFACTR-10 — ADR: Видеодвижок на M5 Pro (VideoToolbox + fallback)

> **Этап:** 01
> **Шаг:** 11 из 67
> **Зависимости:** REFACTR-05 (pipeline stages).
> **Следующий шаг:** REFACTR-11 (ADR: Темы)

---

## Роли

### R-ARCHITECT
**Soul:** Рендер — bottleneck. Если не ускорим здесь — никакой UI-редизайн не спасёт user experience.

### R-RENDER-ENG — Рендер-инженер
**Профессия:** Специалист по видеокодекам, ffmpeg, VideoToolbox.
**Soul:** Hardware encode на Apple Silicon — не опция, а обязательство. Software HEVC на 60-мин видео — это 2+ часа. VideoToolbox — это минуты.

---

## ТРИЗ-принцип

*Принцип использования ресурсов.* M5 Pro содержит Media Engine (VideoToolbox-accelerator). Не использовать его = игнорировать 60% возможностей железа.

---

## Оркестрация

**Режим:** Sequential + Context7 (ffmpeg).

---

## Микрозадачи

### 10.1 Варианты энкодера

**Вариант A: software libx265 (текущий?)**
- + универсален
- − медленный, ест CPU

**Вариант B: hardware hevc_videotoolbox**
- + в разы быстрее
- − специфические параметры (CRF не поддерживается напрямую, используется bitrate)

**Вариант C: h264_videotoolbox + транскод в HEVC post-hoc**
- Оверкилл и бессмысленно.

### 10.2 Context7: ffmpeg VideoToolbox

- [x] Проверено локально: `ffmpeg 7.1.1` с `--enable-videotoolbox` — доступны `h264_videotoolbox`, `hevc_videotoolbox`, `prores_videotoolbox`.
- [x] Зафиксированы параметры двух профилей (см. ADR):
  - `publer_direct`: `-c:v h264_videotoolbox -tag:v avc1 -b:v 12M -maxrate 17M -bufsize 24M -pix_fmt yuv420p -r 30 -allow_sw 1 -realtime 0 -prio_speed 0`.
  - `archive_hevc`: `-c:v hevc_videotoolbox -tag:v hvc1 -b:v 15M -maxrate 20M -bufsize 30M -pix_fmt yuv420p10le -r 30 -allow_sw 1 -realtime 0 -prio_speed 0`.
- [x] Detection-команда: `ffmpeg -hide_banner -encoders | grep -E "videotoolbox|libx26[45]"`.

### 10.3 Fallback-стратегия

**Два профиля, каждый со своей лестницей** (архитектурная корректировка — `export_presets.yaml:6` уже переключён на `h264_videotoolbox` в commit `b3a97c1` ради Publer ≤200 MB; один профиль не покрывает оба use-case):

- `publer_direct`: `h264_videotoolbox` → `libx264 -crf 21 -preset medium`.
- `archive_hevc`: `hevc_videotoolbox` → `libx265 -crf 23 -preset medium -pix_fmt yuv420p10le` → `libx264 -crf 21 -preset slow` (крайний 8-bit).
- Detection кешируется в `runtime_settings.encoder_capabilities` (REFACTR-21).

### 10.4 Параметры качества

- `publer_direct`: 12 Mbps VBR — 90-с рилс ≈ 135 MB, влезает в Publer `POST /media` ≤200 MB.
- `archive_hevc`: 15 Mbps VBR 10-bit — mastering-качество для архива/YouTube 4K.
- VBR (`-b:v` + `-maxrate` + `-bufsize`) вместо CRF-like `-q:v` для детерминированного размера.

### 10.5 Потоковый рендер (streaming)

- [x] Прогресс через stderr parsing `frame=N ... time=HH:MM:SS speed=Xx` → пример regex зафиксирован в ADR.
- [x] SSE-events через существующий `JobEventBus.mark_stage_progress` (REFACTR-05).

### 10.6 Написать ADR

`docs/adr/0004-video-engine.md` — создан (≈350 строк, MADR).

### 10.7 Serena memory

- [x] `write_memory(name="refactr-10-adr-video-engine", content="...")`.

---

## GATE-чекпоинт

- [x] ADR-0004 принят (status ACCEPTED).
- [x] Параметры VideoToolbox зафиксированы для двух профилей (`publer_direct` H.264 12 Mbps + `archive_hevc` HEVC 15 Mbps 10-bit); M-chip flags `-allow_sw 1 -realtime 0 -prio_speed 0` сохранены из текущего `filter_graph_builder.py:555-565`.
- [x] Fallback-лестница описана для каждого профиля (таблица в ADR §Fallback-таблица).
- [x] Detection-команда: `ffmpeg -hide_banner -encoders | grep -E "videotoolbox|libx26[45]"` + programmatic через `EncoderDetector` (REFACTR-21).

---

## Артефакт на выходе

`docs/adr/0004-video-engine.md`.
