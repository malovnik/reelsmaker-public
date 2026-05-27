# Editing Craft для AI Video Editor — research отчёт 2026-04-19

**Источник:** deep-research-analyst agent (`ae38079b64bbd134b`, 86K токенов, 22 tool uses, 392 сек)
**Связано с:** `consolidated-action-plan.md` → секция T10 (editing craft — главная рамка «профессиональный монтажёр vs машина»)
**Контекст:** пользователь просит сделать рилсы ощущающимися как ручной монтаж, не «алгоритм нарезал». Это ШИРОКАЯ рамка включающая T8 (audio ≈30%) и T9 (composer mode ≈10%). Основные 60% — здесь.

---

## ГЛАВНЫЙ ВЫВОД (перед всем остальным)

**Ни один mass-market AI editor не управляет variable pacing внутри одного рилса алгоритмически в 2026.** Opus Clip, Descript Underlord, Gling, Vizard — все решают проблему «что включить» (выбор сегментов), но не «как быстро резать в разных частях» (rhythm of cuts).

Это **прямая точка роста для videomaker** — можно сделать то, чего нет на рынке.

---

## 1. Pacing Analysis в AI-editors 2026

### Opus Clip ClipAnything
- Заявляет 94% precision в key moment detection
- Мультимодальный: аудио sentiment + визуал (face, motion) + текст (hooks)
- Pacing signals: sentiment spikes, energy pauses вокруг тезисов, social trend alignment
- Конкретные pacing параметры **не раскрыты**

### Gling (YouTube influencers)
- Только silence removal + jump cuts через ASR
- Чистит talking-head (паузы, «мм», «эм»)
- **Нет variable pacing engine** — финальный rhythm за автором

### Descript Underlord
- Редактирование как текста
- Story Mode — narrative arc через LLM
- Pacing decisions — ручные

### Vizard
- Speaker boundary detection
- Лучше держит natural pacing при речи 1.25x normal (vs Opus Clip)

---

## 2. Shot Duration — Правила индустрии

### Walter Murch Rule of Six (иерархия приоритетов)

| Приоритет | Параметр | Вес | Автоматизируется 2026 |
|---|---|---|---|
| 1 | **Emotion** | **51%** | Частично — sentiment + energy spikes |
| 2 | Story | 23% | Частично — LLM narrative |
| 3 | Rhythm | 10% | Librosa beat tracking + VAD |
| 4 | Eye Trace | 7% | MediaPipe gaze |
| 5 | 2D Space | 5% | Face tracking (есть) |
| 6 | 3D Space | 4% | Не автоматизируется |

**Murch: «Если кат эмоционально правильный — зритель простит любую техническую ошибку».** → emotion score = primary signal, rhythm = secondary.

### Численные правила

**TikTok / Reels / Shorts:**
- Средняя длина шота в топовых Shorts 2024: **2.5 сек** (35% выше completion rate vs 4+ сек)
- Completion rate 75-85% при длительности 15-30 сек
- Правило 3 сек: «Что-то новое каждые 3 секунды» (Adobe Creative Cloud 2025: attention drop после 2.7 сек)
- B-roll: 1-3 сек каждый

**Диалог vs Action:**
- Action: 1-2 сек (beat-synced)
- Dialog / talking-head: 2-5 сек
- **Punchline pause: 0.3-0.6 сек ПОСЛЕ тезиса** — алгоритм часто сжимает, монтажёр держит
- Между смысловыми блоками: минимум 1.0-1.5 сек на последнем кадре

**Числовая шкала для videomaker:**

| EMOTION_SIGNAL | CUT_HOLD_AFTER |
|---|---|
| high energy | 0.2-0.4 сек (быстро cut away) |
| punchline peak | 0.35-0.6 сек (пауза ДО cut) |
| neutral content | 1.5-3.0 сек |
| question/hook | 0.5-0.8 сек (cut на ожидании) |
| emotional peak | 2.0-4.0 сек (дать осесть) |

**MrBeast pacing (2026 data):**
- Micro-payoff каждые 30-60 сек для retention
- Сдвиг от hyper-stimulation к breathing room
- Звуковой нарратив (risers, silence, impacts) важнее визуала

---

## 3. Visual Transitions — когда какой тип

