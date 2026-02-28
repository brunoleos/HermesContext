#!/usr/bin/env python3
"""Ingere um documento de texto na base RAG.

Lê um arquivo .txt, .md ou .pdf, faz chunking, embedding e insere no Oracle DB.

Uso:
    python -m scripts.ingest_file documento.txt --title "LEP" --type legislacao
    python -m scripts.ingest_file pasta/ --type resolucao
"""

import sys
import os
import argparse
import glob
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database
from src.embeddings import EmbeddingService
from src.engine import RAGEngine


def read_file(path: str) -> str:
    """Lê conteúdo de texto de um arquivo."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md", ".csv", ".json"):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    elif ext == ".pdf":
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(path)
            return "\n\n".join(page.get_text() for page in doc)
        except ImportError:
            print("       ⚠️  PyMuPDF não instalado. Instale com: pip install PyMuPDF")
            sys.exit(1)
    else:
        # Tentar como texto
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


def ingest_one(engine: RAGEngine, path: str, title: str | None, doc_type: str | None) -> None:
    """Ingere um único arquivo."""
    filename = os.path.basename(path)
    doc_title = title or os.path.splitext(filename)[0]

    print(f"\n  📄 {filename}")
    print(f"     Título: {doc_title}")

    content = read_file(path)
    if not content.strip():
        print("     ⚠️  Arquivo vazio, pulando.")
        return

    print(f"     Tamanho: {len(content):,} chars, ~{len(content.split()):,} palavras")

    t0 = time.monotonic()
    result = engine.ingest_document(
        title=doc_title,
        content=content,
        source=path,
        doc_type=doc_type,
        metadata={"filename": filename, "size_chars": len(content)},
    )
    elapsed = time.monotonic() - t0

    print(f"     ✅ Doc ID: {result['document_id']}, "
          f"Chunks: {result['chunk_count']}, "
          f"Tempo: {elapsed:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingere documentos na base RAG")
    parser.add_argument("path", help="Arquivo ou diretório para ingerir")
    parser.add_argument("--title", "-t", help="Título do documento (só para arquivo único)")
    parser.add_argument("--type", "-T", dest="doc_type", help="Tipo: legislacao, resolucao, manual, portaria, etc.")
    args = parser.parse_args()

    print("=" * 60)
    print("  RAG MCP — Ingestão de Documentos")
    print("=" * 60)

    # Inicializar
    db = Database()
    db.connect()
    db.init_schema()
    emb = EmbeddingService()
    engine = RAGEngine(db=db, emb=emb)

    # Coletar arquivos
    if os.path.isdir(args.path):
        files = sorted(
            glob.glob(os.path.join(args.path, "**/*.*"), recursive=True)
        )
        files = [f for f in files if os.path.isfile(f)]
        print(f"\n  Diretório: {args.path}")
        print(f"  Arquivos encontrados: {len(files)}")
    elif os.path.isfile(args.path):
        files = [args.path]
    else:
        print(f"\n  ❌ Caminho não encontrado: {args.path}")
        sys.exit(1)

    # Ingerir
    t_total = time.monotonic()
    for f in files:
        ingest_one(engine, f, args.title if len(files) == 1 else None, args.doc_type)

    elapsed_total = time.monotonic() - t_total

    # Resumo
    stats = db.get_stats()
    db.close()

    print(f"\n{'=' * 60}")
    print(f"  ✅ Ingestão completa em {elapsed_total:.1f}s")
    print(f"  Base atual: {stats['documents']} docs, "
          f"{stats['chunks']} chunks, "
          f"{stats['total_tokens']:,} tokens")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
