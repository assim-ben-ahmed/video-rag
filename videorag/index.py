"""The searchable index of one video: speech chunks and on-screen descriptions, each with its time span.

Search is hybrid: dense embeddings (cosine) and BM25 keyword scores, merged with reciprocal rank fusion. Exact
numbers and names ("38 kg", "Buckfast") are often found by BM25 when embeddings blur them.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import numpy as np

from .timeutil import fmt_span

Embedder = Callable[[list[str]], np.ndarray]


@dataclass
class Doc:
    id: str
    kind: str  # "speech" | "screen"
    start: float
    end: float
    text: str
    frame: str | None = None  # keyframe file name, for "screen" docs

    def evidence(self) -> str:
        label = "speech" if self.kind == "speech" else "on screen"
        return f"{fmt_span(self.start, self.end)} ({label}) {self.text}"


def tokenize(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+(?:[.,][0-9]+)?", text)


class BM25:
    def __init__(self, corpus: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(d) for d in corpus]
        self.lens = np.array([len(d) for d in corpus], dtype=np.float32)
        self.avg = float(self.lens.mean()) if len(corpus) else 0.0
        df: Counter = Counter()
        for d in corpus:
            df.update(set(d))
        n = len(corpus)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(len(self.docs), dtype=np.float32)
        for i, tf in enumerate(self.docs):
            norm = self.k1 * (1 - self.b + self.b * self.lens[i] / (self.avg or 1))
            for t in query:
                if t in tf:
                    out[i] += self.idf[t] * tf[t] * (self.k1 + 1) / (tf[t] + norm)
        return out


def rrf(rankings: Iterable[list[int]], k: int = 60) -> dict[int, float]:
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return fused


class VideoIndex:
    def __init__(self, docs: list[Doc], vectors: np.ndarray):
        self.docs = docs
        self.vectors = vectors
        self._bm25 = BM25([tokenize(d.text) for d in docs])

    @classmethod
    def build(cls, docs: list[Doc], embed: Embedder) -> "VideoIndex":
        vectors = embed([d.text for d in docs]) if docs else np.zeros((0, 1), dtype=np.float32)
        return cls(docs, vectors)

    def search(self, query: str, embed: Embedder, k: int = 5, kinds: tuple[str, ...] = ("speech", "screen")) -> list[Doc]:
        allowed = [i for i, d in enumerate(self.docs) if d.kind in kinds]
        if not allowed:
            return []
        qv = embed([query])[0]
        dense = self.vectors[allowed] @ qv
        sparse = self._bm25.scores(tokenize(query))[allowed]
        dense_rank = [allowed[i] for i in np.argsort(-dense)]
        sparse_rank = [allowed[i] for i in np.argsort(-sparse) if sparse[i] > 0]
        fused = rrf([dense_rank, sparse_rank])
        best = sorted(fused, key=fused.get, reverse=True)[:k]
        return [self.docs[i] for i in best]

    # ── persistence ─────────────────────────────────────────────────────────

    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "docs.json").write_text(json.dumps([asdict(d) for d in self.docs], indent=1), encoding="utf-8")
        np.save(folder / "vectors.npy", self.vectors)

    @classmethod
    def load(cls, folder: Path) -> "VideoIndex":
        docs = [Doc(**d) for d in json.loads((folder / "docs.json").read_text(encoding="utf-8"))]
        return cls(docs, np.load(folder / "vectors.npy"))
