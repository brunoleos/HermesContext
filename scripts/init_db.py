#!/usr/bin/env python3
"""Inicializa o schema no Oracle Autonomous DB.

Cria tabelas (documents, chunks), índices vetoriais (HNSW) e Oracle Text.
Seguro para rodar múltiplas vezes (idempotente).

Uso:
    python -m scripts.init_db
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import Database


def main() -> None:
    print("=" * 60)
    print("  RAG MCP — Inicialização do Oracle Autonomous DB")
    print("=" * 60)

    db = Database()

    print("\n[1/3] Conectando ao Oracle Autonomous DB...")
    db.connect()
    print("       ✅ Conexão estabelecida.")

    print("\n[2/3] Criando schema (tabelas + índices)...")
    db.init_schema()
    print("       ✅ Schema criado/verificado.")

    print("\n[3/3] Verificando estatísticas...")
    stats = db.get_stats()
    print(f"       Documentos: {stats['documents']}")
    print(f"       Chunks:     {stats['chunks']}")
    print(f"       Tokens:     {stats['total_tokens']}")

    db.close()
    print("\n✅ Banco inicializado com sucesso.\n")


if __name__ == "__main__":
    main()
