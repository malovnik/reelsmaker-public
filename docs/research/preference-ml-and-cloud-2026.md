# Preference ML на лайках + Cloud Deployment 2026

**Дата:** 2026-04-19
**Источник:** deep-research-analyst agent (77K tokens, 22 tool uses)
**Связано с:** `consolidated-action-plan.md` → секции T6 и T7

Этот документ — полный research-отчёт. План проекта содержит краткие выжимки (T6, T7) со ссылкой сюда для деталей.

---

## СЕКЦИЯ 1 — PREFERENCE ML НА ЛАЙКАХ

### 1.1 Контекст

Исходная ситуация: few-shot промптинг с топ-8 hook-фразами из лайкнутых рилсов (`services/preference_memory.py`). Это уже персонализация через retrieval — вопрос в том, даст ли более сложный ML прирост, оправдывающий затраты.

Ключевая переменная: объём данных. При 50 лайках и одном пользователе условия принципиально отличаются от академических бенчмарков, где тысячи пар от сотен аннотаторов.

### 1.2 Пять подходов — сравнение

#### Подход 1: Retrieval-Augmented Rank (bi-encoder + cosine similarity)

Суть: эмбеддинг каждого нового кандидата-рилса сравнивается с эмбеддингами лайкнутых через косинусное сходство. Топ-N ближайших лайков инжектятся в промпт.

- **Данные:** от 10 лайков. Улучшение над random заметно с 15-20 примеров.
- **Прирост над текущим few-shot:** умеренный — полный embedding может поймать стиль/ритм/структуру, которые фраза не передаёт.
- **Компьют:** 0 мс training, <5 мс inference.
- **Библиотеки:** numpy + PostgreSQL с pgvector. Не нужны ML-библиотеки.

#### Подход 2: Shallow Reward Model (MLP поверх embedding)

Суть: берёшь embeddings лайкнутых (positive) и нелайкнутых (negative) рилсов, обучаешь маленькую двуслойную MLP предсказывать score: 0 = dislike, 1 = like.

- **Данные:** 50-100 примеров (liked + not liked). Для 50 примеров — жёсткая регуляризация (dropout 0.3-0.5 + L2).
- **Прирост над retrieval:** +5-15% при n>150.
- **Training:** <30 сек CPU для 500 примеров, 50 эпох. Инкрементальный retrain: 2-5 сек.
- **Inference:** <1 мс (forward pass через две матрицы 256x128 и 128x1).
- **Библиотеки:** sklearn `MLPClassifier` 1.4+ или torch.

#### Подход 3: SetFit (Sentence Transformers Few-Shot Fine-Tuning)

Контрастивный fine-tuning sentence-transformer на позитивных/негативных парах + классификационная голова.

- **Версия:** setfit 1.1.3 (август 2025), 212K скачиваний/мес.
- **Данные:** 8-16 примеров на класс (hard lower bound).
- **Training:** 3-7 мин CPU для 50 примеров. Модель ~400 MB (MiniLM) или ~1.3 GB (mpnet).
- **Inference:** 20-50 мс CPU (значительно медленнее MLP).
- **Проблема:** оптимизирован для классификации, наша задача — ranking. SetFit даёт бинарный score, не непрерывный ранг.

**Вердикт:** избыточен. Gemini embedding + MLP проще и быстрее.

#### Подход 4: DPO / KTO для маленьких LLM

Дообучение open-source LLM 1-3B (Phi-3.5-mini, Qwen2.5-1.5B) через Direct Preference Optimization на парах (preferred, rejected).

- **Критическая проблема:** DPO/KTO обучает **генерацию**, а нам нужен **scoring**. Архитектурное несоответствие задаче.
- **KTO** практичнее (непарные сигналы), но всё равно требует ~100-200 примеров.
- **Компьют:** 15-20 мин GPU RTX 4090 или 2-3 часа M2 Pro для 500 примеров.
- **RAM:** ~8 GB для 1B модели + LoRA adapters в bfloat16.

