"""Serviço de embedding 100% local com BGE-M3.

Zero custo, sem rate limit, sem dependência externa.
Dense vectors (1024d) + Sparse vectors (BM25-like) nativos.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """BGE-M3 via fastembed — ONNX INT8, ~1.2 GB RAM, ~100ms/chunk no ARM."""

    def __init__(self) -> None:
        self._dense_model: Any = None
        self._sparse_model: Any = None

    # ── Lazy Loading (evita RAM até primeiro uso) ───

    @property
    def dense_model(self) -> Any:
        if self._dense_model is None:
            from fastembed import TextEmbedding

            logger.info("Carregando BGE-M3 dense (ONNX)...")
            self._dense_model = TextEmbedding(
                model_name=settings.embedding_model,
                max_length=settings.embedding_max_length,
                providers=["CPUExecutionProvider"],
            )
            logger.info("BGE-M3 dense pronto.")
        return self._dense_model

    @property
    def sparse_model(self) -> Any:
        if self._sparse_model is None:
            from fastembed import SparseTextEmbedding

            logger.info("Carregando BGE-M3 sparse...")
            self._sparse_model = SparseTextEmbedding(
                model_name="Qdrant/bm25",
                providers=["CPUExecutionProvider"],
            )
            logger.info("BGE-M3 sparse pronto.")
        return self._sparse_model

    # ── API pública ─────────────────────────────────

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Gera dense embeddings (1024d float32) para uma lista de textos."""
        embeddings = list(self.dense_model.embed(texts))
        return [e.tolist() for e in embeddings]

    def embed_query(self, query: str) -> list[float]:
        """Gera dense embedding para uma query."""
        return self.embed_texts([query])[0]

    def sparse_embed_texts(self, texts: list[str]) -> list[dict]:
        """Gera sparse embeddings (índices + valores) para keyword matching.

        Retorna lista de dicts com 'indices' e 'values'.
        """
        results = []
        for sparse_emb in self.sparse_model.embed(texts):
            results.append(
                {
                    "indices": sparse_emb.indices.tolist(),
                    "values": sparse_emb.values.tolist(),
                }
            )
        return results

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Similaridade cosseno entre dois vetores."""
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        dot = np.dot(va, vb)
        norm = np.linalg.norm(va) * np.linalg.norm(vb)
        if norm == 0:
            return 0.0
        return float(dot / norm)
