"""T2.2 — Cross-session preference memory.

Собирает примеры из ранее лайкнутых рилсов пользователя и отдаёт их
как few-shot anchors в extraction-промпты нового job'а. Через итерации
накапливается «вкус пользователя» — какие hook'и, эмоциональные пики,
мотивы он отмечает как сильные.

Два режима (переключаются через ``PerformanceSettings.preference_retrieval_mode``):

* ``top_by_date`` (legacy) — топ-N свежих лайков по дате без семантики.
  Простой и дешёвый. Работает всегда, даже если embeddings ещё не
  сохранены.
* ``cosine`` (T6.1, default) — топ-K семантически ближайших лайкнутых
  рилсов к текущему Canvas'у (по 256-dim Gemini embeddings). Находит
  релевантные примеры, а не просто свежие. Требует embeddings в
  ``Artifact.embedding_json`` — заполняется при проставлении лайка.
  Если ни у одного liked-артефакта embedding не сохранён (или query
  пустой) — автоматический fallback на ``top_by_date``.

ТРИЗ «обратная связь»: система учится НЕ через fine-tune (Gemini не
поддерживает для Flash Lite), а через включение примеров в промпт.
Самый дёшевый канал адаптации.

Lightweight: только чтение БД + artifacts/*/reel_plan.json, 0 LLM calls
(embeddings считаются при лайке, не при retrieval).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy import select

from videomaker.core.artifacts import ArtifactsManager
from videomaker.core.db import session_scope
from videomaker.core.logging import get_logger
from videomaker.models.job import Artifact, ArtifactKind

log = get_logger(__name__)


#: Максимум anchor-фраз в промпте для legacy top-by-date режима. Больше —
#: промпт раздувается и теряется фокус агента; меньше — слабый сигнал.
#: 6-8 — sweet spot.
_MAX_ANCHORS = 8

#: Максимум anchor-фраз для cosine retrieval режима. Семантически
#: отобранные — плотнее legacy top-8 по дате, хватает 5.
_MAX_COSINE_ANCHORS = 5

#: Максимальная длина одной anchor-фразы (chars). Обрезаем длинные hooks.
_MAX_ANCHOR_LEN = 180


async def load_liked_anchors_text(
    *,
    artifact_store: ArtifactsManager,
    current_job_id: str | None = None,
    max_anchors: int = _MAX_ANCHORS,
    retrieval_mode: str = "top_by_date",
    query_embedding: list[float] | None = None,
) -> str:
    """Возвращает plaintext с примерами лайкнутых hook'ов для инъекции в user payload.

    ``current_job_id`` — исключается из выборки (новый job, его рилсов ещё нет).

    ``retrieval_mode`` — ``"cosine"`` или ``"top_by_date"``. В cosine-режиме
    нужен ``query_embedding`` (256-dim эмбеддинг текущего Canvas'а). При
    отсутствии query_embedding или embeddings у лайкнутых рилсов —
    автоматический fallback на ``top_by_date``.

    Возвращает пустую строку если:
    - лайков нет
    - все reel_plan.json файлы недоступны / повреждены
    - artifact_store не умеет разрешить пути (graceful-degrade)
    """
    liked_entries = await _fetch_liked_artifacts(exclude_job_id=current_job_id)
    if not liked_entries:
        return ""

    use_cosine = (
        retrieval_mode == "cosine"
        and query_embedding is not None
        and len(query_embedding) > 0
    )

    anchors: list[str] = []
    mode_used: str = "top_by_date"

    if use_cosine:
        hook_emb_pairs = _build_hook_embedding_pairs(
            liked_entries, artifact_store=artifact_store
        )
        if hook_emb_pairs:
            cosine_hooks = retrieve_top_k_similar(
                query_embedding,
                hook_emb_pairs,
                k=min(max_anchors, _MAX_COSINE_ANCHORS),
            )
            if cosine_hooks:
                anchors = cosine_hooks
                mode_used = "cosine"
        if not anchors:
            log.info(
                "preference_memory_cosine_fallback",
                reason="no_embeddings_on_liked_or_empty_result",
                liked_count=len(liked_entries),
                with_embedding=sum(
                    1
                    for entry in liked_entries
                    if entry[1].get("_embedding") is not None
                ),
            )

    if not anchors:
        # Legacy top-by-date path (также используется как fallback от cosine).
        seen_hooks: set[str] = set()
        for entry in liked_entries:
            if len(anchors) >= max_anchors:
                break
            hook = _extract_hook_for_liked(entry, artifact_store=artifact_store)
            if not hook:
                continue
            hook_key = hook.lower().strip()
            if hook_key in seen_hooks:
                continue
            seen_hooks.add(hook_key)
            anchors.append(hook)

    if not anchors:
        return ""

    log.info(
        "preference_memory_anchors_selected",
        mode=mode_used,
        anchors_count=len(anchors),
    )

    lines = [
        "=== ИЗБРАННЫЕ ПОЛЬЗОВАТЕЛЕМ ФРАГМЕНТЫ (из предыдущих job'ов) ===",
        "Это примеры hook/момента которые пользователь отметил как сильные.",
        "Ориентируйся на их ЭНЕРГЕТИКУ и СТИЛЬ при поиске в текущем chunk'е —",
        "но не копируй буквально, ищи РОДСТВЕННЫЕ по интонации моменты.",
        "",
    ]
    for i, anchor in enumerate(anchors, start=1):
        lines.append(f"  {i}. «{anchor}»")
    return "\n".join(lines)


def retrieve_top_k_similar(
    current_candidate_embedding: list[float] | None,
    liked_reels_with_embeddings: list[tuple[str, list[float]]],
    k: int = 5,
) -> list[str]:
    """Top-K семантически ближайших hook-фраз через cosine similarity.

    ``liked_reels_with_embeddings`` — list of (hook_phrase, embedding_256d).
    Linear scan numpy — достаточно при <500 likes (sub-ms вычисление,
    индекс не нужен до ×10 scale).

    Fallback: если ``current_candidate_embedding`` None/пустой или в
    liked нет валидных embeddings → возвращаем пустой список.
    Caller использует legacy top-by-date.
    """
    if not current_candidate_embedding or not liked_reels_with_embeddings:
        return []
    cand_vec = np.array(current_candidate_embedding, dtype=np.float32)
    cand_norm = float(np.linalg.norm(cand_vec))
    if cand_norm < 1e-9:
        return []
    scored: list[tuple[float, str]] = []
    for hook, emb in liked_reels_with_embeddings:
        if not emb or len(emb) != len(current_candidate_embedding):
            continue
        emb_vec = np.array(emb, dtype=np.float32)
        emb_norm = float(np.linalg.norm(emb_vec))
        if emb_norm < 1e-9:
            continue
        sim = float(np.dot(cand_vec, emb_vec) / (cand_norm * emb_norm))
        scored.append((sim, hook))
    if not scored:
        return []
    scored.sort(key=lambda t: t[0], reverse=True)
    # Dedup по lowercased тексту (один и тот же hook может повторяться
    # если встречается в нескольких liked рилсах — сохраняем лучший score).
    seen: set[str] = set()
    result: list[str] = []
    for _, hook in scored:
        key = hook.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        result.append(hook)
        if len(result) >= k:
            break
    return result


def mean_embedding(embeddings: list[list[float] | None]) -> list[float] | None:
    """Усреднённый центроид из набора embeddings (None/пустые пропускаются).

    Используется для построения query-embedding в cosine retrieval —
    представляет «семантический центр» текущего Canvas'а. None если
    нет ни одного валидного embedding.
    """
    valid: list[list[float]] = [e for e in embeddings if e and len(e) > 0]
    if not valid:
        return None
    # Проверяем консистентность размерности — берём первую как референс.
    ref_dim = len(valid[0])
    matrix = np.array(
        [emb for emb in valid if len(emb) == ref_dim], dtype=np.float32
    )
    if matrix.size == 0:
        return None
    centroid = matrix.mean(axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm < 1e-9 or math.isnan(norm):
        return None
    return centroid.tolist()


async def _fetch_liked_artifacts(
    *, exclude_job_id: str | None
) -> list[tuple[str, dict[str, Any]]]:
    """Возвращает [(job_id, meta), ...] из Artifact с meta.liked='like'.

    Meta обогащается ``_embedding`` (из ``Artifact.embedding_json``) для
    переиспользования cosine-ветке без повторного запроса. Префикс
    ``_`` маркирует internal-only поле.

    Сортировка: новее первым — свежие лайки важнее для legacy адаптации.
    Лимит 500 (больше не нужно, отберём top-N anchors из них).

    Фильтр ``kind == reel_output`` выносим в SQL — лайкают только рилсы,
    остальные артефакты (transcript/proxy/log/…) в выборке бесполезны.
    Композитный индекс ``ix_artifacts_kind_created_at`` ускоряет запрос.
    """
    async with session_scope() as session:
        result = await session.execute(
            select(Artifact)
            .where(Artifact.kind == ArtifactKind.reel_output)
            .order_by(Artifact.created_at.desc())
            .limit(500)
        )
        artifacts = list(result.scalars().all())

    liked: list[tuple[str, dict[str, Any]]] = []
    for art in artifacts:
        if exclude_job_id and art.job_id == exclude_job_id:
            continue
        meta = dict(art.meta or {})
        if meta.get("liked") != "like":
            continue
        # Вкладываем embedding в meta для downstream cosine retrieval.
        # Префикс `_` подчёркивает что это internal-поле, не persistence.
        meta["_embedding"] = art.embedding_json
        liked.append((art.job_id, meta))
        if len(liked) >= 50:
            break
    return liked


def _build_hook_embedding_pairs(
    liked_entries: list[tuple[str, dict[str, Any]]],
    *,
    artifact_store: ArtifactsManager,
) -> list[tuple[str, list[float]]]:
    """Собирает (hook_phrase, embedding) пары для cosine retrieval.

    Пропускает лайки без embedding — для них нужен fallback путь.
    """
    pairs: list[tuple[str, list[float]]] = []
    for entry in liked_entries:
        _, meta = entry
        emb = meta.get("_embedding")
        if not isinstance(emb, list) or not emb:
            continue
        hook = _extract_hook_for_liked(entry, artifact_store=artifact_store)
        if not hook:
            continue
        pairs.append((hook, emb))
    return pairs


def _extract_hook_for_liked(
    entry: tuple[str, dict[str, Any]],
    *,
    artifact_store: ArtifactsManager,
) -> str | None:
    """Находит hook-текст из reel_plan.json по reel_id в meta.

    Meta reel_output обычно содержит ``reel_id`` и иногда ``hook``. Если hook
    есть прямо в meta — используем его. Иначе читаем reel_plan.json (лежит
    в job_dir/reel_plan.json) и ищем запись с соответствующим reel_id.
    """
    job_id, meta = entry

    direct_hook = meta.get("hook")
    if isinstance(direct_hook, str) and direct_hook.strip():
        return _trim_anchor(direct_hook)

    reel_id = meta.get("reel_id")
    if not reel_id:
        return None

    try:
        reel_plan_path = artifact_store.job_dir(job_id) / "reel_plan.json"
    except Exception as exc:
        log.warning(
            "preference_memory_lookup_failed",
            job=job_id,
            error=str(exc)[:200],
        )
        return None

    if not reel_plan_path.exists():
        return None

    try:
        data = json.loads(Path(reel_plan_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("preference_memory_reel_plan_read_failed", job=job_id, error=str(exc))
        return None

    for reel in data.get("reels") or []:
        if not isinstance(reel, dict):
            continue
        if reel.get("reel_id") == reel_id:
            hook = reel.get("hook")
            if isinstance(hook, str) and hook.strip():
                return _trim_anchor(hook)
            break
    return None


def _trim_anchor(text: str) -> str:
    stripped = " ".join(text.strip().split())
    if len(stripped) <= _MAX_ANCHOR_LEN:
        return stripped
    return stripped[: _MAX_ANCHOR_LEN - 1].rstrip() + "…"


__all__ = [
    "load_liked_anchors_text",
    "mean_embedding",
    "retrieve_top_k_similar",
]