**Вердикт:** не рекомендуется. Не соответствует задаче.

#### Подход 5: Контрастивное обучение embeddings

Fine-tune embedding модель через triplet loss, чтобы liked рилсы кластеризовались, а disliked — отталкивались.

- **Проблема:** Gemini embedding — closed API, нельзя fine-tune. Нужен переход на локальный sentence-transformer (E5, BGE, mpnet).
- **Данные:** ~50-100 триплетов. Критична генерация hard negatives.
- **Компьют:** 5-10 мин CPU fine-tuning. Модель ~90 MB. Inference 15-30 мс.
- **Прирост:** +10-20% recall@5 при n>200.

**Вердикт:** интересен как upgrade от 200-300+ примеров. До этого — преждевременная оптимизация.

### 1.3 Сравнительная таблица

| Подход | Минимум данных | Прирост над few-shot | Компьют train | Компьют inference | Сложность | Gemini emb. |
|---|---|---|---|---|---|---|
| Retrieval rank (cosine) | 10 liked | +5-10% | 0 мс | <5 мс | Низкая | Полная |
| MLP reward model | 50+50 | +10-20% при n>150 | <30 сек CPU | <1 мс | Низкая | Полная |
| SetFit | 16 итого | +10-15% | 3-7 мин CPU | 20-50 мс | Средняя | Нет |
| Contrastive fine-tune | 100 триплетов | +10-20% при n>200 | 5-10 мин CPU | 15-30 мс | Средняя | Нет |
| DPO / KTO | 200+ | Нерелевантен | 15-20 мин GPU | 50-200 мс | Высокая | Нет |

### 1.4 Реалистичный порог: когда ML бьёт few-shot промптинг

- **< 30 лайков:** любой ML хуже хорошего few-shot. Текущий подход — оптимален.
- **30-100:** MLP reward model начинает давать прирост (если есть negatives). Без negatives — cosine retrieval уже хорошо.
- **100-300:** MLP полноценно работает. Contrastive fine-tuning оправдан.
- **300+:** полноценный bi-encoder с personalised embeddings. KTO на small LLM для генерации hook-фраз в стиле пользователя.

**Single-user ограничение:** нет collaborative filtering сигнала. Matrix factorization неприменима.

### 1.5 Рекомендация

**Фаза 1 (30-100 лайков): Cosine retrieval с Gemini embeddings**

Переключить few-shot с «топ-8 фраз» на «топ-5 лайкнутых рилсов по cosine similarity» в 256-dim пространстве. PostgreSQL + pgvector, `vector(256)` column, `<=>` оператор. При <500 записей индекс не нужен.

**Фаза 2 (100+ с negatives): sklearn MLP reward scorer**

```python
from sklearn.neural_network import MLPClassifier

model = MLPClassifier(
    hidden_layer_sizes=(128, 64),
    activation='relu',
    alpha=0.01,      # L2
    dropout=0.3,
    max_iter=200,
    random_state=42
)
model.fit(X_train, y_train)
scores = model.predict_proba(candidate_embeddings)[:, 1]
```

Retrain <10 сек CPU в background. Serialization через `joblib` (~200 KB).

**Не делать:** DPO, SetFit, contrastive fine-tune. ROI слишком низкий при текущих объёмах.

---

## СЕКЦИЯ 2 — CLOUD DEPLOYMENT 2026

### 2.1 Исходные данные

- **Нагрузка:** 50 видео/мес (10-15/неделю)
- **Baseline на M2 Pro:** 30 мин видео → GPU активен 7-8 мин
- **На A40 (Replicate):** Whisper large-v3-turbo RTF ~0.005-0.008x → 20-35 сек GPU для 30 мин аудио
- **Общий GPU time/видео:** ~30-60 сек на 30-мин видео, ~120-240 сек на 2-часовое
- **Средний микс:** ~90 сек GPU/видео
- **Месячный total:** 50 × 90 = **4500 сек = 75 минут чистого GPU/мес**

