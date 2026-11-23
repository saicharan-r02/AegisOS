"""Pure-Python Okapi BM25 index with subtoken splitting for code search."""

from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


def tokenize_code(text: str) -> list[str]:
    """Tokenize source code splitting identifiers, camelCase, and punctuation."""
    raw_tokens = re.findall(r"[A-Za-z0-9_]+", text)
    tokens: list[str] = []
    for token in raw_tokens:
        lower = token.lower()
        tokens.append(lower)
        if "_" in token:
            for part in token.split("_"):
                if part:
                    tokens.append(part.lower())
        subwords = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+", token)
        if len(subwords) > 1:
            for sub in subwords:
                tokens.append(sub.lower())
    return [t for t in tokens if len(t) > 1]


class BM25Index:
    """Okapi BM25 retrieval index for codebases."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.doc_lengths: dict[str, int] = {}
        self.avg_doc_len: float = 0.0
        self.doc_count: int = 0
        self.term_doc_frequencies: dict[str, int] = {}
        self.doc_term_frequencies: dict[str, Counter[str]] = {}

    def add_documents(self, documents: dict[str, str]) -> None:
        """Index a mapping of doc_id -> text content."""
        self.doc_lengths.clear()
        self.doc_term_frequencies.clear()
        self.term_doc_frequencies.clear()

        total_length = 0
        for doc_id, text in documents.items():
            tokens = tokenize_code(text)
            length = len(tokens)
            self.doc_lengths[doc_id] = length
            total_length += length
            counts = Counter(tokens)
            self.doc_term_frequencies[doc_id] = counts
            for term in counts:
                self.term_doc_frequencies[term] = self.term_doc_frequencies.get(term, 0) + 1

        self.doc_count = len(documents)
        self.avg_doc_len = (total_length / self.doc_count) if self.doc_count > 0 else 0.0

    def query(self, query_text: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Return top_k matching doc_ids sorted by BM25 score descending."""
        if not self.doc_count:
            return []

        query_tokens = tokenize_code(query_text)
        if not query_tokens:
            return []

        scores: dict[str, float] = defaultdict(float)

        for term in query_tokens:
            df = self.term_doc_frequencies.get(term, 0)
            if df == 0:
                continue
            # Standard Lucene/BM25 IDF
            idf = math.log(1.0 + (self.doc_count - df + 0.5) / (df + 0.5))

            for doc_id, term_counts in self.doc_term_frequencies.items():
                tf = term_counts.get(term, 0)
                if tf == 0:
                    continue
                doc_len = self.doc_lengths[doc_id]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (
                    1.0 - self.b + self.b * (doc_len / (self.avg_doc_len or 1.0))
                )
                score = idf * (numerator / denominator)
                scores[doc_id] += score

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        return ranked[:top_k]

    def save_cache(self, path: Path) -> None:
        """Save index metadata to json."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "k1": self.k1,
            "b": self.b,
            "doc_lengths": self.doc_lengths,
            "avg_doc_len": self.avg_doc_len,
            "doc_count": self.doc_count,
            "term_doc_frequencies": self.term_doc_frequencies,
            "doc_term_frequencies": {k: dict(v) for k, v in self.doc_term_frequencies.items()},
        }
        path.write_text(json.dumps(data), encoding="utf-8")

    @classmethod
    def load_cache(cls, path: Path) -> BM25Index | None:
        """Load index from cached json file."""
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            idx = cls(k1=data.get("k1", 1.5), b=data.get("b", 0.75))
            idx.doc_lengths = data["doc_lengths"]
            idx.avg_doc_len = data["avg_doc_len"]
            idx.doc_count = data["doc_count"]
            idx.term_doc_frequencies = data["term_doc_frequencies"]
            idx.doc_term_frequencies = {
                k: Counter(v) for k, v in data["doc_term_frequencies"].items()
            }
            return idx
        except Exception:
            return None
