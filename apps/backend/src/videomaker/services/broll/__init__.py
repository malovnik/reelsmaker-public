"""B-roll retrieval layer — semantic search over VisualEvidenceResult.

Архитектура:
* `VisualEvidenceIndex` — in-memory inverted index по tokens из caption
  + detected tags VisualEvidenceItem. Простой keyword-based retrieval как
  первая итерация, без embeddings.
* `find_broll_for_segment()` — matches segment text → top-K visual observations.
* `suggest_broll_inserts()` — для каждого development segment арки находит
  до N B-roll кандидатов и форматирует как BRollSuggestion (overlay на 2-3s).

Предпосылки:
* Работает только при vision_enabled (VisualEvidenceResult должен быть пополнен).
* Не модифицирует arc — только возвращает suggestions. Применение — отдельный
  рендер-шаг (пока не реализован; это интеграция будущего спринта).
"""

from videomaker.services.broll.index import VisualEvidenceIndex
from videomaker.services.broll.inserter import BRollSuggestion, suggest_broll_inserts
from videomaker.services.broll.retriever import BRollCandidate, find_broll_for_segment

__all__ = [
    "BRollCandidate",
    "BRollSuggestion",
    "VisualEvidenceIndex",
    "find_broll_for_segment",
    "suggest_broll_inserts",
]
