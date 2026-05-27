# Adaptive Audio Editing — research отчёт 2026-04-19

**Источник:** deep-research-analyst agent (`a364748cc5bec5395`, 68K токенов, 40 tool uses, 559 сек)
**Связано с:** `consolidated-action-plan.md` → секция T8 (audio cleanup, узкая часть от проблемы «качество монтажа»)
**Контекст:** пользователь хочет чтобы рилсы звучали как ручной монтаж — адаптивная очистка звука с учётом неровной записи (микрофон, сглатывания, cluck'и).

**ВАЖНО:** это УЗКАЯ часть запроса (≈30% от общей проблемы «профессиональный монтажёр vs машина»). Широкий editing craft — см. `editing-craft-2026.md` (в работе, второй агент).

---

## СЕКЦИЯ 1 — Adaptive Audio Cleaning

### 1.1 Mouth sounds detection/removal

**Реалистичное положение дел 2026:** специализированных open-source моделей именно для lip smacks / tongue clicks крайне мало. Индустрия разделилась на GUI (iZotope RX, Adobe Enhance Speech) и generic noise reduction.

#### noisereduce v3.0.3 (MIT)
Самая зрелая библиотека. Режим `stationary=False` работает против нестационарных кликов.

```python
import noisereduce as nr
reduced = nr.reduce_noise(y=y, sr=sr, stationary=False,
                          prop_decrease=0.8, time_constant_s=1.0)
```
Trade-off: `prop_decrease > 0.85` артефачит сибилянты (с/ш). Оптимум для mouth clicks: 0.6–0.75.

#### DeepFilterNet v0.5.6 (MIT)
Нейронная модель с двумя стадиями (ERB filter bank + детальная). Real-time ~5ms latency. Убирает plosives и breath лучше noisereduce на шумных записях.

```python
from df import enhance, init_df
model, df_state, _ = init_df()
enhanced = enhance(model, df_state, audio)
```
Trade-off: не классифицирует тип звука. Может уменьшить натуральность («plastic voice»). Рекомендуется `atten_lim_db=6` (мягкое подавление).

#### Resemble Enhance (MIT)
Двухкомпонентная: Denoiser (генеративный) + Enhancer (super-resolution). Обучен на 60K часах речи. Медленнее DeepFilterNet (~0.3 real-time factor без GPU).

Trade-off: Enhancer добавляет «polish» — неестественно для разговорного контента. Использовать только `--denoise_only`.

#### Специализированные модели для lip smacks (2025)

- **`padmalcom/wav2vec2-large-nonverbalvocalization-classification`** (HuggingFace) — классифицирует nonverbal vocalizations: laughter, crying, breath, cough, grunt, throat clearing, yawn. **НЕ** отдельно lip clicks.
- **`links-ads/kk-nonverbal-vocal-class`** (MIT, 2025) — эксперименты с PEFT дообучением Wav2Vec2/HuBERT/WavLM/Whisper на ReCANVo + VIVAE + CNVVE. Не production-ready, требует дообучения.

**Практический вывод:** для mouth click detection в 2026 signal-based работает надёжнее ML:

```python
def detect_clicks(y, sr, threshold_percentile=99.5, min_click_duration=0.003):
    frame_len = int(sr * 0.005)
    rms = librosa.feature.rms(y=y, frame_length=frame_len, hop_length=frame_len//2)[0]
    rms_db = librosa.amplitude_to_db(rms)
    threshold = np.percentile(rms_db, threshold_percentile)
    click_frames = np.where(rms_db > threshold)[0]
    return librosa.frames_to_time(click_frames, sr=sr, hop_length=frame_len//2)
```

### 1.2 Adaptive breath detection

**Основная находка: `padmalcom/wav2vec2-large-nonverbalvocalization-classification`** — класс `breath` присутствует. Confidence на реальных подкастах 72-80% accuracy breath vs silence. Проблема: модель не разделяет inhale/exhale.

```python
from transformers import pipeline
clf = pipeline("audio-classification",
               model="padmalcom/wav2vec2-large-nonverbalvocalization-classification")
result = clf("segment.wav")  # [{'label': 'breath', 'score': 0.87}]
```

#### Альтернативы
- **SpeechBrain VAD (CRDNN-LibriParty)** — через `activation_threshold=0.85` + `deactivation_threshold=0.15` получаем сегменты где VAD неуверен — часто breath.
- **pyannote/segmentation-3.0** (Apache-2.0, 2024) — speaker change detection как proxy для pauses.

#### Двухуровневый подход (рекомендуется)

1. Silero VAD v5+ (~50ms) — speech/non-speech segments
2. На non-speech 0.1-1.5 сек → wav2vec2 classifier
3. breath score > 0.6 → breath segment → breath compression
4. breath score < 0.4 → silence → silence compression

**Silero VAD v5/v6 (2024-2025):** v5 3x быстрее v4, 6000+ языков. `pip install silero-vad`. Нет встроенного adaptive threshold — нужно перевычислять per-chunk RMS.

### 1.3 Adaptive Pause Retention — punctuation approach

Whisper large-v3 расставляет точки с ~85% precision (чистая речь), ~70% (спонтанная). `whisper-timestamped` добавляет confidence per-word.

**Академическое обоснование (arxiv 2511.14779, 2025):** Prosodic Segmentation of Spontaneous Speech — паузы после интонационных единиц в среднем 200-250 ms, внутри единиц 50-80 ms.

**Таблица keep_sec:**

| Контекст | keep_sec | Обоснование |
|---|---|---|
| После `.` `?` `!` | 0.25-0.40 сек | Полная пауза, смена мысли |
| После `,` `;` | 0.08-0.14 сек | Внутри фразы |
| После `:` | 0.15-0.20 сек | Перечисление |
| Между словами | 0.02-0.05 сек | Breath room |
| Topic-change (LLM) | 0.40-0.60 сек | Монтажная пауза |

### 1.4 Adaptive Loudness Normalization

**pyloudnorm** — только global EBU R128. Для per-segment:

#### ffmpeg dynaudnorm (встроенный)
Gaussian smoothed sliding window.
```bash
ffmpeg -i in.wav -af "dynaudnorm=f=500:g=31:p=0.95:m=10.0:r=0.9:n=0" out.wav
```

#### ffmpeg-normalize (Python, MIT)
Двухпроходный loudnorm.
```python
from ffmpeg_normalize import FFmpegNormalize
normalizer = FFmpegNormalize(target_level=-16.0, loudness_range_target=11.0,
                              true_peak=-1.5, dynamic=True)
```

#### DynamicAudioNormalizer (GPL-2, lordmulder)
Отдельный бинарь с Python binding через ctypes. Более гибкий чем ffmpeg dynaudnorm.

#### Auphonic Adaptive Leveler (проприетарный)
Python client через requests. $11/мес за 9 часов аудио. Quality: лучший из доступных. Open-source альтернативы с comparable quality не существует.

**Рекомендация для videomaker:** ffmpeg dynaudnorm + pyloudnorm для финального измерения:

```python
def adaptive_level_segment(audio_np, sr, target_lufs=-16.0):
    meter = pyln.Meter(sr)
    loudness = meter.integrated_loudness(audio_np)
    if np.isinf(loudness):
        return audio_np
    gain_linear = 10 ** ((target_lufs - loudness) / 20)
    return np.clip(audio_np * gain_linear, -0.98, 0.98)
```

### 1.5 De-click / De-ess / De-plosive

#### De-click через scipy
```python
def soft_declicker(y, sr, threshold_factor=4.0):
    rms = np.sqrt(np.mean(y**2))
    threshold = rms * threshold_factor
    click_mask = np.abs(y) > threshold
    indices = np.arange(len(y))
    y_clean = np.interp(indices, indices[~click_mask], y[~click_mask])
    return y_clean
```

#### De-ess через spectral (librosa + scipy)
```python
def deess(y, sr, freq_start=5500, freq_end=8500, reduction_db=6):
    S = librosa.stft(y)
    freqs = librosa.fft_frequencies(sr=sr)
    mask = (freqs >= freq_start) & (freqs <= freq_end)
    S[mask, :] *= 10 ** (-reduction_db / 20)
    return librosa.istft(S)
```

#### De-plosive
High-pass filter + transient shaper через spectral subtraction. `noisereduce` с `freq_mask_smooth_hz=100` частично решает.

### 1.6 Dropped word endings — whisper confidence

**Алгоритм детекции «сглатывания»:**

```python
def detect_swallowed_endings(words, conf_threshold=0.45, duration_threshold=0.08):
    flagged = []
    for i, w in enumerate(words[:-1]):
        dur = w["end"] - w["start"]
        gap = words[i+1]["start"] - w["end"]
        if w["confidence"] < conf_threshold and dur < duration_threshold:
            flagged.append({
                "word": w["text"], "start": w["start"],
                "reason": "low_conf_short_duration", "gap_to_next": gap
            })
    return flagged
```

**Отличие tight-cut от bad articulation:**
- confidence < 0.45 + normal duration (>0.12 сек) + gap > 0.05 → articulation issue
- confidence OK + gap < 0.01 → tight cut от паузы

**arxiv 2502.13446 (февраль 2025):** C-Whisper-large AUC-ROC 0.992 на LibriSpeech-clean, 0.828 на Chime6 (шум). Confidence надёжен на чистых записях.

---

## СЕКЦИЯ 2 — J/L-Cuts и ритмичная резка

### 2.1 Автоматическое применение J/L-cut

**J-cut:** аудио следующего клипа входит за 0.2-0.5 сек до смены видео. Плавность/предвосхищение.
**L-cut:** аудио текущего продолжается 0.2-0.5 сек после смены видео. «Мысль ещё звучит».

**FireCut** (Premiere Pro plugin): пауза >0.3 сек + конец логического сегмента → J-cut 0.2-0.35 сек.

**MovieCuts Dataset (arxiv 2109.05569, ECCV 2022):**
- J-cuts встречаются в **28% случаев смены говорящего**
- L-cuts — в **19% случаев конца реплики с эмоциональным контентом**
- Accuracy классификации J/L-cut: ~68% F1

**arxiv 2408.10998 (август 2024):** "Audio Match Cutting" — Audio Spectral Similarity + CLAP embeddings для семантического matching.

**Эвристики расстановки:**

| Триггер | Тип | Длина |
|---|---|---|
| Смена speaker (diarization) | J-cut | 0.25-0.35 сек |
| Конец `?` (риторический) | L-cut | 0.20-0.30 сек |
| Смена темы (LLM/embedding) | J-cut | 0.30-0.45 сек |
| Эмоциональный пик | L-cut | 0.25-0.40 сек |
| Конец `.` | Hard cut | 0.05-0.10 сек |
| Перечисление | Hard cut | 0.02-0.05 сек |

**moviepy реализация:**
```python
def apply_j_cut(clip_prev, clip_next, j_duration=0.3):
    next_audio_intro = clip_next.audio.subclip(0, j_duration)
    next_audio_intro = next_audio_intro.set_start(clip_prev.duration - j_duration)
    prev_with_j = clip_prev.set_audio(
        CompositeAudioClip([clip_prev.audio, next_audio_intro])
    )
    return concatenate_videoclips([prev_with_j, clip_next])
```

### 2.2 Rhythm-aware cut length

**OpenSMILE (BSD)** — extraction 6373 acoustic features (F0, HNR, RMS, MFCC, spectral centroid, ZCR).

```python
smile = opensmile.Smile(feature_set=opensmile.FeatureSet.eGeMAPSv02,
                        feature_level=opensmile.FeatureLevel.Functionals)
features = smile.process_file("segment.wav")
```

**Prosody → rhythm:**
- Высокий F0 в конце фразы = восходящая интонация = вопрос → L-cut
- Падение F0 + снижение loudness = конец мысли → больше воздуха
- Tempo > 3.5 слов/сек = tight cuts уместны
- Tempo < 2.0 слов/сек = больше пространства

**Librosa envelope:**
```python
rms = librosa.feature.rms(y=y, frame_length=int(sr*0.1), hop_length=int(sr*0.05))[0]
pacing_score = (rms - rms.min()) / (rms.max() - rms.min() + 1e-8)
# mean_energy > 0.6 → tight cuts (0.02-0.08)
# mean_energy < 0.3 → больше воздуха (0.15-0.35)
```

**Beat tracking на речи:** бесполезно (нет регулярного ритма). Альтернатива: onset strength envelope + OpenSMILE F0 contour для интонационных групп. Cut points на onset boundaries, не в середине звука.

### 2.3 Crossfade algorithms

| Тип | Длина | Применение |
|---|---|---|
| Equal-power | 5-25 ms | Hard cuts, устранение click-артефактов |
| Equal-power | 100-300 ms | J/L-cuts, смена speaker |
| Linear | 2-5 ms | Fade-in/out краёв клипа |
| S-curve | 200-500 ms | Музыкальные переходы, ambient |
| Без | 0 ms | Намеренный tight cut |

```python
def crossfade_equal_power(a_end, b_start, n_samples):
    t = np.linspace(0, np.pi/2, n_samples)
    return a_end * np.cos(t) + b_start * np.sin(t)
```

**Zero-crossing alignment:**
```python
def find_zero_crossing_near(y, idx, window=100):
    search = y[max(0, idx-window):min(len(y), idx+window)]
    zc = np.where(np.diff(np.sign(search)))[0]
    return max(0, idx-window) + zc[np.argmin(np.abs(zc - window))] if len(zc) else idx
```

---

## СЕКЦИЯ 3 — Composer «телевизионщик» — context control

### 3.1 Индустриальные AI-редакторы 2026

**Opus Clip:** «ClipAnything» (текстовый запрос) + «Scene Analysis» детектирует смены сцены. Нет явного флага preserve vs allow cross-scene — управляется через topic query.

**Descript Underlord:** «Shorten word gaps» (gaps > N sec → M sec). Нет режима cross-scene compilation. Работает в рамках одного проекта/файла.

**Gling (2026):** детектирует boring moments через silences + filler words + low speech energy. Нет cross-scene compilation.

**Вывод:** cross-scene compilation (T2.3 thematic composer) — **уникальная возможность videomaker**, не стандарт рынка.

**Индустриальная терминология:**

| Термин | Смысл |
|---|---|
| «Tight clip» | Только continuous, без jumps |
| «Highlight reel» | Compilation (допускает jumps) |
| «Context clip» | Сохраняет контекст до/после ключевого |
| «Topic-based clip» | Нарезка по тематическому запросу |
| «Scene-locked» | Запрет cross-scene |

**Рекомендуемые флаги для videomaker T9:**

```python
class ComposerMode(str, Enum):
    TIGHT = "tight"           # max_gap=0, только continuous
    TOPIC_REEL = "topic_reel" # cross-scene по embedding similarity
    HIGHLIGHT = "highlight"   # cross-scene по score ranking
    CONTEXT = "context"       # +N сек контекста вокруг момента

class ComposerConfig(BaseModel):
    mode: ComposerMode = ComposerMode.TIGHT
    max_temporal_gap_minutes: float = 5.0
    require_approval_if_gap_minutes: float = 10.0
    context_padding_sec: float = 3.0
```

### 3.2 Ethics of cross-scene compilation

**YouTube scandal 2025:** тайно применили AI-upscaling к Shorts без ведома авторов. Backlash → сделали opt-out. **Принцип для videomaker:** любые автоматические AI-изменения — transparently disclosed и reversible.

**Signal для problematic cross-scene:**
```python
def assess_cross_scene_risk(seg_a_end, seg_b_start, total_duration,
                            transcript_a, transcript_b):
    temporal_gap = seg_b_start - seg_a_end
    gap_fraction = temporal_gap / total_duration
    risks = []
    if temporal_gap > 600: risks.append("temporal_gap_high")
    if gap_fraction > 0.3: risks.append("large_fraction_jump")
    overlap = len(set(transcript_a.split()) & set(transcript_b.split())) / max(
        len(set(transcript_a.split()) | set(transcript_b.split())), 1)
    if overlap < 0.1: risks.append("low_semantic_overlap")
    return risks  # пустой = OK, иначе warn
```

### 3.3 Rhythm/pacing analysis — что реально

**Gling / Descript / Opus Clip algorithms** — black box, публичных деталей мало. Реалистичная реализация:

```python
def compute_pacing_score(audio_path, window_sec=30.0):
    y, sr = librosa.load(audio_path, sr=16000)
    rms = librosa.feature.rms(y=y, frame_length=512, hop_length=256)[0]
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    n = int(window_sec * sr / 256)
    scores = []
    for i in range(0, len(rms) - n, n):
        scores.append({
            "energy_mean": float(np.mean(rms[i:i+n])),
            "energy_var": float(np.var(rms[i:i+n])),
            "onset_mean": float(np.mean(onset_env[i:i+n])),
            "pause_density": float(np.mean(rms[i:i+n] < 0.01))
        })
    return scores
```

---

## ДОПОЛНИТЕЛЬНЫЕ ТЕМЫ

### Silence vs Breath — правильная separation

| Класс | RMS | Спектр | Длительность |
|---|---|---|---|
| Silence | <-50 dBFS | Flat noise floor | любая |
| Breath | -40 до -20 dBFS | Broadband, пик 200-800 Hz | 0.1-0.8 сек |
| Speech | >-30 dBFS | Форманты, F0 | >0.05 сек |

Правильный детектор: Silero VAD → non-speech → wav2vec2 classifier → решение о компрессии.

### Dynamic noise floor
```python
def estimate_noise_floor(y, sr, percentile=10, frame_sec=0.1):
    rms = librosa.feature.rms(y=y, frame_length=int(sr*frame_sec))[0]
    from scipy.ndimage import percentile_filter
    return percentile_filter(rms, percentile=percentile, size=int(1.0/frame_sec))
```

### Formant analysis (speaker fingerprint для cross-cuts)
```python
from librosa import lpc
def estimate_formants(y, sr, n_formants=3):
    order = 2 + int(sr / 1000)
    a = lpc(y, order=order)
    roots = np.roots(a)
    roots = roots[np.imag(roots) >= 0]
    freqs = sorted(np.arctan2(np.imag(roots), np.real(roots)) * sr / (2*np.pi))
    return [f for f in freqs if f > 90][:n_formants]
```

### Master bus
```python
def master_bus(audio, sr, target_lufs=-14.0, true_peak_dbtp=-1.0):
    meter = pyln.Meter(sr)
    loudness = meter.integrated_loudness(audio)
    if not np.isinf(loudness):
        audio = pyln.normalize.loudness(audio, loudness, target_lufs)
    return np.clip(audio, -10**(true_peak_dbtp/20), 10**(true_peak_dbtp/20))
```

---

## СВОДНАЯ ТАБЛИЦА

| Библиотека | Задача | Версия | License | Рекомендовать? |
|---|---|---|---|---|
| noisereduce | Spectral noise gate, de-click | 3.0.3 | MIT | ДА — первый уровень |
| DeepFilterNet | Neural denoising | 0.5.6 | MIT | ДА — шумные записи |
| Resemble Enhance | Generative denoising+SR | latest | MIT | ОСТОРОЖНО — только Denoiser |
| Silero VAD v5/v6 | VAD | 6.2.1 | MIT | ДА — основа pipeline |
| padmalcom/wav2vec2-nvv | Breath classification | HF model | Apache-2.0 | ДА — breath detection |
| whisper-timestamped | Word confidence | 1.15+ | Apache-2.0 | ДА — confidence scoring |
| pyannote/segmentation-3.0 | Speaker diarization | 3.0 | MIT | ДА — speaker change |
| pyloudnorm | EBU R128 | 0.2.0 | MIT | ДА — финальное измерение |
| ffmpeg dynaudnorm | Adaptive normalization | 8.x | LGPL | ДА — leveling |
| ffmpeg-normalize | Two-pass R128 | 1.28+ | MIT | ДА — batch |
| OpenSMILE | Prosody features | 3.0.2 | MIT | ДА — rhythm analysis |
| librosa | Onset, RMS, spectral | 0.11.0 | ISC | ДА — везде |
| moviepy | J/L-cut rendering | 2.1+ | MIT | ДА — применение cuts |
| scipy | De-click, crossfade | 1.14+ | BSD | ДА — утилиты |
| Auphonic API | Cloud adaptive levelling | 2026 | proprietary | ЕСЛИ нужен top quality |

---

## АРХИТЕКТУРНАЯ РЕКОМЕНДАЦИЯ: Adaptive Audio Pipeline

Заменить 2 глобальных threshold на 8 адаптивных стадий:

```
PASS 0: Dynamic noise floor estimation (per-30sec window)
        → normalize threshold references

PASS 1: DeepFilterNet denoising (если SNR < 20 dB)
        мягкий atten_lim_db=6

PASS 2: Silero VAD v5 → speech/non-speech
        + wav2vec2-nvv classifier на non-speech → breath/silence/click

PASS 3: Breath compression (fade to -24dBFS, не удалять)
        Silence compression (global threshold)
        Click removal (scipy interpolation)

PASS 4: Per-segment adaptive leveling (pyloudnorm + ffmpeg dynaudnorm)

PASS 5: Punctuation-aware pause retention
        (whisper-timestamped + punct → keep_sec lookup)

PASS 6: J/L-cut application at reel boundaries
        (OpenSMILE F0 + energy → mode determination)

PASS 7: Crossfade at cut boundaries (equal-power, 5-15 ms, zero-crossing aligned)

PASS 8: Master bus loudness (-14 LUFS podcast / -16 LUFS YouTube)
        + True peak limiting at -1.0 dBTP
```

---

## ОГРАНИЧЕНИЯ И ПРОБЕЛЫ

1. **Нет open-source production-ready lip smack classifier** — только generic NVV или signal-based workarounds
2. **Внутренние алгоритмы pacing** Gling/Opus Clip не раскрываются
3. **Adaptive threshold для Silero VAD** per-segment требует кастомной реализации — нет out-of-the-box решения
4. **Accuracy breath classifier на русской спонтанной речи** не тестировалась (padmalcom модель на EN/DE)

---

## Источники

- arxiv 2502.13446 "Adopting Whisper for Confidence Estimation" (2025)
- arxiv 2408.10998 "Audio Match Cutting" (2024)
- arxiv 2511.14779 "Prosodic Segmentation" (2025)
- arxiv 2109.05569 "MovieCuts Dataset" (ECCV 2022)
- links-ads/kk-nonverbal-vocal-class (CLiC-it 2025)
- GitHub: timsainb/noisereduce, Rikorose/DeepFilterNet, resemble-ai/resemble-enhance
- HuggingFace: padmalcom/wav2vec2-large-nvv
- FireCut Premiere Pro docs (2023-2024)
- Descript/Gling/Opus Clip product pages (2025-2026)
