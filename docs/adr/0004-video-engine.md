# ADR-0004 — Видеодвижок на Apple Silicon (VideoToolbox + fallback-лестница)

- **Статус:** ACCEPTED
- **Дата:** 2026-04-24
- **Авторы:** R-ARCHITECT, R-RENDER-ENG
- **Связанные ADR:** [0001 Frontend Stack](./0001-frontend-stack.md), [0002 Data Storage](./0002-data-storage.md)
- **Связанный чанк:** REFACTR-10 (Этап 01, шаг 11/67)
- **Реализация:** REFACTR-21 (VideoToolbox encode — `encoder_detection` + `encoder_strategy` + `ffmpeg_builder`), REFACTR-22 (параметры качества ≥15 Mbps mastering)

---

## Контекст

Рендер — bottleneck pipeline. 60-минутное видео нарезается в 15-30 рилсов, каждый рилс 30-90 с. Без hardware-acceleration на Apple Silicon software HEVC требует 2-4× realtime (60-мин сорс → 2-4 часа рендера) и забивает 8 CPU-потоков. С VideoToolbox — 8-12× realtime (60-мин сорс → 5-7 минут), загрузка CPU <30%, Media Engine (аппаратный блок) делает всю работу.

**Текущая инсталляция (2026-04-24):**

| Параметр | Значение |
| --- | --- |
| Железо | Apple M5 (10 cores: 4P + 6E, 24 GB unified memory) |
| ffmpeg | 7.1.1 (homebrew, `--enable-videotoolbox --enable-audiotoolbox --enable-neon`) |
| Доступные encoders | `h264_videotoolbox`, `hevc_videotoolbox`, `prores_videotoolbox`, `libx264`, `libx265` |
| Текущий default (`export_presets.yaml:6`) | `h264_videotoolbox` + `avc1` tag + 12 Mbps (fix `b3a97c1` для Publer) |
| Текущий fallback в коде (`renderer.py:54`) | `hevc_videotoolbox` (используется, если YAML перезаписан) |
| Publer path (`publer/media_uploader.py:98-116`) | `h264_videotoolbox` с target bitrate для ≤150 MB |
| Detection (`api/routes/health.py:60`) | `ffmpeg -encoders | grep hevc_videotoolbox` |
| M-chip flags (`filter_graph_builder.py:555-565`) | `-allow_sw 1 -realtime 0 -prio_speed 0` |

**Ключевой конфликт разрешается архитектурно:**

- Чанк `REFACTR-10` просит «hevc_videotoolbox default + libx265 fallback + libx264 крайний».
- Реальность кода (после fix `b3a97c1`): Publer direct-upload не принимает HEVC >200 MB → пришлось переключить default на H.264 12 Mbps.

**Решение:** ADR фиксирует **два render-профиля**, а не один. Пользователь выбирает сценарий, каждый профиль имеет свою fallback-лестницу и параметры.

---

## Движущие критерии решения

1. **Hardware-acceleration обязательна** — software HEVC на Apple Silicon — антипаттерн, игнорирующий 60% возможностей железа (Media Engine + NPU offload).
2. **Publer API-ограничения** — `POST /media` multipart ≤200 MB. 90-секундный HEVC 25 Mbps даёт ~280 MB → не влезает. Нужен отдельный H.264 12 Mbps профиль.
3. **Mastering quality** — для ручного скачивания / архива / других платформ (YouTube Shorts, TikTok direct) нужен HEVC 10-bit ≥15 Mbps.
4. **Fallback для CI / старого macOS** — без VideoToolbox (в Docker, на Linux CI, на старых Macbook) pipeline должен продолжать работать.
5. **Detection кешируется** — `ffmpeg -encoders` вызывается при старте, результат кешируется в `runtime_settings.encoder_available`.
6. **Progress через stderr parsing** — ffmpeg печатает `frame= N fps=M time=HH:MM:SS speed=Xx`, парсим в `JobEventBus` для SSE (инфра из REFACTR-05).

---

