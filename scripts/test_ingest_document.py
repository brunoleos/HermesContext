#!/usr/bin/env python3
"""Test rag_ingest_document endpoint"""
import time
from src.engine import RAGEngine
from src.database import Database
from src.embeddings import EmbeddingService

db = Database()
db.connect()
emb = EmbeddingService()
engine = RAGEngine(db=db, emb=emb)

t0 = time.monotonic()
result = engine.ingest_document(
    title='Smoke Test - Artigo 112 LEP',
    content='Art. 112. A pena privativa de liberdade será executada, conforme a natureza do delito, em regime aberto ou semi-aberto. A progressão de regime é direito do condenado, desde que cumpla requisitos objetivos e subjectivos.',
    source='Teste Smoke',
    doc_type='test'
)
elapsed = (time.monotonic() - t0) * 1000

print(f'Document ID: {result["document_id"]}')
print(f'Chunks: {result["chunk_count"]}')
print(f'Time: {result["elapsed_ms"]}ms')