| Transition | Длина | Триггер | Реализация |
|---|---|---|---|
| Hard cut | 0 мс | Default. Action, energy, смена темы | `ffmpeg concat` |
| J-cut | −200 до −500 мс | Плавный, аудио «тянет» вперёд | moviepy audio offset |
| L-cut | +200 до +500 мс | Aftermath, аудио ещё идёт | audio_clip.set_start() |
| Cross-dissolve | 200-800 мс | Смена времени/места | ffmpeg `fade` |
| Dip to black | 300-1000 мс | Конец секции, cliffhanger | `fade=type=out` |
| Whip pan | 80-200 мс | Энергия, excitement | ffmpeg + motion blur |
| Speed ramp | 300-1500 мс | Climax, slow-mo reveal | moviepy `fl_time` + bezier |
| Match-cut | 0 мс | Визуальное сходство кадров | OpenCV optical flow match |
| Morph cut | 100-400 мс | Скрыть jump cut в talking-head | Только NLE, **нет open-source Python** |

### AI-driven transition choice 2026

**V-Trans4Style** (arXiv:2501.07983, Jan 2025, Guhan/Huang/Manocha):
- Transformer encoder-decoder, рекомендует transitions для стиля (documentary/drama/channel)
- AutoTransition++ dataset: 6k видео
- Улучшение 10-80% Recall@K vs baseline (AutoTransition ECCV 2022)
- GitHub: `acherstyx/AutoTransition` (65 stars, Python, MIT)
- Единственный 2025 paper напрямую по video production style transfer

**Сигналы для автоматического выбора:**
- Optical flow cosine similarity > 0.7 → match-cut кандидат
- Sentiment shift positive→negative → cross-dissolve или dip to black
- Same speaker continuing → J/L-cut
- Energy peak → hard cut (не смягчать)
- Audio onset → hard cut на onset

---

## 4. Emphasis Motion Effects

### Punch-in zoom (самый важный)

- Вход: 1.00x → 1.06-1.12x за **100-200 мс** с ease-in
- Триггер: ключевое слово / emotional peak / punchline
- Возврат: 1.12x → 1.00x за **300-500 мс** (медленнее входа)
- Max для natural feel: **1.15x** (больше — cartoonish)

```python
# FFmpeg zoompan: punch-in 150мс @ 30fps
# 5 кадров нарастание → hold → 10 кадров выход
subprocess.run([
    "ffmpeg", "-i", "clip.mp4",
    "-vf", "zoompan=z='min(zoom+0.012,1.06)':d=5:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
    "-c:v", "libx264", "out.mp4"
])
```

### Ken Burns (для статики)
- Slow drift: 0.3-0.5% scale per second
- За 5 сек: 1.00x → 1.025x
- Направление: к лицу / ключевому объекту

### Speed ramp (для B-roll transitions)
- 1.0x → 0.3x за 15 frames → hold → 1.0x за 15 frames
- Accelerate out: 1.0x → 3.0x → cut (momentum)

```python
from moviepy import VideoFileClip
clip = VideoFileClip("clip.mp4")
def speed_ramp(t, total=clip.duration):
    progress = t / total
    speed = 0.5 + 2.5 * (progress * (1 - progress)) * 4
    return speed * t
ramped = clip.fl_time(speed_ramp)
```

### Horizontal pan в 9:16 crop
- Drift 2-5% ширины за длину шота
- По направлению взгляда субъекта

---

## 5. Eye Trace и Motion Continuity

**Проблема:** субъект смотрит вправо в конце A → зритель ожидает «пространство для взгляда» слева в B. Нарушение = jump.

### MediaPipe Face Mesh (MIT)
- Iris tracking, 468 landmarks
- Landmarks 468/473 = iris centers
- 30+ FPS на CPU для 720p

```python
import mediapipe as mp

face_mesh = mp.solutions.face_mesh.FaceMesh(refine_landmarks=True)

def get_gaze_direction(frame):
    results = face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    if not results.multi_face_landmarks:
        return None
    lms = results.multi_face_landmarks[0].landmark
    left_iris = lms[468]; right_iris = lms[473]
    gaze_x = (left_iris.x + right_iris.x) / 2 - 0.5  # >0 = вправо
    return gaze_x
```

### Continuity principles

1. Gaze direction разница > 0.3 между концом A и началом B → warn / корректировка кропа
2. `cv2.calcOpticalFlowFarneback` на последних 5 frames A и первых 5 frames B → cosine similarity
3. 180-degree rule: side-of-frame check при смене шота

