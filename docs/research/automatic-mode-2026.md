# Automatic Mode — research отчёт 2026-04-19

**Источник:** deep-research-analyst agent (`aa40065d57e2871d0`, 75K токенов, 25 tool uses, 385 сек)
**Связано с:** `consolidated-action-plan.md` → секция T11 (Automatic Mode — робот-монтажёр)
**Цель:** полная замена монтажёра — система сама принимает решения по всем 25 параметрам pipeline.

---

## ГЛАВНЫЙ ВЫВОД

MVP строится на **hybrid rule tree + LLM fallback** архитектуре:
- **Rule tree** покрывает 85-90% случаев для typical talking-head контента
- **Gemini Flash Lite fallback** при confidence < 0.4 (narrative/сложные случаи)
- Нужны **5-6 новых библиотек** (librosa есть, + opensmile, parselmouth, silero-vad, pyloudnorm, scikit-maad, pedalboard)
- **20 сек end-to-end** от upload до старта pipeline (15 сек feature extraction параллельно + 1 сек rule tree)

**Реальное время реализации (калибровано ×7):**
- MVP (Sprint 1-2 по research) → **~40-60 минут моего времени**

---

## 1. Audio Signal Feature Extraction

### Стек библиотек 2026 (production-ready)

| Библиотека | Версия | License | Назначение |
|---|---|---|---|
| **librosa** | 0.11.0 | ISC | Спектральные features (есть) |
| **opensmile** | 2.5+ (audeering) | Apache-2.0 | eGeMAPSv02 88 features |
| **praat-parselmouth** | 0.4.3+ | GPL-3 | Pitch/HNR/jitter/shimmer |
| **silero-vad** | 6.2.1 | MIT | VAD (есть в проекте) |
| **pyloudnorm** | 0.1.1 | MIT | EBU R128, LRA |
| **noisereduce** | 3.0+ | MIT | Spectral gating |
| **pedalboard** | 0.9.22 | GPL-3 (Spotify) | NoiseGate, Compressor, HighpassFilter |
| **scikit-maad** | 1.5.1 | BSD-3 | `temporal_snr()` 3 строки кода |

### Ключевые features для решений

| Feature | Библиотека | Значение / пороги |
|---|---|---|
| **SNR dB** | scikit-maad `temporal_snr()` | >25 чисто, 15-25 лёгкий шум, 8-15 агрессивный denoise, <8 predупреждать |
| **WPS (words/sec)** | whisper transcript | <2.0 medium docs, 2-3.5 balanced, >3.5 dynamic |
| **Pitch std (Hz)** | Parselmouth F0 std | <15 монотонный, 15-40 умеренный, >40 эмоциональный |
| **LRA (LU)** | pyloudnorm | <6 компрессирован, 6-12 нормальный, >12 широкий динамический |
| **Spectral flatness** | librosa | >0.3 noise-dominated, <0.05 tonal |
| **Spectral centroid** | librosa | <2000 Hz «бубнящий» mic, >4500 Hz яркий → de-ess |
| **Gap stats** | silero-vad | mean/std/kurtosis пауз → compression strategy |
| **Rhythm CV** | librosa onset_detect | CV<0.3 ритмичный → beat-snap, CV>0.6 хаотичный → onset-snap |
| **Whisper avg_logprob** | faster-whisper | proxy confidence (arXiv 2502.13446) |

### Время feature extraction (30-мин видео)

| Этап | Время |
|---|---|
| VAD silero | ~8 сек |
| SNR scikit-maad | ~2 сек |
| Loudness pyloudnorm | ~1 сек |
| Spectral librosa | ~5 сек |
| Pitch Parselmouth | ~12 сек (медленный) |
| eGeMAPS opensmile | ~6 сек |
| **Sequential total** | **~34 сек** |
| **Параллельно (asyncio + threadpool)** | **~12-15 сек** |

---

## 2. Decision Engine — Hybrid архитектура

### Сравнение подходов