## Рассмотренные варианты

### Вариант A — Один профиль `hevc_videotoolbox` (как в чанке)

**FOR:**
- Один путь кода, меньше веток.
- HEVC меньше mb/min → меньше место.
- ffmpeg docs и Apple рекомендуют HEVC для Apple Silicon.

**AGAINST:**
- **Публикация через Publer ломается** — HEVC 25 Mbps × 90 с = 280 MB > 200 MB API-limit. Приходится re-encode обратно в H.264 (это сейчас в `publer/media_uploader.py:78` — костыль).
- Instagram Reels / TikTok не принимают hvc1 через публичные API (только через нативное приложение). H.264 avc1 — lingua franca.
- Один default не покрывает оба use-case.

**VERDICT: ❌ REJECTED.** Игнорирует production-реальность (Publer-интеграция).

---

### Вариант B — Два профиля: `publer_direct` (H.264) + `archive_hevc` (HEVC)

**FOR:**
- **`publer_direct` (по умолчанию):** `h264_videotoolbox` 12 Mbps avc1 → 90-с рилс ≈135 MB → влезает в Publer `POST /media`. Кросс-платформенная совместимость (Instagram/TikTok/YouTube Shorts принимают H.264).
- **`archive_hevc` (опциональный):** `hevc_videotoolbox` 25 Mbps hvc1 10-bit → высокое качество для скачивания/архива/YouTube 4K.
- Pипеline не требует post-hoc re-encoding для Publer — костыль в `publer/media_uploader.py:78` можно оставить как defense-in-depth для случая, когда пользователь выбрал `archive_hevc` и всё равно постит в Publer, но это не основной путь.
- Каждый профиль имеет независимую fallback-лестницу.

**AGAINST:**
- +1 selector в UI (post-production settings «Качество экспорта» — `publer_direct` / `archive_hevc`).
- +1 поле в `settings.json` (`sections.post_production_preset.render_profile`).
- Больше пресетов в YAML (4 aspect × 2 render-profile = 8 пресетов). Но aspect × profile — декартово произведение, реализуется через merging defaults + aspect-overrides.

**VERDICT: ✅ ACCEPTED.**

---

### Вариант C — `h264_videotoolbox` default + транскод в HEVC post-hoc

**FOR:**
- Один основной рендер, HEVC-версия — отдельный async-шаг.

**AGAINST:**
- **Удвоение времени рендера** — 90-с рилс × 2 encode = 2× больше. Нарушает SLA «15 рилсов за 10 мин».
- Двойные I/O-операции — лишние GB на диск.
- Логически избыточно, когда можно сразу выбрать целевой encoder.

**VERDICT: ❌ REJECTED.**

---

## Решение

Принимаем **Вариант B** — два render-профиля с явным выбором пользователя, hardware-first с software fallback.

### Профиль #1 — `publer_direct` (default, 9:16 Reels / Shorts / TikTok)

**Цель:** direct-upload через Publer API (≤200 MB per reel), компактность, universal-совместимость.

**Параметры ffmpeg (argv):**

```
-c:v h264_videotoolbox
-tag:v avc1
-b:v 12M -maxrate 17M -bufsize 24M
-pix_fmt yuv420p
-r 30
-allow_sw 1 -realtime 0 -prio_speed 0
-c:a aac -b:a 192k
-movflags +faststart
```

**Контейнер:** MP4 (`.mp4`).
**Audio:** AAC-LC 192 kbps 48 kHz stereo.
**Container flags:** `+faststart` для веб-стриминга (moov atom в начало).
**Ожидаемый размер:** 90-с рилс ≈ 135 MB (12 Mbps × 90 с / 8 = 135 MB, без overhead).

### Профиль #2 — `archive_hevc` (optional, высокое качество для скачивания / YouTube)

**Цель:** mastering-качество для архива, ручного скачивания, YouTube 4K (HEVC hvc1), apple-native экосистемы.

**Параметры ffmpeg (argv):**

