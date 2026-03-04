"""MCP Server for RAG Engine.

Exposes semantic search, document ingestion, and management tools
via Model Context Protocol, consumable by any generative LLM.

Runs as a persistent HTTP service on Oracle Always Free VM.
LLMs connect via: http://<vm-ip>:9090/mcp

100% self-hosted · zero cost · no rate limit.
"""

from __future__ import annotations

import asyncio
import glob
import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .config import settings
from .database import Database
from .embeddings import EmbeddingService
from .engine import RAGEngine
from .utils import read_file_from_disk as _read_file_from_disk

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("hermes_mcp")


# ════════════════════════════════════════════════════
# Lifespan: inicializa DB, modelos e engine uma vez
# ════════════════════════════════════════════════════

# Globais — inicializados no lifespan, usados pelos tools
_db: Database | None = None
_engine: RAGEngine | None = None


@asynccontextmanager
async def app_lifespan(app: Any) -> Any:
    """Inicializa recursos compartilhados por todos os tools."""
    global _db, _engine

    logger.info("Inicializando RAG MCP Server...")

    _db = Database()
    _db.connect()
    _db.init_schema()

    emb = EmbeddingService()
    _engine = RAGEngine(db=_db, emb=emb)

    # Pré-carregar modelos (evita latência na primeira chamada)
    logger.info("Pré-carregando modelos de embedding...")
    _ = emb.embed_query("warmup")
    logger.info("Modelos prontos.")

    yield {}

    _db.close()
    _db = None
    _engine = None
    logger.info("RAG MCP Server encerrado.")


mcp = FastMCP(
    "hermes_mcp",
    lifespan=app_lifespan,
)


# ════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════

class ResponseFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"


def _get_engine() -> RAGEngine:
    assert _engine is not None, "Server não inicializado"
    return _engine


def _get_db() -> Database:
    assert _db is not None, "Server não inicializado"
    return _db


def _format_search_results(results: dict, fmt: ResponseFormat) -> str:
    """Formats search results for the LLM."""
    if fmt == ResponseFormat.JSON:
        return json.dumps(results, indent=2, ensure_ascii=False)

    # Markdown
    lines = [f"## Resultados para: \"{results['query']}\""]
    lines.append(
        f"*{len(results['results'])} resultados de {results['total_candidates']}"
        f" candidatos em {results['elapsed_ms']}ms"
        f"{' (cache)' if results.get('cached') else ''}*\n"
    )

    for i, r in enumerate(results["results"], 1):
        score = r.get("rerank_score") or r.get("rrf_score") or r.get("score", 0)
        lines.append(f"### {i}. {r.get('document_title', 'No title')} (score: {score})")
        lines.append(f"*Doc ID: {r['document_id']} | Chunk ID: {r['chunk_id']}*\n")
        lines.append(r["chunk_text"])
        lines.append("")

    return "\n".join(lines)


# ════════════════════════════════════════════════════
# Tools
# ════════════════════════════════════════════════════

