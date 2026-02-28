#!/usr/bin/env python3
"""Baixa e faz warmup dos modelos de ML.

Baixa BGE-M3 (embedding) e MiniLM (reranker) para o cache local.
Executa uma inferência de warmup para validar que tudo funciona.

Uso:
    python -m scripts.warmup_models
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import settings


def main() -> None:
    print("=" * 60)
    print("  RAG MCP — Download e Warmup dos Modelos")
    print("=" * 60)

    # 1. BGE-M3 Dense Embedding
    print(f"\n[1/3] Baixando BGE-M3 ({settings.embedding_model})...")
    t0 = time.monotonic()
    from fastembed import TextEmbedding

    model = TextEmbedding(
        model_name=settings.embedding_model,
        max_length=settings.embedding_max_length,
        providers=["CPUExecutionProvider"],
    )
    elapsed = time.monotonic() - t0
    print(f"       ✅ Carregado em {elapsed:.1f}s")

    print("\n       Warmup: embedding de teste...")
    t0 = time.monotonic()
    result = list(model.embed(["Teste de embedding para warmup do modelo."]))
    elapsed = (time.monotonic() - t0) * 1000
    print(f"       ✅ Dimensão: {len(result[0])}, latência: {elapsed:.0f}ms")

    # 2. BGE-M3 Sparse (BM25-like)
    print("\n[2/3] Baixando BGE-M3 Sparse (Qdrant/bm25)...")
    t0 = time.monotonic()
    from fastembed import SparseTextEmbedding

    sparse = SparseTextEmbedding(
        model_name="Qdrant/bm25",
        providers=["CPUExecutionProvider"],
    )
    elapsed = time.monotonic() - t0
    print(f"       ✅ Carregado em {elapsed:.1f}s")

    # 3. Cross-Encoder Reranker
    print(f"\n[3/3] Baixando Reranker ({settings.reranker_model})...")
    t0 = time.monotonic()
    from sentence_transformers import CrossEncoder

    reranker = CrossEncoder(settings.reranker_model, max_length=512)
    elapsed = time.monotonic() - t0
    print(f"       ✅ Carregado em {elapsed:.1f}s")

    print("\n       Warmup: reranking de teste...")
    t0 = time.monotonic()
    scores = reranker.predict([
        ("Qual a pena para furto?", "Art. 155 - Subtrair coisa alheia móvel."),
        ("Qual a pena para furto?", "O clima hoje está ensolarado."),
    ])
    elapsed = (time.monotonic() - t0) * 1000
    print(f"       ✅ Scores: [{scores[0]:.4f}, {scores[1]:.4f}], latência: {elapsed:.0f}ms")

    # Resumo
    cache_dir = os.path.expanduser("~/.cache")
    cache_size = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, filenames in os.walk(cache_dir)
        for f in filenames
    ) / (1024 * 1024 * 1024)

    print(f"\n{'=' * 60}")
    print(f"  ✅ Todos os modelos prontos.")
    print(f"  Cache em: {cache_dir} ({cache_size:.1f} GB)")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
