#!/usr/bin/env python3
"""Testa conectividade com o Oracle Autonomous DB.

Verifica: wallet, credenciais, versão do DB e suporte a VECTOR.

Uso:
    python -m scripts.test_connection
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import oracledb
from src.config import settings


def main() -> None:
    print("=" * 60)
    print("  RAG MCP — Teste de Conexão Oracle")
    print("=" * 60)

    print(f"\n  DSN:    {settings.oracle_dsn}")
    print(f"  User:   {settings.oracle_user}")
    print(f"  Wallet: {settings.oracle_wallet_dir}")

    # 1. Verificar wallet
    print("\n[1/4] Verificando wallet...")
    wallet_files = ["cwallet.sso", "tnsnames.ora", "sqlnet.ora"]
    for f in wallet_files:
        path = os.path.join(settings.oracle_wallet_dir, f)
        if os.path.exists(path):
            print(f"       ✅ {f}")
        else:
            print(f"       ❌ {f} NÃO ENCONTRADO em {settings.oracle_wallet_dir}")
            print(f"       Baixe o wallet no Console Oracle > Autonomous DB > DB Connection")
            sys.exit(1)

    # 2. Conectar
    print("\n[2/4] Conectando (thin mode, sem Oracle Client)...")
    try:
        conn = oracledb.connect(
            user=settings.oracle_user,
            password=settings.oracle_password,
            dsn=settings.oracle_dsn,
            config_dir=settings.oracle_wallet_dir,
            wallet_location=settings.oracle_wallet_dir,
            wallet_password=settings.oracle_password,
        )
        print("       ✅ Conexão OK")
    except oracledb.DatabaseError as e:
        print(f"       ❌ Falha: {e}")
        sys.exit(1)

    # 3. Versão do DB
    print("\n[3/4] Versão do banco...")
    cursor = conn.cursor()
    cursor.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
    row = cursor.fetchone()
    if row:
        print(f"       {row[0]}")

    # 4. Suporte a VECTOR
    print("\n[4/4] Testando suporte a VECTOR...")
    try:
        cursor.execute("""
            SELECT VECTOR_DISTANCE(
                VECTOR('[1.0, 0.0, 0.0]', 3, FLOAT32),
                VECTOR('[0.0, 1.0, 0.0]', 3, FLOAT32),
                COSINE
            ) FROM DUAL
        """)
        dist = cursor.fetchone()[0]
        print(f"       ✅ VECTOR suportado (distância teste: {dist:.4f})")
    except oracledb.DatabaseError as e:
        print(f"       ❌ VECTOR não suportado: {e}")
        print("       O Autonomous DB precisa ser versão 23ai ou superior.")
        sys.exit(1)

    conn.close()
    print("\n✅ Todos os testes passaram.\n")


if __name__ == "__main__":
    main()