@mcp.tool(
    name="rag_search",
    annotations={
        "title": "RAG Semantic Search",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def rag_search(
    query: str = Field(
        ...,
        description="Natural language query or question. Examples: 'What is the procedure for prisoner transfer?', 'requirements for regime progression'",
    ),
    top_k: int = Field(
        default=5,
        description="Number of results to return (1-20)",
        ge=1,
        le=20,
    ),
    use_reranker: bool = Field(
        default=True,
        description="Apply cross-encoder reranking to improve precision",
    ),
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (readable) or 'json' (structured)",
    ),
) -> str:
    """Search documents by semantic similarity using embedding + keyword hybrid search.

    Combines vector search (BGE-M3 dense embeddings) with keyword search,
    applies Reciprocal Rank Fusion and optional cross-encoder reranking.

    Use this tool when you need to find information in the knowledge base,
    answer questions about regulations, laws, procedures, or any
    previously indexed content.

    Returns:
        str: Formatted results with relevant excerpts, scores and metadata.
    """
    engine = _get_engine()

    results = engine.search(
        query=query,
        top_k=top_k,
        use_reranker=use_reranker,
    )

    return _format_search_results(results, response_format)


@mcp.tool(
    name="rag_ingest_document",
    annotations={
        "title": "Ingest Document into RAG",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def rag_ingest_document(
    title: str = Field(
        ...,
        description="Document title (e.g., 'Resolution SAP 123/2025')",
        min_length=1,
        max_length=500,
    ),
    content: str = Field(
        ...,
        description="Full text of the document to be indexed",
        min_length=10,
    ),
    source: Optional[str] = Field(
        default=None,
        description="Document source (e.g., 'SAP/SC', 'DEPEN', URL)",
        max_length=1000,
    ),
    doc_type: Optional[str] = Field(
        default=None,
        description="Document type for filtering (e.g., 'resolution', 'ordinance', 'manual', 'legislation')",
        max_length=100,
    ),
    metadata: Optional[str] = Field(
        default=None,
        description="Additional metadata as JSON string with key-value pairs",
    ),
) -> str:
    """Index a new document in the RAG knowledge base.

    The document will be: chunked, enriched with context,
    converted to vector embeddings (BGE-M3 1024d) and stored
    in Oracle Autonomous DB for semantic search.

    Use this tool to add new documents (laws, resolutions,
    manuals, ordinances) to the knowledge base.

    Returns:
        str: Confirmation with document ID, chunk count and time.
    """
    engine = _get_engine()

    meta_dict = None
    if metadata:
        try:
            meta_dict = json.loads(metadata)
        except json.JSONDecodeError:
            return "❌ Error: metadata must be a valid JSON string"

    result = engine.ingest_document(
        title=title,
        content=content,
        source=source,
        doc_type=doc_type,
        metadata=meta_dict,
    )

    return (
        f"✅ Document ingested successfully.\n"
        f"- **ID**: {result['document_id']}\n"
        f"- **Title**: {result['title']}\n"
        f"- **Chunks**: {result['chunk_count']}\n"
        f"- **Time**: {result['elapsed_ms']}ms"
    )


@mcp.tool(
    name="rag_ingest_file",
    annotations={
        "title": "Ingest File (PDF, TXT, etc)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def rag_ingest_file(
    path: str = Field(
        ...,
        description="Path to file or directory in /data/ (e.g., '/data/doc.pdf' or '/data/')",
        min_length=1,
    ),
    title: Optional[str] = Field(
        default=None,
        description="Document title (default: filename). Ignored if path is a directory.",
        max_length=500,
    ),
    doc_type: Optional[str] = Field(
        default=None,
        description="Document type for filtering (e.g., 'resolution', 'ordinance', 'manual', 'legislation')",
        max_length=100,
    ),
    metadata: Optional[str] = Field(
        default=None,
        description="Additional metadata as JSON string with key-value pairs",
    ),
) -> str:
    """Ingests an existing file on the VM (in /data/) into the RAG knowledge base.

    Supports individual files (.txt, .md, .csv, .json, .pdf) or entire directories.
    For directories, all files will be processed recursively.

    Use this tool after transferring files to the VM via SCP or mounting.
    The file must be in /data/ (volume mounted in the container).

    Returns:
        str: Summary of ingestion (N documents, total chunks, time)
    """
    # Validation: path must be in /data/
    path = path.rstrip("/")
    if not path.startswith("/data"):
        return f"❌ Security error: path must be in /data/, received: {path}"

    # Parse metadata JSON if provided
    meta_dict = None
    if metadata:
        try:
            meta_dict = json.loads(metadata)
        except json.JSONDecodeError:
            return "❌ Error: metadata must be a valid JSON string"

    db = _get_db()
    job_id = str(uuid.uuid4())

    if not os.path.exists(path):
        return f"❌ Path does not exist or is not accessible: {path}"

    db.create_ingest_job(job_id=job_id, file_path=path)
    asyncio.create_task(
        _process_ingest_job(
            job_id=job_id,
            path=path,
            title=title,
            doc_type=doc_type,
            meta_dict=meta_dict,
        )
    )

    return (
        f"⏳ Ingest iniciado em background.\n"
        f"- **job_id**: `{job_id}`\n"
        f"- **Arquivo**: {path}\n\n"
        f"Use `rag_get_ingest_status` com o job_id para acompanhar o progresso."
    )


async def _process_ingest_job(
    job_id: str,
    path: str,
    title: str | None,
    doc_type: str | None,
    meta_dict: dict | None,
) -> None:
    """Background task: processa ingest e atualiza status no Oracle."""
    db = _get_db()
    engine = _get_engine()

    db.update_ingest_job(job_id=job_id, status="PROCESSING", progress=10)

    def _ingest_file(file_path: str, file_title: str, content: str, file_metadata: dict) -> dict:
        """Helper to ingest a single file (runs in executor)."""
        return engine.ingest_document(
            title=file_title,
            content=content,
            source=file_path,
            doc_type=doc_type,
            metadata=file_metadata,
        )

    try:
        if os.path.isfile(path):
            content = _read_file_from_disk(path)
            if not content.strip():
                db.update_ingest_job(
                    job_id=job_id,
                    status="FAILED",
                    progress=0,
                    error_message="Arquivo vazio.",
                )
                return

            file_title = title or os.path.splitext(os.path.basename(path))[0]
            file_metadata = dict(meta_dict) if meta_dict else {}
            file_metadata["filename"] = os.path.basename(path)
            file_metadata["size_chars"] = len(content)

            result = await asyncio.to_thread(
                _ingest_file,
                path,
                file_title,
                content,
                file_metadata,
            )
            db.update_ingest_job(
                job_id=job_id,
                status="COMPLETED",
                progress=100,
                document_id=result["document_id"],
                total_chunks=result["chunk_count"],
            )

        elif os.path.isdir(path):
            files = sorted(glob.glob(os.path.join(path, "**/*.*"), recursive=True))
            files = [f for f in files if os.path.isfile(f)]

            if not files:
                db.update_ingest_job(
                    job_id=job_id,
                    status="FAILED",
                    progress=0,
                    error_message="Nenhum arquivo encontrado no diretório.",
                )
                return

            total_chunks = 0
            errors = []

            for i, file_path in enumerate(files):
                try:
                    content = _read_file_from_disk(file_path)
                    if not content.strip():
                        continue

                    file_title = os.path.splitext(os.path.basename(file_path))[0]
                    file_metadata = dict(meta_dict) if meta_dict else {}
                    file_metadata["filename"] = os.path.basename(file_path)
                    file_metadata["size_chars"] = len(content)

                    result = await asyncio.to_thread(
                        _ingest_file,
                        file_path,
                        file_title,
                        content,
                        file_metadata,
                    )
                    total_chunks += result["chunk_count"]
                except Exception as e:
                    errors.append(f"{os.path.basename(file_path)}: {e}")

                progress = int(10 + 90 * (i + 1) / len(files))
                db.update_ingest_job(job_id=job_id, status="PROCESSING", progress=progress)

            error_msg = "; ".join(errors) if errors else None
            db.update_ingest_job(
                job_id=job_id,
                status="COMPLETED",
                progress=100,
                total_chunks=total_chunks,
                error_message=error_msg,
            )

    except Exception as e:
        logger.exception("Erro no job de ingest %s", job_id)
        db.update_ingest_job(
            job_id=job_id,
            status="FAILED",
            progress=0,
            error_message=str(e),
        )


@mcp.tool(
    name="rag_get_ingest_status",
    annotations={
        "title": "Get Ingest Job Status",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def rag_get_ingest_status(
    job_id: str = Field(
        ...,
        description="Job ID returned by rag_ingest_file",
    ),
) -> str:
    """Verifica o status e progresso de um job de ingest assíncrono.

    Returns:
        str: Status atual (PENDING, PROCESSING, COMPLETED, FAILED), progresso %,
             document_id e chunk_count quando concluído, ou mensagem de erro.
    """
    db = _get_db()
    job = db.get_ingest_job(job_id)

    if not job:
        return f"❌ Job não encontrado: `{job_id}`"

    status = job["status"]
    progress = job["progress"] or 0
    icon = {"PENDING": "⏳", "PROCESSING": "🔄", "COMPLETED": "✅", "FAILED": "❌"}.get(status, "❓")

    lines = [
        f"{icon} **Status**: {status} ({progress}%)",
        f"- **job_id**: `{job['job_id']}`",
        f"- **Arquivo**: {job['file_path']}",
        f"- **Iniciado em**: {job['created_at']}",
        f"- **Atualizado em**: {job['updated_at']}",
    ]

    if job["document_id"] is not None:
        lines.append(f"- **document_id**: {job['document_id']}")
    if job["total_chunks"] is not None:
        lines.append(f"- **Chunks**: {job['total_chunks']}")
    if job["error_message"]:
        lines.append(f"- **Erro**: {job['error_message']}")

    return "\n".join(lines)


@mcp.tool(
    name="rag_list_documents",
    annotations={
        "title": "List Documents",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def rag_list_documents(
    limit: int = Field(
        default=20,
        description="Maximum number of results (1-100)",
        ge=1,
        le=100,
    ),
    offset: int = Field(
        default=0,
        description="Offset for pagination",
        ge=0,
    ),
    doc_type: Optional[str] = Field(
        default=None,
        description="Filter by document type",
        max_length=100,
    ),
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    ),
) -> str:
    """Lists indexed documents in the knowledge base with pagination.

    Use to see which documents are available for searching,
    filter by type, or check the base status.

    Returns:
        str: List of documents with ID, title, type and chunk count.
    """
    db = _get_db()
    data = db.list_documents(
        limit=limit,
        offset=offset,
        doc_type=doc_type,
    )

    if response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2, ensure_ascii=False)

    lines = [f"## Documents ({data['total']} total)\n"]
    for doc in data["items"]:
        lines.append(
            f"- **[{doc['id']}]** {doc['title']} "
            f"({doc['doc_type'] or '—'}, {doc['chunk_count']} chunks, "
            f"{doc['created_at']})"
        )

    if data["has_more"]:
        next_off = offset + limit
        lines.append(f"\n*More results available (offset={next_off}).*")

    return "\n".join(lines)


@mcp.tool(
    name="rag_get_document",
    annotations={
        "title": "Get Document Details",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def rag_get_document(
    document_id: int = Field(
        ...,
        description="Numeric document ID",
        ge=1,
    ),
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    ),
) -> str:
    """Gets details of a specific document by ID.

    Returns title, source, type, metadata and chunk count.

    Returns:
        str: Document details or error message if not found.
    """
    db = _get_db()
    doc = db.get_document(document_id)

    if not doc:
        return f"❌ Document with ID {document_id} not found."

    if response_format == ResponseFormat.JSON:
        return json.dumps(doc, indent=2, ensure_ascii=False)

    meta_str = ""
    if doc["metadata"]:
        meta_str = "\n".join(f"  - {k}: {v}" for k, v in doc["metadata"].items())

    return (
        f"## Document #{doc['id']}\n"
        f"- **Title**: {doc['title']}\n"
        f"- **Source**: {doc['source'] or '—'}\n"
        f"- **Type**: {doc['doc_type'] or '—'}\n"
        f"- **Chunks**: {doc['chunk_count']}\n"
        f"- **Created at**: {doc['created_at']}\n"
        f"{'- **Metadata**:' + chr(10) + meta_str if meta_str else ''}"
    )


@mcp.tool(
    name="rag_delete_document",
    annotations={
        "title": "Delete Document",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def rag_delete_document(
    document_id: int = Field(
        ...,
        description="Numeric ID of the document to delete",
        ge=1,
    ),
) -> str:
    """Deletes a document and all its chunks from the knowledge base.

    ⚠️ Irreversible action. All associated chunks and embeddings will be removed.

    Returns:
        str: Deletion confirmation or error if not found.
    """
    db = _get_db()
    deleted = db.delete_document(document_id)

    if deleted:
        return f"✅ Document #{document_id} deleted successfully (including all chunks)."
    return f"❌ Document #{document_id} not found."


@mcp.tool(
    name="rag_get_stats",
    annotations={
        "title": "RAG Base Statistics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def rag_get_stats(
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    ),
) -> str:
    """Returns general statistics about the knowledge base.

    Includes: total documents, chunks, tokens and distribution by type.

    Returns:
        str: Formatted statistics of the RAG base.
    """
    db = _get_db()
    stats = db.get_stats()

    if response_format == ResponseFormat.JSON:
        return json.dumps(stats, indent=2, ensure_ascii=False)

    by_type = "\n".join(
        f"  - {t}: {c} docs" for t, c in stats["by_type"].items()
    )

    return (
        f"## RAG Base Statistics\n"
        f"- **Documents**: {stats['documents']}\n"
        f"- **Chunks**: {stats['chunks']}\n"
        f"- **Total tokens**: {stats['total_tokens']:,}\n"
        f"- **By type**:\n{by_type or '  No documents.'}\n\n"
        f"*Embedding model: BGE-M3 (1024d, sentence-transformers)*\n"
        f"*Reranker: ms-marco-MiniLM-L-6-v2*"
    )


# ════════════════════════════════════════════════════
# Resources (MCP resources para acesso direto)
# ════════════════════════════════════════════════════

@mcp.resource("rag://config")
async def get_rag_config() -> str:
    """Current RAG engine configuration."""
    config = {
        "embedding_model": settings.embedding_model,
        "embedding_dim": settings.embedding_dim,
        "reranker_model": settings.reranker_model,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "retrieval_top_k": settings.retrieval_top_k,
        "rerank_top_k": settings.rerank_top_k,
        "vector_weight": settings.vector_weight,
        "keyword_weight": settings.keyword_weight,
        "cache_ttl_seconds": settings.cache_ttl_seconds,
    }
    return json.dumps(config, indent=2)


# ════════════════════════════════════════════════════
# Entrypoint
# ════════════════════════════════════════════════════

def main() -> None:
    """Starts the MCP server as a persistent HTTP service.

    Default: streamable_http at 0.0.0.0:9090
    MCP Endpoint: http://<vm-ip>:9090/mcp
    """
    transport = settings.mcp_transport
    port = settings.mcp_port
    host = settings.mcp_host

    logger.info(
        "Iniciando RAG MCP Server — transport=%s, host=%s, port=%d",
        transport, host, port,
    )

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # Tentar obter ASGI app e rodar com uvicorn (controle total de host/port)
        import uvicorn

        app = None
        for method_name in ("streamable_http_app", "sse_app", "http_app"):
            method = getattr(mcp, method_name, None)
            if method is not None:
                app = method()
                logger.info("Usando %s()", method_name)
                break

        if app is not None:
            uvicorn.run(app, host=host, port=port)
        else:
            # Fallback: mcp.run() sem host (ouve em 127.0.0.1)
            logger.warning(
                "Nenhum método *_app() encontrado no FastMCP. "
                "Usando mcp.run() — pode não ouvir em 0.0.0.0"
            )
            mcp.run(transport="streamable_http", port=port)


if __name__ == "__main__":
    main()