"""Stage 5.2.5 — Canvas Embedder: semantic memory для downstream retrieval.

Заполняет ``embedding`` на каждом ``CanvasCandidateMoment`` оригинальным
текстом фразы из диапазона [moment.start, moment.end]. Это не абстрактный
one_liner от LLM, а plain-speech из транскрипта — выше semantic density,
точнее retrieval.

Используется downstream:
* **Reducer (Stage 6):** dedup по cosine similarity вместо Jaccard по
  one_liner — ловит перефразировки одной мысли.
* **Story Doctor (Stage 7):** retrieval кандидатов на замену слабой
  концовки или плоского хука.
* **Reels Composer:** cross-reel diversity filter — не пускаем в один
  батч рилсы с semantically близкими моментами.

Fallback: если embed API недоступен или упал — возвращаем Canvas как
есть (``embedding=None``). Downstream consumers должны делать
``if moment.embedding is not None`` — graceful-degrade без потери
функционала.

Реализация использует ``gemini-embedding-001`` (актуальная prod-модель
Gemini Embeddings), ``output_dimensionality=256`` — хватает для semantic
similarity, экономит память Canvas-артефактов в 12× по сравнению с
нативными 3072-dim.
"""

from __future__ import annotations

import math

from videomaker.core.config import Settings
from videomaker.core.logging import get_logger
from videomaker.models.canvas import CanvasCandidateMoment, ProjectCanvas
from videomaker.services.transcribers.base import TranscribedWord

log = get_logger(__name__)

_MODEL_ID = "gemini-embedding-001"
"""Prod-модель Gemini Embeddings. Native 3072-dim, поддерживает
``output_dimensionality`` (Matryoshka-truncation) и ``task_type``."""

_DEFAULT_DIM = 256
"""Достаточно для cosine similarity между короткими фразами. Снижение
с 3072 до 256 даёт 12× экономию памяти Canvas-артефакта и ускоряет
cosine-компьют без заметной потери качества семантической близости."""

_BATCH_SIZE = 90
"""Gemini batch-limit ≤100 контентов за вызов, держим запас."""

_TASK_TYPE = "SEMANTIC_SIMILARITY"
"""Универсальный task_type для нашего микс-применения (dedup + retrieval +
diversity). Если кому-то из downstream нужен чистый retrieval —
пересчитывать локально с ``RETRIEVAL_QUERY`` не требуется, разница между
SEMANTIC_SIMILARITY и RETRIEVAL_* на dot-product близости минимальна
для коротких русских фраз."""


async def embed_canvas_moments(
    canvas: ProjectCanvas,
    words: list[TranscribedWord],
    *,
    settings: Settings,
    output_dim: int = _DEFAULT_DIM,
) -> ProjectCanvas:
    """Возвращает ``ProjectCanvas`` с заполненными ``embedding`` на candidate_moments.

    Immutability через ``model_copy``: исходный canvas не мутируется,
    возвращается новая структура. Если embed-вызов упал — возвращается
    тот же canvas без изменений (с логом предупреждения).
    """
    if not canvas.candidate_moments:
        return canvas

    texts = [_moment_text(moment, words) for moment in canvas.candidate_moments]

    try:
        embeddings = await _embed_batch(
            texts,
            settings=settings,
            output_dim=output_dim,
        )
    except Exception as exc:
        log.warning(
            "canvas_embedder_failed_fallback",
            moments=len(canvas.candidate_moments),
            error=str(exc),
        )
        return canvas

    if len(embeddings) != len(canvas.candidate_moments):
        log.warning(
            "canvas_embedder_length_mismatch_fallback",
            expected=len(canvas.candidate_moments),
            got=len(embeddings),
        )
        return canvas

    enriched: list[CanvasCandidateMoment] = []
    for moment, emb in zip(canvas.candidate_moments, embeddings, strict=True):
        if not emb:
            enriched.append(moment)
            continue
        enriched.append(moment.model_copy(update={"embedding": emb}))

    populated = sum(1 for m in enriched if m.embedding is not None)
    log.info(
        "canvas_embeddings_populated",
        total=len(enriched),
        populated=populated,
        dim=output_dim,
        model=_MODEL_ID,
    )

    return canvas.model_copy(update={"candidate_moments": enriched})