### 2.2 Сценарий A — Per-second GPU

#### A1: Replicate.com

**Актуальные цены (апрель 2026):**

| Hardware | $/сек | $/час |
|---|---|---|
| T4 | $0.000225 | $0.81 |
| L40S | $0.000975 | $3.51 |
| A100 80GB | $0.001400 | $5.04 |
| H100 | $0.001525 | $5.49 |

Custom cog-контейнер можно упаковать под весь pipeline. **A40 исчез из прайса** — используем L40S. Расчёт для L40S: 4500 × $0.000975 = **$4.39/мес**. Cold start 30-90 сек для custom cog.

Ограничение: нет нативного FastAPI хостинга — backend нужно отдельно.

#### A2: Modal.com ⭐

**Актуальные цены:**

| GPU | $/сек |
|---|---|
| T4 | $0.000164 |
| L4 | $0.000222 |
| A10 | $0.000306 |
| A100 40GB | $0.000583 |
| A100 80GB | $0.000694 |
| L40S | $0.000542 |
| H100 | $0.001097 |

**Cold start:** с caching — 3-10 сек для A10G с предзагруженной Whisper.

**Расчёт для A10G (24 GB — достаточно для Whisper large-v3-turbo):**
- 4500 × $0.000306 = **$1.38/мес GPU**
- Cold starts: 10 сек × $0.000306 × 50 = $0.15
- **Starter free tier: $30/мес credits** → реально $0-3/мес

**Ключевое преимущество:** FastAPI + GPU workers в одном `modal.App` через `@modal.fastapi_endpoint` + `@app.function(gpu="A10G")`.

#### A3: RunPod Serverless

**Цены:**

| GPU | VRAM | Flex $/сек | Active $/сек |
|---|---|---|---|
| A4000 | 16 GB | $0.00016 | $0.00011 |
| L4/A5000 | 24 GB | $0.00019 | $0.00013 |
| A6000/A40 | 48 GB | $0.00034 | $0.00024 |
| L40S | 48 GB | $0.00053 | $0.00037 |

**FlashBoot:** P95 cold start для Whisper endpoint **<2.3 сек**.

**Расчёт A4000:** 4500 × $0.00016 = **$0.72/мес GPU**. Дешевле всех, но только inference endpoint — backend отдельно.

### 2.3 Сценарий B — Dedicated GPU VPS 24/7

#### B1: Hetzner GEX44

- **GPU:** NVIDIA RTX 4000 SFF Ada, 20 GB GDDR6 ECC
- **CPU:** i5-13500, 64 GB DDR4, 2x 1.92 TB NVMe
- **Цена:** **€184/мес** + €264 setup fee
- **Локация:** Nuremberg / Falkenstein

Для 75 минут GPU time/мес — это **$147/час эффективной ставки**. Абсурд для личного использования.

#### B2: OVH Public Cloud GPU

| Инстанс | GPU | $/час |
|---|---|---|
| l4-1-gpu | NVIDIA L4 Ada 24 GB | $0.91 |
| l40s-1-gpu | NVIDIA L40S 48 GB | $1.69 |

Почасовая тарификация, минимум 1 час. Для 50 job по ~2 мин — 50 часов × $0.91 = **$45.50/мес**. Дорого для bursty нагрузки.

#### B3: Lambda Labs / Paperspace / Vast.ai

| Provider | GPU | $/час |
|---|---|---|
| Lambda | A10 | $0.75 |
| Lambda | A100 SXM 80GB | $1.29 |
| Lambda | H100 SXM | $2.49 |
| Paperspace | A100 SXM 80GB | $1.15 |
| Paperspace | H100 SXM | $2.24 |
| Vast.ai | A40 | $0.32 |
| Vast.ai | RTX 4090 | $0.29-0.40 |

Vast.ai — нестабильность, uptime не гарантирован.