```
-c:v hevc_videotoolbox
-tag:v hvc1
-b:v 15M -maxrate 20M -bufsize 30M
-pix_fmt yuv420p10le
-r 30
-allow_sw 1 -realtime 0 -prio_speed 0
-color_primaries bt709 -color_trc bt709 -colorspace bt709
-c:a aac -b:a 256k
-movflags +faststart
```

**Контейнер:** MP4 (`.mp4`).
**Audio:** AAC-LC 256 kbps 48 kHz stereo.
**10-bit yuv420p10le:** Apple Silicon Media Engine поддерживает Main10, даёт плавные градиенты без banding. Для archive-качества оправдано.
**Ожидаемый размер:** 90-с рилс ≈ 170 MB HEVC 10-bit → **не влезает** в Publer, поэтому explicit mastering-профиль, не для direct-upload.

### Fallback-лестница (для каждого профиля)

**Детектор:** `EncoderDetector` на старте приложения (REFACTR-21):

```python
@dataclass(frozen=True)
class EncoderCapabilities:
    h264_videotoolbox: bool
    hevc_videotoolbox: bool
    libx264: bool
    libx265: bool

async def detect_encoders(ffmpeg_path: str) -> EncoderCapabilities:
    output = await run_capture([ffmpeg_path, "-hide_banner", "-encoders"])
    return EncoderCapabilities(
        h264_videotoolbox="h264_videotoolbox" in output,
        hevc_videotoolbox="hevc_videotoolbox" in output,
        libx264="libx264" in output,
        libx265="libx265" in output,
    )
```

Результат кешируется в `runtime_settings.encoder_capabilities` (не сбрасывается между рендерами).

**Стратегия выбора:**

```python
def select_encoder(profile: RenderProfile, caps: EncoderCapabilities) -> EncoderChoice:
    if profile == "publer_direct":
        if caps.h264_videotoolbox:
            return EncoderChoice("h264_videotoolbox", vt=True)
        if caps.libx264:
            return EncoderChoice("libx264", crf=21, preset="medium")
        raise RuntimeError("No H.264 encoder available")

    if profile == "archive_hevc":
        if caps.hevc_videotoolbox:
            return EncoderChoice("hevc_videotoolbox", vt=True, ten_bit=True)
        if caps.libx265:
            return EncoderChoice("libx265", crf=23, preset="medium", ten_bit=True)
        if caps.libx264:
            return EncoderChoice("libx264", crf=21, preset="slow")  # крайний случай
        raise RuntimeError("No encoder available for HEVC profile")
```

### Fallback-таблица

| Profile | Hardware (default) | Fallback-1 (software) | Fallback-2 (крайний) |
| --- | --- | --- | --- |
| `publer_direct` | `h264_videotoolbox` 12 Mbps VBR avc1 | `libx264 -crf 21 -preset medium` | — (H.264 software — уже крайний) |
| `archive_hevc` | `hevc_videotoolbox` 15 Mbps VBR hvc1 10-bit | `libx265 -crf 23 -preset medium -pix_fmt yuv420p10le` | `libx264 -crf 21 -preset slow` (8-bit degradation) |

### VideoToolbox-специфичные флаги (M-chip)

```
-allow_sw 1       # graceful fallback на software HEVC если VT отказал
-realtime 0       # НЕ realtime-constrained → приоритет качества
-prio_speed 0     # quality > speed
```

Установлены в `filter_graph_builder.py:555-565`, сохраняются.

**Почему `-b:v` (VBR) вместо `-q:v` (CRF-like):**
- `hevc_videotoolbox` поддерживает `-q:v 45-65` (quality scale), но:
  - Non-deterministic size — видео варьируется ±30% между прогонами при одной CRF.
  - Нарушает Publer-ограничение ≤200 MB (нельзя гарантировать размер).
- `-b:v 12M -maxrate 17M -bufsize 24M` — VBR с clamp, размер предсказуем, bufsize 2× maxrate даёт VBR-пикам окно.

### Detection-команда (для troubleshooting / CI)

