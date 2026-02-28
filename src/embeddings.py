"""Serviço de embedding 100% local com BGE-M3.

Zero custo, sem rate limit, sem dependência externa.
Usa sentence-transformers (PyTorch) que suporta BGE-M3 nativamente.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from .config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """BGE-M3 via sentence-transformers — ~1.5 GB RAM, ~100-200ms/chunk no ARM."""

    def __init__(self) -> None:
        self._model: Any = None

    @property
    def model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Carregando %s...", settings.embedding_model)
            self._model = SentenceTransformer(
                settings.embedding_model,
                device="cpu",
            )
            self._model.max_seq_length = settings.embedding_max_length
            logger.info(
                "Modelo pronto — dim=%d, max_seq=%d",
                self._model.get_sentence_embedding_dimension(),
                self._model.max_seq_length,
            )
        return self._model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Gera dense embeddings para uma lista de textos."""
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
            batch_size=32,
        )
        return embeddings.tolist()

    def embed_query(self, query: str) -> list[float]:
        """Gera dense embedding para uma query."""
        return self.embed_texts([query])[0]

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Similaridade cosseno entre dois vetores."""
        va = np.array(a, dtype=np.float32)
        vb = np.array(b, dtype=np.float32)
        dot = np.dot(va, vb)
        norm = np.linalg.norm(va) * np.linalg.norm(vb)
        if norm == 0:
            return 0.0
        return float(dot / norm)