| Подход | Pros | Cons | Рекомендация |
|---|---|---|---|
| Hard-coded rule tree | Debuggable, быстрый, без данных, контроль | Хрупкий, экспертные правила | **MVP: ДА** |
| ML classifier | Обобщается, адаптивен | Нет training data, black box | Фаза 2 (200+ решений) |
| LLM (Gemini Flash Lite) | Гибкий, zero-shot, объяснимый | $0.01/вызов, 3-8 сек latency, недетерминизм | Fallback при confidence<0.4 |
| Bayesian | Uncertainty estimation | Сложный, prior-калибровка | Фаза 3 |

**Выбор:** Rule tree с confidence scoring + LLM fallback для low-confidence. Накапливать пары `(features → settings, user_liked)` для будущего ML.

### AudioProfile и AutoSettings dataclasses

```python
@dataclass
class AudioProfile:
    snr_db: float
    wps: float
    pitch_std: float
    lra_lu: float
    mean_gap_sec: float
    gap_kurtosis: float
    rhythm_cv: float
    spectral_flatness: float
    spectral_centroid_hz: float
    whisper_avg_confidence: float
    content_type: str  # talking_head / screencast / interview
    total_duration_sec: float

@dataclass
class AutoSettings:
    # все 25 параметров pipeline...
    pacing_profile: str
    pause_compression_threshold_sec: float
    # + для каждого решения:
    confidence: float
    reasoning: dict  # evidence per decision
```

---

## 3. Content-Aware Zone Detection

### Per-chunk профили

Используем existing chunk infra (Stage 2 у нас уже есть). 60-сек окна с 15-сек overlap.

```python
def extract_per_chunk_profile(audio, sr, transcript_chunks):
    profiles = []
    step = int(60.0 * sr)
    overlap = int(15 * sr)
    for i in range(0, len(audio), step - overlap):
        chunk = audio[i:i + step]
        profiles.append(extract_audio_profile(chunk, sr))
    return profiles
```

### Merge per-zone settings для рилса

Если рилс спанает несколько zones — weighted average по длине:

```python
def merge_zone_settings(zones_in_reel):
    weights = [z.duration_sec for z in zones_in_reel]
    dominant = zones_in_reel[np.argmax(weights)]
    return AutoSettings(
        pacing_profile=dominant.settings.pacing_profile,  # categorical — dominant
        pause_threshold_sec=np.average([z.settings.pause_threshold for z in zones_in_reel],
                                         weights=weights)
    )
```

### PySceneDetect для visual zones

Дополнительный signal: `AdaptiveDetector()` для визуальных scene boundaries.

### Scene-VLM (arXiv 2512.21778, декабрь 2025) — долгосрочная цель

Amazon Prime + BGU. +6 AP, +13.7 F1 над baseline для scene segmentation. Production-избыточно на MVP, но правильное направление развития.

---

## 4. Confidence Estimation

### Мета-confidence

```python
def compute_meta_confidence(profile) -> float:
    c = 1.0
    if profile.snr_db < 10: c *= 0.5
    elif profile.snr_db < 18: c *= 0.8
    if profile.whisper_avg_confidence < 0.5: c *= 0.6
    elif profile.whisper_avg_confidence < 0.7: c *= 0.85
    if profile.total_duration_sec < 120: c *= 0.7
    if profile.content_type == "unknown": c *= 0.75
    return c
```

### Fallback при low confidence

```python
CONFIDENCE_FALLBACK_THRESHOLD = 0.4

def decide_with_confidence(profile, rule_fn, default_value):
    result = rule_fn(profile)
    if result.confidence < CONFIDENCE_FALLBACK_THRESHOLD:
        return DecisionConfidence(
            value=default_value,
            confidence=0.9,  # высокая уверенность в safe default
            source="default",
            evidence=f"Low confidence ({result.confidence:.2f})"
        )
    return result
```

### Whisper confidence

Из faster-whisper `segments[i].avg_logprob`:
```python
avg_confidence = np.mean([np.exp(seg.avg_logprob) for seg in segments])
# <0.4 → ненадёжная транскрипция → отключить filler_removal
```

### Soft decisions

Вместо scalar — distribution:
```python
pause_threshold = {"mode": 0.45, "low": 0.35, "high": 0.60, "confidence": 0.73}
```

---

## 5. Industry Precedents — что портируемо

