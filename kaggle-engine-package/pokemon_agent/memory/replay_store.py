"""Phase 1 of v5 (docs/v5-architecture.md §3.1) — Replay Vector Store.

Stores `(features, label, meta)` records from real games: `features` is
`featurize.featurize_observation()`'s output at one real decision point,
`label` is that decision's eventual real outcome (1.0 = the featurized
player won, 0.0 = lost, 0.5 = draw), `meta` is free-form (game id, whether
search was enabled, etc.).

Honesty about scale, stated in the v5 doc and repeated here: this is a
brute-force numpy nearest-neighbor index, not FAISS/annoy. At the data
volumes this project actually has (hundreds to low thousands of records —
see docs/v5-architecture.md for the real count), brute-force cosine
similarity over a numpy array is exact and fast enough; a real ANN library
would be a scaling upgrade for a dataset size this project doesn't have yet,
not a correctness requirement today. Swap in one later if `len(store)` ever
makes `query_similar()` a measured bottleneck -- nothing here would need to
change shape to do that, only the internals of `query_similar()`.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class ReplayRecord:
    features: list[float]
    label: float  # 1.0 win / 0.0 loss / 0.5 draw, from the featurized player's perspective
    meta: dict = field(default_factory=dict)


class ReplayVectorStore:
    def __init__(self):
        self._records: list[ReplayRecord] = []
        self._matrix: Optional[np.ndarray] = None  # lazily (re)built cache for query_similar

    def log_decision(self, features: list[float], label: float, meta: Optional[dict] = None) -> None:
        self._records.append(ReplayRecord(features=list(features), label=float(label), meta=dict(meta or {})))
        self._matrix = None  # invalidate the cached matrix

    def __len__(self) -> int:
        return len(self._records)

    @property
    def records(self) -> list[ReplayRecord]:
        return self._records

    def _ensure_matrix(self) -> np.ndarray:
        if self._matrix is None or len(self._matrix) != len(self._records):
            self._matrix = np.array([r.features for r in self._records], dtype=float)
        return self._matrix

    def query_similar(self, features: list[float], k: int = 5) -> list[tuple[ReplayRecord, float]]:
        """Return up to `k` (record, cosine_similarity) pairs, most similar
        first. Brute-force -- see module docstring for why that's the
        honest, correct choice at this project's real data scale."""
        if not self._records:
            return []
        matrix = self._ensure_matrix()
        query = np.array(features, dtype=float)
        query_norm = np.linalg.norm(query)
        matrix_norms = np.linalg.norm(matrix, axis=1)
        denom = matrix_norms * query_norm
        denom[denom == 0] = 1e-12
        sims = (matrix @ query) / denom
        top_idx = np.argsort(-sims)[:k]
        return [(self._records[i], float(sims[i])) for i in top_idx]

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            for r in self._records:
                f.write(json.dumps({"features": r.features, "label": r.label, "meta": r.meta}) + "\n")

    @classmethod
    def load(cls, path: str) -> "ReplayVectorStore":
        store = cls()
        if not os.path.exists(path):
            return store
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                store.log_decision(rec["features"], rec["label"], rec.get("meta"))
        return store

    def append_to_file(self, path: str, record: ReplayRecord) -> None:
        """Append one record directly to disk (used by the self-play data
        generator so a long run's progress survives even if it's interrupted
        partway through -- the in-memory store alone would lose everything)."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a") as f:
            f.write(json.dumps({"features": record.features, "label": record.label, "meta": record.meta}) + "\n")
