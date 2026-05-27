"""VisualEvidenceIndex — inverted keyword index над VisualEvidenceResult.

Стратегия:
* Для каждого `VisualEvidenceItem` извлекаем tokens из caption + main_object
  + person_position (опционально). Простая токенизация: lower, удаление
  stopwords, минимальная длина 3.
* Строим dict `token → list[item_idx]` для O(1) lookup.
* `score(query_tokens)` — Jaccard-подобный счёт пересечений с бонусом за
  повтор токена в индексе.

Это baseline-реализация без embeddings — работает на Russian capcap/EN captions
Moondream одинаково плохо (ключевых слов мало), но даёт непустой сигнал. В
будущем можно swap на embedding-based retrieval.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from videomaker.services.visual_evidence_agent import (
    VisualEvidenceItem,
    VisualEvidenceResult,
)

_STOPWORDS: frozenset[str] = frozenset(
    {
        "the", "with", "and", "that", "this", "there", "which", "for",
        "into", "from", "over", "under", "are", "was", "were", "has",
        "have", "can", "could", "would", "should", "about", "also",
        "his", "her", "their", "some", "any", "all", "not", "but",
        "very", "more", "less", "much", "many", "few", "each", "every",
        # RU
        "это", "как", "что", "так", "его", "ему", "она", "они", "там",
        "тут", "был", "была", "были", "есть", "один", "одно", "одна",
        "при", "для", "без", "над", "под", "про", "или", "если", "когда",
    }
)


def tokenize(text: str) -> list[str]:
    """Простая токенизация для каскадного keyword-match."""
    if not text:
        return []
    tokens: list[str] = []
    buf = ""
    for ch in text.lower():
        if ch.isalpha():
            buf += ch
        else:
            if len(buf) >= 3 and buf not in _STOPWORDS:
                tokens.append(buf)
            buf = ""
    if len(buf) >= 3 and buf not in _STOPWORDS:
        tokens.append(buf)
    return tokens


@dataclass(slots=True)
class VisualEvidenceIndex:
    """Inverted index: token → list of visual item indices + source items."""

    items: list[VisualEvidenceItem] = field(default_factory=list)
    inverted: dict[str, list[int]] = field(default_factory=dict)

    @classmethod
    def build(cls, evidence: VisualEvidenceResult) -> VisualEvidenceIndex:
        index = cls(items=list(evidence.items))
        for idx, item in enumerate(index.items):
            tokens = set()
            tokens.update(tokenize(item.caption))
            if item.main_object:
                tokens.update(tokenize(item.main_object))
            if item.has_person:
                tokens.add("person")
            if item.person_position:
                tokens.update(tokenize(item.person_position.replace("-", " ")))
            for tok in tokens:
                index.inverted.setdefault(tok, []).append(idx)
        return index

    def search(self, query_tokens: list[str], limit: int = 5) -> list[tuple[int, float]]:
        """Возвращает top-K (item_idx, score) по Jaccard-like similarity.

        Score: count_matched_tokens / (len(query_tokens) + 1). Более частые
        слова в индексе получают бонус через += 1/n (n = кол-во item'ов где слово).
        """
        if not query_tokens or not self.items:
            return []
        scores: dict[int, float] = {}
        for token in query_tokens:
            bucket = self.inverted.get(token)
            if not bucket:
                continue
            bonus = 1.0 / len(bucket) if bucket else 0.0
            for idx in bucket:
                scores[idx] = scores.get(idx, 0.0) + bonus

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return ranked[:limit]

    @property
    def is_empty(self) -> bool:
        return not self.items