### 2.4 Сценарий C — Гибрид (рекомендуемый)

**Архитектура:**

```
Browser → Hetzner CX32 (DE, €9.18/мес)
          ├─ Next.js frontend
          ├─ FastAPI backend
          ├─ PostgreSQL + Redis
          ├─ Moondream 2 GGUF (CPU, 2 GB int4, 3-5 сек/frame)
          └─ FFmpeg render (CPU)
             │
             ↓ .remote() call для whisper stage
             │
          Modal.com (US, A10G serverless)
          └─ mlx-whisper endpoint
             ~90 сек GPU per видео
```

**Hetzner CX32:** 4 vCPU AMD, 8 GB RAM, 80 GB SSD, €9.18/мес (после апрельского повышения 2026).

**Итого:**
- Hetzner CX32: ~$10/мес
- Modal GPU: $0-3/мес (free tier)
- Cloudflare R2 (10 GB артефактов): $0.15/мес
- Gemini API (50 видео): $1-5/мес
- **Total: $12-17/мес**

### 2.5 Итоговая таблица

| Сценарий | Base $/мес | + 50 видео | Cold start | Сложность |
|---|---|---|---|---|
| A1: Replicate L40S | $0 | ~$5 GPU | 15-90 сек | Средняя |
| A2: Modal A10G ⭐ | $0 (free tier) | ~$1-3 GPU | 3-15 сек | **Низкая** |
| A3: RunPod A4000 | $0 | <$1 GPU | 0.5-2.3 сек | Средняя |
| B1: Hetzner GEX44 | €184 | €184 | 0 | Высокая |
| B2: OVH L4 | hourly $0.91 | ~$45 | 2-5 мин | Средняя |
| B3: Lambda A10 | hourly $0.75 | ~$37 | 2-5 мин | Средняя |
| **C: Hetzner CX32 + Modal** ⭐ | **€9** | **+$1-3** | 3-15 сек (только GPU) | **Низкая** |

### 2.6 Детали платформ

**Replicate:** custom cog-контейнер возможен, но нет FastAPI хостинга. A40 Large пропал из прайса. Cold start 30-90 сек для custom cog.

**Modal:** единственный provider с нативной поддержкой FastAPI + GPU workers в одном `modal.App`. Декораторы `@modal.fastapi_endpoint` + `@app.function(gpu="A10G")`. Starter free tier $30/мес credits — покрывает весь use-case.

**RunPod FlashBoot:** P95 cold start 0.5-2.3 сек для Whisper. Без FlashBoot — 10-42 сек.

**Европейские хостеры:**
- Hetzner — только GEX dedicated (нет cloud GPU)
- OVH — L4 $0.91/hr, L40S $1.69/hr, FR
- Scaleway — от $0.83/hr, FR
- Lyceum — от €0.39/hr, EU-sovereign
- Nebius — $1.55+/hr, NL

---

## ФИНАЛЬНАЯ РЕКОМЕНДАЦИЯ

### Preference ML
1. **Сейчас (30-100 лайков):** cosine retrieval по Gemini embeddings поверх текущего few-shot. Нулевой overhead, уже есть infrastructure.
2. **При 100+ с negatives:** sklearn MLP (128, 64) как reward scorer в reducer/composer. joblib serialization.
3. **Не трогать:** DPO, KTO, SetFit, contrastive fine-tune — ROI не оправдан.

### Cloud Deployment
**Сценарий C: Hetzner CX32 + Modal A10G**, итого **$12-17/мес** для 2-3 пользователей.

Аргументы:
- Modal — единственный provider с FastAPI + GPU в одном app
- Free tier $30/мес credits покрывает все 50 видео
- Hetzner CX32 в Германии — Gemini API без блокировок
- Cold start 3-15 сек допустим для batch pipeline
- Moondream 2 GGUF работает на CPU — не нужен dedicated GPU
- Dedicated GPU (€184/мес) — абсурд для 75 минут GPU time/мес
