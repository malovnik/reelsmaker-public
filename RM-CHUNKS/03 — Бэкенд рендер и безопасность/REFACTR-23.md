# REFACTR-23 — Бенчмарк рендера на M5 Pro

> **Этап:** 03
> **Шаг:** 24 из 67
> **Зависимости:** REFACTR-21, REFACTR-22.
> **Следующий шаг:** REFACTR-24 (Security: секреты)

---

## Роли

### R-RENDER-ENG
**Soul:** Цифры — единственная правда перфоманса. Ощущения не считаются.

### R-DEVIL
**Soul:** Бенчмарк без сравнения = бенчмарк впустую. Нужен baseline (software) и целевой (hardware), дельта.

---

## ТРИЗ-принцип

*Принцип измерения.* Измерить = понять. После бенчмарка pipeline становится квантифицированным активом, не чёрным ящиком.

---

## Оркестрация

**Режим:** Sequential.

---

## Микрозадачи

### 23.1 Подготовить датасет

Три тестовых видео:
- S (15 мин).
- M (30 мин).
- L (60 мин).

Одного говорящего, в 9:16 или 16:9 (для теста resize → 9:16).

### 23.2 Сценарий бенчмарка

Для каждого видео прогнать полный pipeline дважды:
- **Hardware:** `hevc_videotoolbox` + детектор = включён.
- **Software:** `FORCE_SOFTWARE_ENCODE=1` → `libx265`.

Замерять:
- Время каждой стадии (transcribe, silence_cut, llm, compose, render).
- RAM peak (через `/usr/bin/time -l` или psutil).
- Размер финального файла.
- Bitrate (через ffprobe).

### 23.3 Скрипт бенчмарка

`scripts/benchmark_render.py`:

```python
async def run_benchmark(video_path: Path, encoder: EncoderChoice) -> BenchmarkResult:
    start = time.monotonic()
    stages_timing = {}
    peak_rss_mb = 0
    
    # Prepare project ...
    # Run pipeline ...
    # Collect metrics ...
    
    return BenchmarkResult(
        video_duration_sec=...,
        total_wall_time_sec=...,
        realtime_ratio=...,
        stages=stages_timing,
        peak_rss_mb=peak_rss_mb,
        output_size_mb=...,
        output_bitrate_mbps=...,
    )
```

### 23.4 Запустить бенчмарк

- [ ] Hardware prof: S, M, L.
- [ ] Software prof: S, M, L.
- [ ] Сохранить JSON-отчёт в `docs/performance/bench-2026-04-XX.json`.

### 23.5 Документ

`docs/performance/m5-render-bench.md`:

| Видео | Длительность | Encoder | Wall | Realtime | RAM peak | Size | Bitrate |
|-------|-------------|---------|------|----------|----------|------|---------|
| S | 15:00 | hardware | XX:XX | 0.X× | XXX MB | XX MB | 15.X Mbps |
| S | 15:00 | software | XX:XX | X.X× | ... | ... | ... |
| M | 30:00 | hardware | ... | ... | ... | ... | ... |
| M | 30:00 | software | ... | ... | ... | ... | ... |
| L | 60:00 | hardware | ... | ... | ... | ... | ... |
| L | 60:00 | software | ... | ... | ... | ... | ... |

Цель: hardware realtime ≤1.5×. Если не достигнута — STOP-1, Context7 по VideoToolbox tuning.

### 23.6 Commit + Serena

---

## GATE-чекпоинт

- [ ] Бенчмарк отработан на 3 видео × 2 encoder = 6 прогонов.
- [ ] Hardware encode укладывается в ≤1.5× realtime на M5 Pro.
- [ ] JSON-отчёт + Markdown-документ созданы.
- [ ] **Этап 03.А (рендер) ЗАВЕРШЁН** → переход к 03.Б (безопасность).

**СТОП если:** hardware > 1.5× realtime → Context7 по hevc_videotoolbox tuning, повторный эксперимент.

---

## Артефакт на выходе

`docs/performance/m5-render-bench.md` + JSON-сырец + скрипт бенчмарка.