### DeepSORT для subject tracking
- `deep-sort-realtime` (PyPI) + YOLOv8 + CLIP embedding для ID matching
- При cross-context: subject position continuity

---

## 6. Rhythm Matching — Prosody для речи

### Текущая проблема T2.5
Beat-snap ±0.15 сек к librosa beats. В speech видео нет beats → нужен **onset snap** к речевым акцентам.

### Parselmouth 0.4.7 (Python для Praat, MIT)

```python
import parselmouth, numpy as np

snd = parselmouth.Sound("audio.wav")
pitch = snd.to_pitch()
intensity = snd.to_intensity()

intensity_values = intensity.values[0]
times = intensity.xs()
mean_i = np.mean(intensity_values)
std_i = np.std(intensity_values)
# Stressed syllable = intensity > mean + 0.5*std
stressed_times = times[intensity_values > mean_i + 0.5 * std_i]
```

### OpenSMILE Python (Apache-2.0)

```python
import opensmile
smile = opensmile.Smile(
    feature_set=opensmile.FeatureSet.eGeMAPSv02,  # 88 features
    feature_level=opensmile.FeatureLevel.LowLevelDescriptors,
)
features = smile.process_file("audio.wav")
# loudness_sma3 — энергетический контур 10мс hop
# F0semitoneFrom27.5Hz_sma3nz — pitch контур
```

### Правила cut-to-prosody

**Downbeat vs offbeat:**
- Cut на downbeat → уверенность, утверждение
- Cut на offbeat → тревога, юмор, неожиданность
- Talking-head: cut на **onset of stressed syllable** → snap/energy

**Speech onset (librosa):**

```python
onset_env = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units='time')
# Cut на ближайший onset ±0.08 сек (не ±0.15 к beat)
```

**Silence-to-speech onset:**
- Пауза > 0.25 сек + speech onset → идеальный cut point
- Пауза < 0.1 сек → не резать (inter-syllabic gap, не пауза)

**Pitch contour rule для punchline:**
- Punchline = pitch drop в конце фразы (final lowering)
- После final lowering + pause > 0.3 сек → cut с высоким emotional приоритетом

---

## 7. Consistency Signature между Рилсами

**Проблема:** каждый рилс может иметь разный pacing profile. У профессионала есть почерк.

### V-Trans4Style — единственный paper 2025

Обучается на примерах конкретного канала, рекомендует transitions в том же стиле.

### Template-based approach (реалистично сейчас)

```python
PACING_PROFILE = {
    "shot_duration_distribution": {
        "min": 1.2, "mode": 2.5, "max": 6.0,
        "distribution": "log-normal"
    },
    "cut_rate_by_energy": {
        "low_energy": 4.0, "medium_energy": 2.5, "high_energy": 1.5,
    },
    "transition_weights": {
        "hard_cut": 0.75, "j_cut": 0.15, "l_cut": 0.08, "dissolve": 0.02,
    },
    "zoom_behavior": {
        "punch_in_probability": 0.3,
        "max_zoom": 1.08,
        "drift_speed": 0.003,
    }
}
```

### Style transfer research (НЕ production-ready 2026)
- EditProp (TMLR 2025): keyframe propagation — visual, не pacing
- RefVFX (arXiv:2601.07833): temporal effect transfer — lighting, не rhythm
- **Вывод:** для editing rhythm нет production tools. Только template-based реалистичен.

### User preference learning (связка с T6)
- После каждого одобренного рилса → записываем shot_duration, transition_types, zoom_events
- Bayesian update профиля пользователя
- После 5-10 рилсов → персонализированный Pacing Profile

---

## 8. Ethics & Craft boundaries

### Сигналы опасного компилирования

**Semantic shift detection:**
- Cosine similarity sentence embeddings < 0.4 → context manipulation risk
- Speaker sentiment shift > 0.5 между соседними сегментами → проверка
- Утверждение → опровержение от одного спикера → флаг

**Temporal coherence:**
- Сегменты из ±30 сек → безопасно
- Сегменты > 5 мин apart → требует LLM narrative justification
- Противоположный sentiment от одного спикера → high-risk flag

### Industry standards 2025-2026
- Meta AI Content Policy (2025): обязательная маркировка при «material risk of misleading»
- EU AI Act (2025): прозрачность для AI-generated media, C2PA watermarking
- YouTube policy: crackdown on «mass-produced» content

