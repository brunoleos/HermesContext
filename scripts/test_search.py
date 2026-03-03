#!/usr/bin/env python3
"""Test rag_search endpoint"""
from src.engine import RAGEngine
from src.database import Database
from src.embeddings import EmbeddingService

db = Database()
db.connect()
emb = EmbeddingService()
engine = RAGEngine(db=db, emb=emb)

results = engine.search(query='progressão de regime', top_k=3, use_reranker=True)
print(f'Query: {results["query"]}')
print(f'Results: {len(results["results"])}')
print(f'Total candidates: {results["total_candidates"]}')
print(f'Elapsed: {results["elapsed_ms"]}ms')
for i, r in enumerate(results['results'][:2], 1):
    print(f'{i}. {r["document_title"]} (score: {r.get("rerank_score") or r.get("rrf_score") or r.get("score")})')