```bash
ffmpeg -hide_banner -encoders | grep -E "videotoolbox|libx26[45]"
```

Ожидаемый вывод на production M5:

```
V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (codec h264)
V....D h264_videotoolbox    VideoToolbox H.264 Encoder (codec h264)
V....D libx265              libx265 H.265 / HEVC (codec hevc)
V....D hevc_videotoolbox    VideoToolbox H.265 Encoder (codec hevc)
```

Если `videotoolbox` отсутствует — ffmpeg собран без `--enable-videotoolbox`. Решение: `brew reinstall ffmpeg` (homebrew по умолчанию включает VT).

### Streaming / progress-parsing

ffmpeg пишет progress в stderr в формате:

```
frame=  123 fps= 48 q=-0.0 Lsize=   45678kB time=00:00:04.10 bitrate=91234.5kbits/s speed=1.60x
```

Парсинг (сохраняется из REFACTR-05 — `apps/backend/src/videomaker/services/ffmpeg_progress.py`, если существует, иначе создаётся в REFACTR-21):

```python
_FRAME_RE = re.compile(r"frame=\s*(\d+).*time=(\d+):(\d+):(\d+\.\d+).*speed=\s*([\d.]+)x")

async def stream_ffmpeg_progress(proc, on_progress):
    async for line in proc.stderr:
        m = _FRAME_RE.search(line.decode("utf-8", errors="replace"))
        if m:
            frame, hh, mm, ss, speed = m.groups()
            elapsed = int(hh) * 3600 + int(mm) * 60 + float(ss)
            await on_progress(frame=int(frame), elapsed=elapsed, speed=float(speed))
```

Events пробрасываются через `JobEventBus.mark_stage_progress(stage, progress)` в SSE — UI обновляет прогресс-бар.

### Concurrency (параллельные рендеры)

Из `renderer.py:125`: `DEFAULT_RENDER_CONCURRENCY = 2`. Apple Media Engine на M-series держит 2-3 одновременных HEVC-сессии без деградации. Больше — отдача падает (CPU-bottleneck на libass/scale). Сохраняем **2** как default, поле в `runtime_settings.render_concurrency` для тюнинга на других Mac.

---

## Последствия

### Положительные

1. **Два профиля → два use-case без компромиссов.** Publer не ломается (12 Mbps H.264), archive даёт HEVC 10-bit quality.
2. **Hardware-first** — 8-12× realtime на M5, ~30% CPU. Background-pipeline не душит UI.
3. **Graceful degradation** — CI/Docker/старые Mac получают software fallback, pipeline работает везде.
4. **Publer direct-upload без костыля** — не нужен post-hoc re-encode в `publer/media_uploader.py:78`. Оставляем как defense-in-depth для случая `archive_hevc` → Publer, но не основной путь.
5. **Progress через SSE** — UI видит `frame=N speed=Xx` в реальном времени, не мёртвый прогресс-бар.
6. **Детерминированный размер** — VBR с clamp предсказуем, гарантирует Publer-лимит ≤200 MB.

### Отрицательные

1. **+1 UI-selector** — «Качество экспорта» в Post-Production settings. Компенсируется внятным описанием `publer_direct` (для публикации) / `archive_hevc` (для архива/YouTube).
2. **+4 YAML-пресета** (4 aspect × 2 profile = 8, пересечение через defaults-merge) — не критично.
3. **`archive_hevc` → Publer — неявный конфликт** — если пользователь выбрал archive-профиль и включил Publer scheduling, надо показать warning «HEVC >200 MB может не загрузиться в Publer, использовать publer_direct?». Решается в UI (REFACTR-55 Post-Production settings).

### Нейтральные

- **10-bit yuv420p10le** — Apple Silicon Media Engine справляется без деградации скорости vs 8-bit (VT hardware поддерживает Main10 нативно). На software libx265 10-bit замедляет encode на 30-40% — приемлемо для fallback-сценария.
- **AV1** (`av1_videotoolbox`) — Apple поддерживает с M3 Pro, но Instagram/TikTok/Publer пока **не** принимают AV1. Отложено до момента, когда платформы добавят поддержку.

