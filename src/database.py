"""Cliente Oracle Autonomous AI Database.

Gerencia pool de conexões, CRUD de documentos/chunks,
e hybrid search (vector + keyword).
"""

from __future__ import annotations

import array
import json
import logging
from contextlib import contextmanager
from typing import Any, Generator

import oracledb

from .config import settings

logger = logging.getLogger(__name__)

# ── Schema SQL ──────────────────────────────────────

SCHEMA_DDL = [
    """
    CREATE TABLE IF NOT EXISTS documents (
        id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        title           VARCHAR2(500)  NOT NULL,
        source          VARCHAR2(1000),
        doc_type        VARCHAR2(100),
        metadata        CLOB CHECK (metadata IS JSON),
        created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
        updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        document_id     NUMBER         NOT NULL
                        REFERENCES documents(id) ON DELETE CASCADE,
        chunk_index     NUMBER         NOT NULL,
        chunk_text      VARCHAR2(4000) NOT NULL,
        enriched_text   VARCHAR2(4000),
        token_count     NUMBER,
        embedding       VECTOR(1024, FLOAT32),
        created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
        CONSTRAINT uq_doc_chunk UNIQUE (document_id, chunk_index)
    )
    """,
]

INDEX_DDL = [
    """
    CREATE VECTOR INDEX IF NOT EXISTS idx_chunk_emb ON chunks(embedding)
        ORGANIZATION NEIGHBOR PARTITIONS
        WITH DISTANCE COSINE
        WITH TARGET ACCURACY 95
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_chunk_doc ON chunks(document_id)
    """,
]


