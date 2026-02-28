#!/usr/bin/env python3
"""Smoke test: valida o pipeline RAG completo end-to-end.

Insere um documento de teste, faz busca semântica, verifica resultados,
e limpa os dados de teste. Não deixa resíduos no banco.

Uso:
    python -m scripts.smoke_test
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database
from src.embeddings import EmbeddingService
from src.engine import RAGEngine

TEST_DOC = """
Lei de Execução Penal - LEP (Lei nº 7.210/1984)

Art. 112. A pena privativa de liberdade será executada em forma progressiva com
a transferência para regime menos rigoroso, a ser determinada pelo juiz, quando o
preso tiver cumprido ao menos:

I - 16% da pena, se o apenado for primário e o crime tiver sido cometido sem
violência à pessoa ou grave ameaça;

II - 20% da pena, se o apenado for reincidente em crime cometido sem violência
à pessoa ou grave ameaça;

III - 25% da pena, se o apenado for primário e o crime tiver sido cometido com
violência à pessoa ou grave ameaça;

IV - 30% da pena, se o apenado for reincidente em crime cometido com violência
à pessoa ou grave ameaça;

Art. 113. O ingresso do condenado em regime aberto supõe a aceitação de seu
programa e das condições impostas pelo juiz.

Art. 114. Somente poderá ingressar no regime aberto o condenado que:
I - estiver trabalhando ou comprovar a possibilidade de fazê-lo imediatamente;
II - apresentar, pelos seus antecedentes ou pelo resultado dos exames a que foi
submetido, fundados indícios de que irá ajustar-se, com autodisciplina e senso
de responsabilidade, ao novo regime.
"""


def main() -> None:
    print("=" * 60)
    print("  RAG MCP — Smoke Test (pipeline completo)")
    print("=" * 60)

    db = Database()
    db.connect()
    db.init_schema()
    emb = EmbeddingService()
    engine = RAGEngine(db=db, emb=emb)

    doc_id = None

    try:
        # 1. Ingestão
        print("\n[1/5] Ingestão de documento de teste...")
        t0 = time.monotonic()
        result = engine.ingest_document(
            title="LEP - Lei de Execução Penal (TESTE)",
            content=TEST_DOC,
            source="smoke_test",
            doc_type="legislacao_teste",
        )
        elapsed = (time.monotonic() - t0) * 1000
        doc_id = result["document_id"]
        print(f"       ✅ Doc ID: {doc_id}, Chunks: {result['chunk_count']}, {elapsed:.0f}ms")

        if result["chunk_count"] == 0:
            print("       ❌ FALHA: nenhum chunk gerado!")
            sys.exit(1)

        # 2. Embedding
        print("\n[2/5] Teste de embedding...")
        t0 = time.monotonic()
        vec = emb.embed_query("progressão de regime")
        elapsed = (time.monotonic() - t0) * 1000
        print(f"       ✅ Dimensão: {len(vec)}, latência: {elapsed:.0f}ms")

        if len(vec) != 1024:
            print(f"       ❌ FALHA: dimensão esperada 1024, obteve {len(vec)}")
            sys.exit(1)

        # 3. Vector search
        print("\n[3/5] Vector search...")
        t0 = time.monotonic()
        vec_results = db.vector_search(vec, top_k=5)
        elapsed = (time.monotonic() - t0) * 1000
        print(f"       ✅ {len(vec_results)} resultados, {elapsed:.0f}ms")

        if not vec_results:
            print("       ❌ FALHA: nenhum resultado do vector search!")
            sys.exit(1)

        # 4. Busca híbrida completa (com reranking)
        print("\n[4/5] Busca híbrida + reranking...")
        t0 = time.monotonic()
        search_result = engine.search(
            query="Quais são os requisitos para progressão de regime?",
            top_k=3,
            use_cache=False,
            use_reranker=True,
        )
        elapsed = (time.monotonic() - t0) * 1000
        print(f"       ✅ {len(search_result['results'])} resultados de "
              f"{search_result['total_candidates']} candidatos, {elapsed:.0f}ms")

        if not search_result["results"]:
            print("       ❌ FALHA: busca não retornou resultados!")
            sys.exit(1)

        # Verificar relevância
        top = search_result["results"][0]
        print(f"       Top resultado: score={top.get('rerank_score', 'N/A')}")
        print(f"       Preview: {top['chunk_text'][:100]}...")

        if "progressão" not in top["chunk_text"].lower() and "regime" not in top["chunk_text"].lower():
            print("       ⚠️  AVISO: resultado pode não ser relevante")

        # 5. Stats
        print("\n[5/5] Estatísticas...")
        stats = db.get_stats()
        print(f"       Documentos: {stats['documents']}")
        print(f"       Chunks: {stats['chunks']}")

    finally:
        # Cleanup
        if doc_id is not None:
            print(f"\n  🧹 Limpando documento de teste (ID: {doc_id})...")
            db.delete_document(doc_id)
            print("       ✅ Documento de teste removido.")

        db.close()

    print(f"\n{'=' * 60}")
    print("  ✅ SMOKE TEST PASSOU — pipeline RAG funcionando!")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