### Для videomaker
- Cross-Context Risk Score в reducer
- Флаг при: semantic distance > threshold, temporal gap > 5 мин, sentiment reversal
- UI signal: «этот рилс из разных контекстов — проверьте перед публикацией»

---

## 9. Industry Breakdowns — сигнатуры лучших

### MKBHD (tech reviews)
- Clean hard cuts, почти нет transitions
- **Breathing pauses: 0.3-0.5 сек перед ключевым тезисом**
- Shot duration: 3-6 сек demo, 1.5-2.5 talking head
- Равномерный pacing (нет dramatic acceleration)
- B-roll illustrative

**Автоматизируется:** pause detection перед ключевыми словами (Parselmouth energy). Clean cut timing. B-roll semantic alignment.

### Casey Neistat (vlog)
- Whip pan transitions (swish)
- Jump cuts как creative tool
- Fast cuts 0.8-1.5 сек средняя
- Title cards как rhythm breaks
- **Rough edges намеренно**

**Автоматизируется:** whip pan detection через optical flow. Jump cut detection. Сложно автоматизировать imperfection.

### Kurzgesagt (animated)
- Smooth, deliberate: 3-7 сек per shot
- Cut на завершении мысли, не середине слова
- **Pause for understanding: 0.5-1.0 сек после сложного концепта**
- Audio-visual sync
- Rhythm accelerates при excitement, decelerates при reflection

**Автоматизируется:** semantic boundary detection. Pause-for-understanding через complexity score от LLM. Beat-to-motion sync.

### Vox / Johnny Harris
- Data viz reveals timed к речи
- Question-driven cuts (сразу после вопроса)
- Tension arc: slow → rapid → resolution → slower
- Signature: long shot → zoom in → cut

**Автоматизируется:** question detection (punctuation + prosody). Tension arc через speech energy. Progressive zoom.

### MrBeast (2025-2026)
- Mini-payoffs каждые 30-60 сек
- Сдвиг от rapid cuts к breathing room
- **Sound design driving retention больше визуала**
- Hook в первые 3 сек без исключений

**Автоматизируется:** retention hook detection. Mini-payoff scheduling. Sound design alignment.

---

## A) СВОДНАЯ ТАБЛИЦА «Проблема → Решение → Effort → Impact»

| # | Проблема | Решение | Библиотека | Effort | Impact |
|---|---|---|---|---|---|
| 1 | Flat pacing | Variable shot duration по emotion | Parselmouth + sentiment | M | **HIGH** |
| 2 | **Нет punchline pause** | Post-punchline hold 0.35-0.6 сек | VAD + pitch final lowering | **S** | **HIGH** |
| 3 | Монотонные transitions | Signal-based transition choice | V-Trans4Style или rule-based | M | MEDIUM |
| 4 | **Нет emphasis zoom** | Punch-in на stressed syllables | FFmpeg zoompan + Parselmouth | **S** | **HIGH** |
| 5 | Gaze continuity | Eye trace check cross-cuts | MediaPipe Face Mesh iris | M | MEDIUM |
| 6 | **Beat-snap не работает на речи** | Prosody onset snap ±0.08 | librosa onset + Parselmouth | **S** | **HIGH** |
| 7 | **Inconsistency между рилсами** | Pacing Profile + preference | Rule-based + Bayesian | M | **HIGH** |
| 8 | Context manipulation | Cross-Context Risk Score | Semantic similarity + temporal | M | MEDIUM |
| 9 | Ken Burns static shots | Slow drift 0.3%/сек | FFmpeg zoompan | **XS** | MEDIUM |
| 10 | J/L-cut absence | Audio offset ±200-400мс | moviepy | S | MEDIUM |

---

## B) TOP-5 улучшений — приоритет effort/impact

### 1. Punchline Pause Detection (S, HIGH) ⭐

После punchline / завершённой мысли — пауза 0.35-0.55 сек перед cut.

**Почему:** один из самых заметных признаков профессионального монтажёра. Алгоритмы убирают все паузы. Нужно вернуть **выбранные**.