class Database:
    """Pool de conexões Oracle com operações RAG."""

    def __init__(self) -> None:
        self._pool: oracledb.ConnectionPool | None = None

    # ── Lifecycle ───────────────────────────────────

    def connect(self) -> None:
        """Cria connection pool com Oracle Wallet (mTLS) — modo thin (sem Oracle Client)."""
        if self._pool is not None:
            return

        self._pool = oracledb.create_pool(
            user=settings.oracle_user,
            password=settings.oracle_password,
            dsn=settings.oracle_dsn,
            config_dir=settings.oracle_wallet_dir,
            wallet_location=settings.oracle_wallet_dir,
            wallet_password=settings.oracle_password,
            min=2,
            max=8,
            increment=1,
        )
        logger.info("Oracle connection pool criado (thin mode, %d-%d conns)", 2, 8)

    def close(self) -> None:
        if self._pool:
            self._pool.close(force=True)
            self._pool = None

    @contextmanager
    def get_conn(self) -> Generator[oracledb.Connection, None, None]:
        """Obtém conexão do pool com auto-commit."""
        assert self._pool is not None, "Database não conectado. Chame connect()."
        conn = self._pool.acquire()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.release(conn)

    def init_schema(self) -> None:
        """Cria tabelas e índices se não existirem."""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            for ddl in SCHEMA_DDL + INDEX_DDL:
                try:
                    cursor.execute(ddl)
                except oracledb.DatabaseError as e:
                    err = e.args[0]
                    # ORA-00955 = name already exists — ignorar
                    if hasattr(err, "code") and err.code == 955:
                        continue
                    raise
        logger.info("Schema inicializado.")

    # ── Documents CRUD ──────────────────────────────

    def insert_document(
        self,
        title: str,
        source: str | None = None,
        doc_type: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        """Insere documento e retorna o ID gerado."""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            doc_id_var = cursor.var(oracledb.NUMBER)
            cursor.execute(
                """
                INSERT INTO documents (title, source, doc_type, metadata)
                VALUES (:title, :source, :doc_type, :metadata)
                RETURNING id INTO :doc_id
                """,
                {
                    "title": title,
                    "source": source,
                    "doc_type": doc_type,
                    "metadata": json.dumps(metadata or {}),
                    "doc_id": doc_id_var,
                },
            )
            return int(doc_id_var.getvalue()[0])

    def delete_document(self, doc_id: int) -> bool:
        """Deleta documento e seus chunks (CASCADE)."""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM documents WHERE id = :id", {"id": doc_id})
            return cursor.rowcount > 0

    def get_document(self, doc_id: int) -> dict | None:
        """Busca documento por ID."""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, title, source, doc_type, metadata,
                       TO_CHAR(created_at, 'YYYY-MM-DD HH24:MI:SS') as created_at,
                       (SELECT COUNT(*) FROM chunks WHERE document_id = d.id) as chunk_count
                FROM documents d WHERE id = :id
                """,
                {"id": doc_id},
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "title": row[1],
                "source": row[2],
                "doc_type": row[3],
                "metadata": json.loads(row[4]) if row[4] else {},
                "created_at": row[5],
                "chunk_count": row[6],
            }

    def list_documents(
        self, limit: int = 20, offset: int = 0, doc_type: str | None = None
    ) -> dict:
        """Lista documentos com paginação."""
        with self.get_conn() as conn:
            cursor = conn.cursor()

            where = ""
            params: dict[str, Any] = {"limit": limit, "offset": offset}
            if doc_type:
                where = "WHERE doc_type = :doc_type"
                params["doc_type"] = doc_type

            cursor.execute(f"SELECT COUNT(*) FROM documents {where}", params)
            total = cursor.fetchone()[0]

            cursor.execute(
                f"""
                SELECT d.id, d.title, d.source, d.doc_type,
                       TO_CHAR(d.created_at, 'YYYY-MM-DD HH24:MI:SS'),
                       (SELECT COUNT(*) FROM chunks WHERE document_id = d.id)
                FROM documents d {where}
                ORDER BY d.created_at DESC
                OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
                """,
                params,
            )

            items = [
                {
                    "id": r[0],
                    "title": r[1],
                    "source": r[2],
                    "doc_type": r[3],
                    "created_at": r[4],
                    "chunk_count": r[5],
                }
                for r in cursor.fetchall()
            ]

            return {
                "items": items,
                "total": total,
                "offset": offset,
                "has_more": total > offset + len(items),
            }

    # ── Helpers ────────────────────────────────────

    @staticmethod
    def _to_vector(embedding: list[float]) -> array.array:
        """Converte list[float] para array.array('f') — formato aceito pelo oracledb thin mode para VECTOR."""
        return array.array("f", embedding)

    # ── Chunks ──────────────────────────────────────

    def insert_chunks(
        self,
        document_id: int,
        chunks: list[dict],
    ) -> int:
        """Insere chunks com embeddings um a um.

        Cada dict em chunks deve ter:
          chunk_text, enriched_text, chunk_index, token_count, embedding
        """
        with self.get_conn() as conn:
            cursor = conn.cursor()
            sql = """
                INSERT INTO chunks
                    (document_id, chunk_index, chunk_text,
                     enriched_text, token_count, embedding)
                VALUES
                    (:document_id, :chunk_index, :chunk_text,
                     :enriched_text, :token_count, :embedding)
            """
            for c in chunks:
                cursor.execute(
                    sql,
                    {
                        "document_id": document_id,
                        "chunk_index": c["chunk_index"],
                        "chunk_text": c["chunk_text"],
                        "enriched_text": c.get("enriched_text"),
                        "token_count": c.get("token_count"),
                        "embedding": self._to_vector(c["embedding"]),
                    },
                )
            return len(chunks)

    # ── Vector Search ───────────────────────────────

    def vector_search(
        self, query_embedding: list[float], top_k: int = 20
    ) -> list[dict]:
        """Busca por similaridade vetorial (HNSW cosine)."""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT c.id, c.chunk_text, c.enriched_text,
                       c.document_id, d.title,
                       VECTOR_DISTANCE(c.embedding, :qvec, COSINE) AS distance
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                ORDER BY VECTOR_DISTANCE(c.embedding, :qvec2, COSINE)
                FETCH APPROXIMATE FIRST :topk ROWS ONLY
                    WITH TARGET ACCURACY 95
                """,
                {
                    "qvec": self._to_vector(query_embedding),
                    "qvec2": self._to_vector(query_embedding),
                    "topk": top_k,
                },
            )
            return [
                {
                    "chunk_id": r[0],
                    "chunk_text": r[1],
                    "enriched_text": r[2],
                    "document_id": r[3],
                    "document_title": r[4],
                    "distance": r[5],
                    "score": 1.0 - r[5],  # cosine similarity
                }
                for r in cursor.fetchall()
            ]

    def keyword_search(self, query: str, top_k: int = 20) -> list[dict]:
        """Busca por keyword (Oracle Text full-text search)."""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            # Escape básico para Oracle Text query
            safe_query = query.replace("'", "''")
            cursor.execute(
                f"""
                SELECT c.id, c.chunk_text, c.enriched_text,
                       c.document_id, d.title,
                       SCORE(1) AS text_score
                FROM chunks c
                JOIN documents d ON c.document_id = d.id
                WHERE CONTAINS(c.chunk_text, '{safe_query}', 1) > 0
                ORDER BY SCORE(1) DESC
                FETCH FIRST :topk ROWS ONLY
                """,
                {"topk": top_k},
            )
            return [
                {
                    "chunk_id": r[0],
                    "chunk_text": r[1],
                    "enriched_text": r[2],
                    "document_id": r[3],
                    "document_title": r[4],
                    "score": r[5],
                }
                for r in cursor.fetchall()
            ]

    # ── Stats ───────────────────────────────────────

    def get_stats(self) -> dict:
        """Estatísticas gerais do banco."""
        with self.get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM documents")
            doc_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM chunks")
            chunk_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT NVL(SUM(token_count), 0) FROM chunks"
            )
            total_tokens = cursor.fetchone()[0]
            cursor.execute(
                """
                SELECT doc_type, COUNT(*)
                FROM documents
                GROUP BY doc_type
                ORDER BY COUNT(*) DESC
                """
            )
            by_type = {r[0] or "unknown": r[1] for r in cursor.fetchall()}
            return {
                "documents": doc_count,
                "chunks": chunk_count,
                "total_tokens": total_tokens,
                "by_type": by_type,
            }