def _moment_text(
    moment: CanvasCandidateMoment,
    words: list[TranscribedWord],
) -> str:
    """Извлекает plain-speech из диапазона moment.

    Стратегия:
    1. Сначала ищем слова строго внутри [start, end].
    2. Если пусто (пауза / разрыв / рассинхрон) — fallback на частичное
       перекрытие: any word где [w.start, w.end] пересекается с диапазоном.
    3. Если и так пусто — возвращаем ``one_liner`` от LLM (всё ещё
       информативнее пустой строки для embedding).
    """
    inside = [
        w for w in words if w.start >= moment.start and w.end <= moment.end
    ]
    if inside:
        return " ".join(w.word for w in inside).strip() or moment.one_liner

    overlap = [
        w for w in words if w.start < moment.end and w.end > moment.start
    ]
    if overlap:
        return " ".join(w.word for w in overlap).strip() or moment.one_liner

    return moment.one_liner


async def _embed_batch(
    texts: list[str],
    *,
    settings: Settings,
    output_dim: int,
) -> list[list[float]]:
    """Batch-embed через ``gemini-embedding-001``.

    Пустые тексты превращаются в плейсхолдер ``(silent)`` — иначе API
    может вернуть 400. Нулевые векторы на таких фразах не создают
    ложной близости в cosine (numerator=0).
    """
    from google import genai
    from google.genai import types as genai_types

    if not settings.gemini_api_key:
        raise RuntimeError("gemini_api_key not set — canvas embedder unavailable")

    client = genai.Client(api_key=settings.gemini_api_key)
    safe_texts = [t if t.strip() else "(silent)" for t in texts]

    config = genai_types.EmbedContentConfig(
        output_dimensionality=output_dim,
        task_type=_TASK_TYPE,
    )

    values: list[list[float]] = []
    for start in range(0, len(safe_texts), _BATCH_SIZE):
        batch: list[str | genai_types.PIL_Image | genai_types.File | genai_types.Part] = list(
            safe_texts[start : start + _BATCH_SIZE]
        )
        resp = await client.aio.models.embed_content(
            model=_MODEL_ID,
            contents=batch,
            config=config,
        )
        for e in resp.embeddings or []:
            values.append(list(e.values or []))
    return values


async def embed_texts(
    texts: list[str],
    *,
    settings: Settings,
    output_dim: int = _DEFAULT_DIM,
) -> list[list[float]] | None:
    """Public batch-embed helper для любых коллекций текстов.

    Переиспользуется downstream стейджами (Reducer, Story Doctor) чтобы
    embed'ить evidence-items или arbitrary query-строки без дублирования
    кода Gemini-клиента.

    Возвращает ``None`` при сбое API — caller делает graceful-degrade.
    """
    if not texts:
        return []
    try:
        return await _embed_batch(
            texts,
            settings=settings,
            output_dim=output_dim,
        )
    except Exception as exc:
        log.warning(
            "embed_texts_failed_fallback",
            count=len(texts),
            error=str(exc),
        )
        return None


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float:
    """Cosine similarity для двух embeddings.

    Возвращает 0.0 если хотя бы один None / пустой / разной размерности.
    Safe для downstream графовых операций — 0.0 означает «неизвестно»,
    не «антиподобно».
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    denom = math.sqrt(na) * math.sqrt(nb)
    if denom <= 1e-9:
        return 0.0
    return dot / denom


__all__ = [
    "cosine_similarity",
    "embed_canvas_moments",
    "embed_texts",
]