```python
import parselmouth, numpy as np

def detect_punchline_moments(audio_path, transcript_segments):
    snd = parselmouth.Sound(audio_path)
    pitch = snd.to_pitch()
    punchlines = []
    for seg in transcript_segments:
        end_time = seg['end']
        start_window = max(0, end_time - 0.3)
        pitch_slice = pitch.get_value_at_time(end_time)
        pitch_before = pitch.get_value_at_time(start_window)
        if pitch_before and pitch_slice:
            if pitch_before - pitch_slice > 20:  # 20 Hz drop = significant
                punchlines.append({'time': end_time, 'hold': 0.45})
    return punchlines
```

**Интеграция:** Stage 8 (rhythm check) — не сжимать паузы после punchline. Добавить `punchline_hold_frames` в timeline builder.

### 2. Variable Shot Duration by Emotion (M, HIGH)

```python
DURATION_BY_ENERGY = {
    (0.0, 0.3): 3.5,
    (0.3, 0.6): 2.5,
    (0.6, 0.8): 1.8,
    (0.8, 1.0): 1.2,
}
```

**Сигналы:** openSMILE loudness_sma3 + pitch variance + LLM sentiment.

### 3. Prosody-Aware Cut Snapping (S, HIGH) ⭐

Замена T2.5 beat-snap ±0.15 на onset-snap ±0.08 к speech onsets.

```python
def snap_to_speech_onset(cut_time, audio, sr=16000, window=0.08):
    onset_env = librosa.onset.onset_strength(y=audio, sr=sr, aggregate=np.median)
    onset_times = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, units='time',
        pre_max=0.03, post_max=0.03, pre_avg=0.1, post_avg=0.1
    )
    candidates = onset_times[np.abs(onset_times - cut_time) < window]
    if len(candidates) > 0:
        return candidates[np.argmin(np.abs(candidates - cut_time))]
    return cut_time
```

### 4. Punch-In Zoom on Stressed Syllables (S, HIGH) ⭐

1.00x → 1.06x за 5 кадров + hold 15 frames + 10 frames возврат.

```python
def generate_zoom_keyframes(stressed_moments, fps=30):
    return [{
        'start_frame': int(m['time'] * fps),
        'zoom_in': 5, 'peak_zoom': 1.06,
        'hold': 15, 'zoom_out': 10,
    } for m in stressed_moments]
```

**Интеграция:** T2.1 zoom_planner — добавить stressed_syllable source к existing face-based zoom.

### 5. Pacing Profile + Consistency Engine (M, HIGH)

```python
DEFAULT_PACING_PROFILES = {
    "dynamic": {
        "shot_duration_mode": 1.8, "shot_duration_max": 4.0,
        "punch_in_rate": 0.4, "transition_hard_cut_ratio": 0.85,
    },
    "documentary": {
        "shot_duration_mode": 3.5, "shot_duration_max": 8.0,
        "punch_in_rate": 0.15, "punchline_hold": 0.5,
        "transition_hard_cut_ratio": 0.70,
    },
    "mkbhd_clean": {
        "shot_duration_mode": 2.8, "punchline_hold": 0.4,
        "punch_in_rate": 0.2, "transition_hard_cut_ratio": 0.95,
    }
}
```

---

## C) Что НЕ автоматизируется (граница машины и ремесла)

1. **Emotion as primary editorial judgment** — Murch отдаёт 51% весу эмоциям. Алгоритм детектирует energy peaks, pitch, sentiment — но не понимает emotional rightness для narrative.
2. **Намеренная imperfection** — Casey оставляет shake/jump cuts. Алгоритм сглаживает.
3. **Cross-context без manipulation** — требует understanding авторского намерения, этической позиции.
4. **Conceptual match-cuts** — Kubrick bone → space station: визуальное + концептуальный leap. Визуал auto, концепт — нет.
5. **Breathability** — MrBeast сдвиг к breathing room = non-trivial decision от macro-arc.
6. **Real-time адаптация к зрителю** — понимание что эта аудитория почувствует в конкретном cut.

**Граница:** машина решает **когда** резать (temporal). Плохо решает **зачем** (narrative). Не решает **как именно** (craft — тип перехода, пауза, motion).

**Цель videomaker:** не заменить монтажёра, а дать 60% работы. Автоматизируй algorithmically detectable (punchline pause, onset snap, punch-in zoom). Оставляй human review для narrative coherence.

---

## НУМЕРИЧЕСКИЕ КОНСТАНТЫ (для внедрения)