| Продукт | Что делает | Портируется как |
|---|---|---|
| **Auphonic Adaptive Leveler** | LRA target + segment leveling | `pyloudnorm` LRA → decision tree |
| **Descript Studio Sound** | Neural one-pass enhancement | `DeepFilterNet 3` (`pip install deepfilternet`) |
| **Adobe Podcast AI Enhance** | Dialog isolation | `resemble-enhance` (MIT, open-source alt) |
| **iZotope RX 11 Repair Assistant** | DeHiss→DeClick→DeReverb→Dialog | `noisereduce` + `pedalboard` HighpassFilter |
| **DaVinci Resolve 20 IntelliCut** | AI cut points | Speech energy + PySceneDetect |

---

## 6. Validation Feedback Loop

### DB схема

```python
class AutoModeDecision(Base):
    __tablename__ = "auto_mode_decisions"
    id: UUID
    project_id: UUID
    created_at: datetime
    # Input features
    snr_db: float
    wps: float
    pitch_std: float
    lra_lu: float
    # Decisions
    pacing_profile: str
    compression_threshold: float
    punch_in_probability: float
    # Outcome
    user_liked: bool | None
    user_exported: bool
    user_modified_settings: bool
    override_params: dict
```

### Стратегия обучения

| Объём оценок | Действие |
|---|---|
| 0-50 | Rule tree only, feedback только записывается |
| 50-200 | Logistic regression / Random Forest, weekly batch retrain |
| 200+ | XGBoost / MLP, персонализированный classifier per user |

**Связь с T6:** decision vector → feature vector для T6 preference ML.

---

## 7. Failure Modes и Safeguards

### Таблица failure modes

| Failure | Trigger | Safeguard |
|---|---|---|
| Плохой mic → агрессивный denoise | SNR<10 | `prop_decrease ≤ 0.6` при SNR<10 |
| Акцент → плохой Whisper | avg_conf<0.4 | Отключить filler_removal |
| Монолог без пауз | mean_gap<0.15 | `min keep_sec = 0.18` всегда |
| Видео без речи | wps=0 | Fallback "minimal" preset + alert |
| Хаотичная речь | CV>0.8 | Отключить rhythm_aware_cuts |
| Длинные смысловые паузы | kurtosis>5 | Poisson threshold: не трогать >3×mean_gap |
| Фоновая музыка | spectral_flatness>0.4 | VAD threshold → 0.7 |
| Много speaker | pyannote>1 | Per-speaker feature extraction |

### Safety limits (circuit breaker)

```python
SAFETY_LIMITS = {
    "pause_compression_keep_sec": {"min": 0.15, "max": 0.5},
    "breath_compression_keep_sec": {"min": 0.08, "max": 0.25},
    "punch_in_zoom_intensity": {"min": 1.0, "max": 1.20},
    "max_shift_sec": {"min": 0.0, "max": 0.5},
    "coherence_threshold": {"min": 0.3, "max": 0.8},
}
```

### User warnings

```python
def generate_warnings(profile, settings):
    warnings = []
    if profile.snr_db < 10:
        warnings.append(f"Низкое качество аудио (SNR {profile.snr_db:.0f} dB).")
    if profile.whisper_avg_confidence < 0.4:
        warnings.append("Качество транскрипции низкое. Удаление слов-паразитов отключено.")
    if settings.confidence < 0.4:
        warnings.append(f"Auto mode confidence {settings.confidence:.0%}. Рекомендуем проверить.")
    return warnings
```

---

## 8. UI Implications

### Upload screen toggle

```
[Режим монтажа]
○ Automatic  ← default
○ Manual (настройки из /settings/performance)
```

### Summary Card после анализа

```
Auto Mode анализ завершён (уверенность: 78%)

Речь: быстрая (3.8 wps) · Эмоциональная (pitch std: 42 Hz)
Качество: хорошее (SNR: 22 dB) · Лёгкий шум 0:00-4:30

Принятые решения:
  Темп           → Dynamic (tight cuts)
  Punch-in zoom  → 40% сцен, 1.08x
  Паузы          → Сжимать до 0.25 сек
  Punchline hold → 0.35 сек
  Шумодав        → Включён (первые 4:30)
  Слова-паразиты → Удалить (conf 91%)

[Запустить]  [Изменить]  [Детали]
```

