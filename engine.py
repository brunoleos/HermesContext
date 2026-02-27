"""RAG Engine — orquestra chunking, hybrid retrieval, reranking e cache.

Totalmente self-hosted. Sem APIs externas, sem rate limits.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any

import numpy as np
import redis

from .config import settings
from .database import Database
from .embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class RAGEngine:
    """Motor RAG completo: ingest, retrieve, rerank."""

    def __init__(self, db: Database, emb: EmbeddingService) -> None:
        self.db = db
        self.emb = emb
        self._reranker: Any = None
        self._redis: redis.Redis | None = None

    # ── Lazy resources ──────────────────────────────

    @property
    def reranker(self) -> Any:
        if self._reranker is None:
            from sentence_transformers import CrossEncoder

            logger.info("Carregando reranker %s...", settings.reranker_model)
            self._reranker = CrossEncoder(
                settings.reranker_model,
                max_length=512,
            )
            logger.info("Reranker pronto.")
        return self._reranker

    @property
    def cache(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(
                settings.redis_url, decode_responses=True
            )
        return self._redis

    # ── Chunking ────────────────────────────────────

    @staticmethod
    def _split_text(
        text: str,
        chunk_size: int = settings.chunk_size,
        overlap: int = settings.chunk_overlap,
        separators: tuple[str, ...] = settings.chunk_separators,
    ) -> list[str]:
        """Recursive character text splitter com sobreposição."""
        chunks: list[str] = []
        if len(text.split()) <= chunk_size:
            return [text.strip()] if text.strip() else []

        # Tenta dividir pelo separador mais forte disponível
        for sep in separators:
            parts = text.split(sep)
            if len(parts) > 1:
                break
        else:
            # Fallback: divide por palavras
            words = text.split()
            parts = []
            for i in range(0, len(words), chunk_size - overlap):
                parts.append(" ".join(words[i : i + chunk_size]))
            return [p.strip() for p in parts if p.strip()]

        current: list[str] = []
        current_len = 0

        for part in parts:
            part_len = len(part.split())
            if current_len + part_len > chunk_size and current:
                chunk_text = sep.join(current).strip()
                if chunk_text:
                    chunks.append(chunk_text)
                # Overlap: manter últimos N tokens
                overlap_parts: list[str] = []
                overlap_len = 0
                for p in reversed(current):
                    plen = len(p.split())
                    if overlap_len + plen > overlap:
                        break
                    overlap_parts.insert(0, p)
                    overlap_len += plen
                current = overlap_parts
                current_len = overlap_len

            current.append(part)
            current_len += part_len

        if current:
            chunk_text = sep.join(current).strip()
            if chunk_text:
                chunks.append(chunk_text)

        return chunks

    @staticmethod
    def _enrich_chunk(
        chunk_text: str,
        doc_title: str,
        chunk_index: int,
        doc_type: str | None = None,
    ) -> str:
        """Enrichment contextual: prefixo hierárquico para melhorar retrieval."""
        prefix_parts = [f"Documento: {doc_title}"]
        if doc_type:
            prefix_parts.append(f"Tipo: {doc_type}")
        prefix_parts.append(f"Trecho {chunk_index + 1}")
        prefix = " | ".join(prefix_parts)
        return f"[{prefix}] {chunk_text}"

    # ── Ingestão ────────────────────────────────────

    def ingest_document(
        self,
        title: str,
        content: str,
        source: str | None = None,
        doc_type: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Pipeline completo: parse → chunk → embed → store.

        Returns dict com doc_id, chunk_count, tempo de processamento.
        """
        t0 = time.monotonic()

        # 1. Inserir documento
        doc_id = self.db.insert_document(
            title=title, source=source, doc_type=doc_type, metadata=metadata
        )

        # 2. Chunking
        raw_chunks = self._split_text(content)
        if not raw_chunks:
            return {
                "document_id": doc_id,
                "title": title,
                "chunk_count": 0,
                "elapsed_ms": int((time.monotonic() - t0) * 1000),
            }

        # 3. Enrichment
        enriched = [
            self._enrich_chunk(c, title, i, doc_type)
            for i, c in enumerate(raw_chunks)
        ]

        # 4. Embedding (local, sem rate limit)
        embeddings = self.emb.embed_texts(enriched)

        # 5. Montar chunks para inserção
        chunk_records = []
        for i, (raw, enr, emb_vec) in enumerate(
            zip(raw_chunks, enriched, embeddings)
        ):
            chunk_records.append(
                {
                    "chunk_index": i,
                    "chunk_text": raw[:4000],
                    "enriched_text": enr[:4000],
                    "token_count": len(raw.split()),
                    "embedding": emb_vec,
                }
            )

        # 6. Inserir no Oracle
        inserted = self.db.insert_chunks(doc_id, chunk_records)

        elapsed = int((time.monotonic() - t0) * 1000)
        logger.info(
            "Ingestão completa: doc=%d, chunks=%d, %dms", doc_id, inserted, elapsed
        )
        return {
            "document_id": doc_id,
            "title": title,
            "chunk_count": inserted,
            "elapsed_ms": elapsed,
        }

    # ── Semantic Cache ──────────────────────────────

    def _cache_key(self, query: str) -> str:
        return f"rag:cache:{hashlib.sha256(query.encode()).hexdigest()[:16]}"

    def _check_cache(self, query: str) -> dict | None:
        """Verifica cache semântico."""
        try:
            key = self._cache_key(query)
            cached = self.cache.get(key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass
        return None

    def _set_cache(self, query: str, result: dict) -> None:
        """Armazena resultado no cache."""
        try:
            key = self._cache_key(query)
            self.cache.setex(
                key,
                settings.cache_ttl_seconds,
                json.dumps(result, ensure_ascii=False),
            )
        except Exception:
            pass

    # ── Hybrid Retrieval + Reranking ────────────────

    def _reciprocal_rank_fusion(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        k: int = settings.rrf_k,
    ) -> list[dict]:
        """Combina vector + keyword search via RRF."""
        scores: dict[int, float] = {}
        chunk_map: dict[int, dict] = {}

        for rank, r in enumerate(vector_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + settings.vector_weight / (
                k + rank + 1
            )
            chunk_map[cid] = r

        for rank, r in enumerate(keyword_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + settings.keyword_weight / (
                k + rank + 1
            )
            if cid not in chunk_map:
                chunk_map[cid] = r

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for cid, rrf_score in ranked:
            item = chunk_map[cid].copy()
            item["rrf_score"] = round(rrf_score, 6)
            results.append(item)

        return results

    def _rerank(
        self, query: str, candidates: list[dict], top_k: int
    ) -> list[dict]:
        """Cross-encoder reranking local (ms-marco-MiniLM, ~90MB)."""
        if not candidates:
            return []

        pairs = [
            (query, c.get("enriched_text") or c["chunk_text"])
            for c in candidates
        ]
        scores = self.reranker.predict(pairs)

        for c, s in zip(candidates, scores):
            c["rerank_score"] = round(float(s), 4)

        candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        return candidates[:top_k]

    def search(
        self,
        query: str,
        top_k: int = settings.rerank_top_k,
        use_cache: bool = True,
        use_reranker: bool = True,
    ) -> dict:
        """Pipeline completo de busca:
        1. Cache check
        2. Embed query
        3. Vector search (top 20)
        4. Keyword search (top 20)
        5. RRF fusion
        6. Cross-encoder reranking → top K

        Returns:
            {
                "query": str,
                "results": [{chunk_text, document_title, score, ...}],
                "total_candidates": int,
                "elapsed_ms": int,
                "cached": bool,
            }
        """
        t0 = time.monotonic()

        # 1. Cache check
        if use_cache:
            cached = self._check_cache(query)
            if cached:
                cached["cached"] = True
                return cached

        # 2. Embed query
        query_vec = self.emb.embed_query(query)

        # 3. Vector search
        vector_results = self.db.vector_search(
            query_vec, top_k=settings.retrieval_top_k
        )

        # 4. Keyword search
        keyword_results = self.db.keyword_search(
            query, top_k=settings.retrieval_top_k
        )

        # 5. RRF
        fused = self._reciprocal_rank_fusion(vector_results, keyword_results)
        total_candidates = len(fused)

        # 6. Reranking
        if use_reranker and fused:
            results = self._rerank(query, fused[: settings.retrieval_top_k], top_k)
        else:
            results = fused[:top_k]

        elapsed = int((time.monotonic() - t0) * 1000)

        response = {
            "query": query,
            "results": results,
            "total_candidates": total_candidates,
            "elapsed_ms": elapsed,
            "cached": False,
        }

        # Cache result
        if use_cache and results:
            self._set_cache(query, response)

        return response