```python
EDITING_CRAFT_CONSTANTS = {
    # Shot duration
    "min_shot_duration": 1.2,
    "max_shot_duration": 6.0,
    "default_duration": 2.5,

    # Punchline / emphasis timing
    "punchline_hold_after_sec": 0.45,
    "question_hold_sec": 0.6,

    # Speech onset snap
    "onset_snap_window_sec": 0.08,
    "beat_snap_window_sec": 0.15,  # legacy для music

    # Punch-in zoom
    "punch_in_zoom_scale": 1.06,
    "punch_in_frames": 5,           # @30fps = 167мс
    "punch_in_hold_frames": 15,     # 500мс на пике
    "punch_out_frames": 10,         # 333мс возврат
    "punch_in_probability": 0.30,

    # Ken Burns drift
    "ken_burns_scale_per_frame": 0.0003,
    "ken_burns_max_scale": 1.025,

    # Transitions
    "j_cut_offset_sec": 0.3,
    "l_cut_offset_sec": 0.3,
    "cross_dissolve_duration_sec": 0.4,
    "dip_to_black_duration_sec": 0.5,

    # Energy thresholds
    "high_energy_threshold": 0.65,
    "low_energy_threshold": 0.35,

    # Cross-context safety
    "semantic_similarity_min": 0.4,
    "temporal_gap_risk_sec": 300,   # >5 мин
    "sentiment_shift_threshold": 0.5,
}
```

---

## АННОТИРОВАННАЯ БИБЛИОГРАФИЯ

- **Walter Murch, "In the Blink of an Eye" (1992/2001)** — Rule of Six с весами. Единственная публично доступная иерархия приоритетов от практика мирового уровня. Применяется как priority scoring для AI cut decisions.
- **V-Trans4Style (arXiv:2501.07983, январь 2025)** — единственный 2025 paper напрямую по video production style transfer. Transformer encoder-decoder. Recall@K +10-80% vs baseline.
- **AutoTransition (ECCV 2022, acherstyx)** — оригинальный dataset + baseline. Python, MIT.
- **CutClaw (arXiv:2603.29664, март 2026)** — multi-agent framework для music-synced editing.
- **ESA Energy-Based Shot Assembly (arXiv:2511.02505, ноябрь 2025)** — energy optimization для shot sequencing + artistic expression.
- **HIVE (EMNLP 2025, ByteDance)** — human-inspired video editing framework с character/dialogue/narrative.
- **PySceneDetect 0.6.7 (2025)** — ContentDetector + AdaptiveDetector.
- **Parselmouth 0.4.7** — Python Praat wrapper для prosody (pitch, intensity, formants).
- **OpenSMILE Python (audeering, Apache 2.0)** — eGeMAPSv02 88 features, ComParE 6373. Industry standard.
- **MoviePy v2.2.1 (май 2025)** — 14.5k stars. fl_time() для speed ramp, audio offset для J/L.
- **MediaPipe Face Mesh (Google, Apache 2.0)** — 468 landmarks + iris (468, 473). 30+ FPS CPU.

---

## КОНЦЕПТУАЛЬНАЯ КАРТА

```
AUDIO SIGNALS              VISUAL SIGNALS           LLM SIGNALS
─────────────              ───────────────          ───────────
Pitch (Parselmouth)     ─┐ Face gaze (MediaPipe)─┐  Sentiment
Intensity envelope      ─┤ Motion (OpenCV flow) ─┤  Narrative arc
Speech onsets (librosa) ─┤ Subject (DeepSORT)   ─┤  Punchline
Silence (VAD)           ─┤                      ─┤  Semantic shift
                        ─┘                      ─┘
                                  ↓
                  ┌───────────────────────────┐
                  │  PACING DECISION ENGINE    │
                  │  (Pacing Profile Template) │
                  └───────────────────────────┘
                                  ↓
  Shot Duration         Transition Type        Emphasis Motion
  (Variable by energy)  (Signal-based choice)  (Punch-in, Ken Burns)
       │                       │                       │
  [1.2-6.0 сек]         [Hard/J/L/Dissolve]     [Zoom ×1.06, Speed ramp]
                                  ↓
                  ┌───────────────────────────┐
                  │  CONSISTENCY ENFORCER     │
                  │  (Pacing Profile check)   │
                  └───────────────────────────┘
                                  ↓
                    PROFESSIONAL-FEELING REEL
```