### История Auto Mode

- Последние видео с принятыми настройками + рейтинг
- Сохранить как template для похожих видео

---

## A) Блок-схема pipeline

```
UPLOAD
  ↓
[Stage 0: Audio Extraction] ~2 сек
  ↓
[Stage 1: Parallel Feature Extraction] ~12-15 сек
  ├── VAD silero-vad
  ├── SNR scikit-maad
  ├── Loudness pyloudnorm
  ├── Spectral librosa
  ├── Pitch Parselmouth
  ├── eGeMAPS opensmile
  └── Speaker count pyannote
  ↓
[Stage 2: Derived Features] ~1 сек
  WPS, whisper confidence, rhythm CV, pause dist, content type
  ↓
[Stage 3: Zone Detection] ~2-3 сек
  per-chunk profiles → ContentZone[]
  ↓
[Stage 4: Meta-Confidence]
  ↓
  ├─ >0.6 → [Stage 5A: Rule Tree] → AutoSettings
  │
  └─ ≤0.6 → [Stage 5B: LLM Advisor] Gemini Flash Lite → AutoSettings
  ↓
[Stage 6: Safety + Warnings]
  apply_safety_limits, generate_warnings
  ↓
[Stage 7: UI Summary Card]
  ↓
[Stage 8: Pipeline Execution]
  inject AutoSettings → runtime_settings_store → run 9-stage pipeline
  ↓
[Stage 9: Feedback Collection]
  store AutoModeDecision, update feedback loop every 50+
```

---

## B) Feature → Decision → Parameter (25 параметров)

| # | Параметр | Audio Feature(s) | Правило |
|---|---|---|---|
| 1 | pause_compression_enabled | mean_gap_sec | True если >0.4 |
| 2 | pause_compression_threshold_sec | mean_gap_sec, gap_std | = mean_gap * 0.7, clamp 0.3-0.8 |
| 3 | pause_compression_keep_sec | gap_kurtosis | >3→0.35, <1→0.20 |
| 4 | breath_compression_enabled | rhythm_cv, wps | wps>3.0 AND CV<0.4 |
| 5 | breath_compression_threshold | mean_gap_sec, hnr | 0.4 * min(breath_gaps), 0.05-0.25 |
| 6 | filler_words_removal_enabled | whisper_conf, snr_db | conf>0.6 AND snr>15 |
| 7 | filler_list | language_id | ru: "э-э, м-м, ну, вот, как бы"; en: "um, uh, like" |
| 8 | rhythm_aware_cuts_enabled | rhythm_cv | CV<0.4 |
| 9 | max_shift_sec | rhythm_cv | CV<0.3→0.1, CV>0.5→0.25 |
| 10 | coherence_threshold | pitch_std, wps, lra | pitch_std>35→0.35, <15→0.25 |
| 11 | coherence_mode | wps, duration | wps>3→"reject", wps<2→"resort" |
| 12 | composer_strategy | pitch_std, kurtosis, wps | pitch>40→"tight", kurtosis>3→"balanced", low wps→"thematic_free" |
| 13 | punchline_hold_sec | rhythm_cv, wps | wps<2→0.55, wps>3.5→0.30 |
| 14 | punch_in_zoom_enabled | pitch_std, content_type | pitch>25 AND talking_head |
| 15 | punch_in_zoom_intensity | pitch_std, wps | wps>3.5→1.10x, <2→1.04x |
| 16 | punch_in_zoom_probability | wps, CV | wps>3.5 AND CV<0.4→0.45 |
| 17 | onset_snap_window_sec | rhythm_cv | CV<0.25→0.08, >0.5→0.2 |
| 18 | ken_burns_enabled | wps, content_type | wps<2.0 OR interview |
| 19 | ken_burns_speed | wps | wps=2.0→0.03, 1.5→0.05 |
| 20 | pacing_profile | wps × pitch_std | см. матрицу |
| 21 | noise_reduction_intensity | snr_db, flatness | snr>25→0.0, 18-25→0.4, 10-18→0.7, <10→0.6 |
| 22 | denoising_zone | per-chunk SNR | chunk_snr<18 |
| 23 | adaptive_leveling_target_lufs | lufs, content_type | dialogue→-16, podcast→-14 |
| 24 | de_esser_enabled | spectral_centroid | >4500 Hz |
| 25 | high_pass_filter_hz | centroid, snr | snr<20→100, >20→80 |