---

## Верификация

Gate-критерии (REFACTR-21 + REFACTR-22):

1. `ffmpeg -encoders | grep videotoolbox` на M5 → 3 строки (h264, hevc, prores). ✅ (проверено 2026-04-24)
2. Рендер 90-с рилса профилем `publer_direct` → файл ≤150 MB, bitrate ≈12 Mbps avg ± 10%, container `mp4`, tag `avc1`.
3. Рендер 90-с рилса профилем `archive_hevc` → bitrate ≈15 Mbps avg ± 10%, container `mp4`, tag `hvc1`, pix_fmt `yuv420p10le`.
4. Publer direct-upload profile `publer_direct` → `POST /media` возвращает 200 + media_id.
5. Kill `VideoToolbox` (mock: временно убрать encoder из `EncoderCapabilities`) → fallback на `libx264` (publer_direct) или `libx265` (archive_hevc) без crash.
6. Progress SSE: UI получает `{stage: "render", progress: 0.0..1.0}` минимум раз в 500 мс во время ffmpeg.
7. Throughput: 15 рилсов × 90 с параллельно (concurrency=2) на M5 → ≤10 мин wall time (бенчмарк REFACTR-22, `docs/performance/m5-render-bench.md`).
8. ffmpeg RAM: <500 MB per process × 2 concurrent = <1 GB total (Media Engine не использует system RAM, только VT buffers).
9. CPU utilisation: <40% на 10-core M5 при 2 concurrent VT-encode.
10. Detection кеш: `runtime_settings.encoder_capabilities` не переспрашивается на каждый рендер, только при старте uvicorn.

---

## Открытые вопросы

1. **Portrait 4:5 (Instagram feed)** — нужна ли отдельная fallback-стратегия? Ответ: **Нет**, те же два профиля, меняются aspect/resolution (из `export_presets.yaml`), не encoder.
2. **HEVC 8-bit vs 10-bit** — не даст ли 10-bit проблем у пользователей archive-файла на Windows? Ответ: HEVC Main10 — стандарт HDR, все современные плееры (VLC, Windows 11 Media, mpv) читают. Для старых Windows 10 < 1903 — fallback на 8-bit через runtime-флаг `archive_hevc_8bit=true`.
3. **ProRes** (`prores_videotoolbox`) — нужен ли третий профиль для DaVinci Resolve intermediate? Ответ: **Отложено** — не в PoC, добавится отдельным ADR, если появится запрос.
4. **AV1** — как выше, отложено до поддержки платформами.

---

## Ссылки

- FFmpeg VideoToolbox wiki: https://trac.ffmpeg.org/wiki/Encode/H.265#VideoToolbox
- FFmpeg hevc_videotoolbox docs: https://ffmpeg.org/ffmpeg-codecs.html#hevc_videotoolbox
- Apple VideoToolbox framework: https://developer.apple.com/documentation/videotoolbox
- ADR-0002 — runs/{run_id}/ structure (рендер пишет в `runs/{run_id}/renders/`)
- `task.md §2.4` — требование hevc_videotoolbox + fallback
- `task.md §4.1 REFACTR-21` — VideoToolbox encode + encoder_strategy
- `task.md §4.2 REFACTR-22` — параметры качества ≥15 Mbps
- Commit `b3a97c1` — H.264 12 Mbps default для Publer <200 MB
- Commit `8b4cbfa` — re-encode >180 MB рилсов для Publer
- `apps/backend/src/videomaker/config/export_presets.yaml` — YAML-пресеты
- `apps/backend/src/videomaker/services/filter_graph_builder.py:526-576` — `_build_encoder_args`
- `apps/backend/src/videomaker/api/routes/health.py:48-66` — `_detect_ffmpeg`
- `apps/backend/src/videomaker/services/publer/media_uploader.py:78-129` — `_reencode_to_h264` (defense-in-depth)