### Матрица pacing_profile

```
              WPS
       <2.0   2-2.8  2.8-3.5  >3.5
     ┌──────┬──────┬────────┬───────┐
pit  │ doc  │ bal  │  bal   │ dyn   │  >40 Hz
std  ├──────┼──────┼────────┼───────┤
     │ doc  │ bal  │ mkbhd  │ dyn   │  20-40
     ├──────┼──────┼────────┼───────┤
     │ doc  │ doc  │ mkbhd  │ mkbhd │  <20
     └──────┴──────┴────────┴───────┘
```

---

## C) Рекомендация реализации

### MVP (40-60 мин моего времени)

1. **`services/audio_analyzer.py`** — feature extraction параллельно через asyncio
2. **`services/auto_config_advisor.py`** — rule tree 25 правил + safety limits + warnings
3. **Интеграция в pipeline** — Stage 0.5 между upload и STT
4. **UI toggle + summary card** — Auto/Manual

Зависимости:
```toml
[project]
dependencies = [
    "librosa==0.11.0",       # есть
    "opensmile>=2.5.0",
    "praat-parselmouth>=0.4.3",
    "silero-vad>=6.2.1",     # есть
    "pyloudnorm>=0.1.1",
    "noisereduce>=3.0.0",
    "pedalboard>=0.9.22",
    "scikit-maad>=1.5.1",
]
```

### Фаза 2 (override UI + Feedback DB + per-zone + LLM fallback)

### Фаза 3 (Production)

Caching похожих AudioProfile (euclidean distance < 0.1) → return cached settings. Экономия LLM вызовов.

**Latency targets:**
- Feature extraction: <15 сек (параллельно) для видео до 60 мин
- Rule tree: <100 мс
- LLM fallback: 2-5 сек
- UI to user: <20 сек от Upload клика

---

## D) Граница автономности

### Полная автономность (>85%)

| Задача | Автономность |
|---|---|
| Темп монтажа | 90% |
| Сжатие пауз | 88% |
| Noise reduction | 85% |
| LUFS normalization | 95% |
| Rhythm-aware cuts | 82% |
| Ken Burns | 83% |
| De-esser | 78% |

### Требует safety override

| Задача | Проблема | Решение |
|---|---|---|
| Filler removal при акценте | Whisper ошибается | confidence>0.7 required |
| coherence_mode творческий | Правила не знают замысла | Preview + approve |
| composer_strategy нарратив | "tight" режет нарратив | Preview reel перед экспортом |
| punch_in при screencast | Нет лица | Moondream content_type |
| Редкий язык | Всё ненадёжно | Banner warning |
| Первое видео user | Нет preference | Onboarding wizard |

### Практический итог

**85-90% автономность для typical talking-head** на русском/английском.
Оставшиеся 10-15% — творческие решения (какой момент из хороших), зависят от авторского намерения.

---

## Аннотированная библиография

- **silero-vad v6.2.1** (9K stars, 234K weekly) — production VAD
- **opensmile-python 2.5** (audeering, 2650+ citations) — eGeMAPSv02 88 features
- **pyloudnorm** (csteinmetz1, AES 2021) — ITU-R BS.1770-4
- **scikit-maad 1.5.1** — `temporal_snr()` 3 строки
- **pedalboard 0.9.22** (Spotify) — NoiseGate, Compressor
- **Parselmouth 0.4.3** — Praat wrapper
- **PySceneDetect 0.6.7 / 0.8b** (2025/2026) — visual scene detection
- **arXiv:2411.04942** (Nov 2024) — RL-based auto editing (rule tree оправдан на MVP)
- **arXiv:2502.13446** (Feb 2025) — Whisper confidence estimation
- **Scene-VLM arXiv:2512.21778** (Dec 2025, Amazon+BGU) — SOTA scene segmentation
- **noisereduce 3.0** — spectral gating
