"""MCP Server for RAG Engine.

Exposes semantic search, document ingestion, and management tools
via Model Context Protocol, consumable by any generative LLM.

Runs as a persistent HTTP service on Oracle Always Free VM.
LLMs connect via: http://<vm-ip>:9090/mcp

100% self-hosted · zero cost · no rate limit.
"""

from __future__ import annotations

import glob
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from enum import Enum
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import settings
from .database import Database
from .embeddings import EmbeddingService
from .engine import RAGEngine

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


def _read_file_from_disk(path: str) -> str:
    """Reads file content (txt, md, csv, json, pdf).

    Args:
        path: File path (must be in /data/)

    Returns:
        str: File content

    Raises:
        ValueError: If file doesn't exist or format not supported
    """
    if not os.path.isfile(path):
        raise ValueError(f"File not found: {path}")

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
            raise ValueError("PyMuPDF not installed. Install with: pip install PyMuPDF")
    else:
        # Try as generic text
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            raise ValueError(f"Error reading file {path}: {e}")


# ════════════════════════════════════════════════════
# Tool Input Models (Pydantic v2)
# ════════════════════════════════════════════════════

class SearchInput(BaseModel):
    """Semantic search parameters in the RAG."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        ...,
        description=(
            "Natural language query or question. "
            "Examples: 'What is the procedure for prisoner transfer?', "
            "'requirements for regime progression'"
        ),
        min_length=2,
        max_length=2000,
    )
    top_k: int = Field(
        default=5,
        description="Number of results to return (1-20)",
        ge=1,
        le=20,
    )
    use_reranker: bool = Field(
        default=True,
        description="Apply cross-encoder reranking to improve precision",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' (readable) or 'json' (structured)",
    )


class IngestInput(BaseModel):
    """Parameters for document ingestion."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(
        ...,
        description="Document title (e.g., 'Resolution SAP 123/2025')",
        min_length=1,
        max_length=500,
    )
    content: str = Field(
        ...,
        description="Full text of the document to be indexed",
        min_length=10,
    )
    source: Optional[str] = Field(
        default=None,
        description="Document source (e.g., 'SAP/SC', 'DEPEN', URL)",
        max_length=1000,
    )
    doc_type: Optional[str] = Field(
        default=None,
        description=(
            "Document type for filtering "
            "(e.g., 'resolution', 'ordinance', 'manual', 'legislation')"
        ),
        max_length=100,
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional metadata as key-value pairs",
    )


class IngestFileInput(BaseModel):
    """Parameters for file ingestion already on the VM."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    path: str = Field(
        ...,
        description="Path to file or directory in /data/ (e.g., '/data/doc.pdf' or '/data/')",
        min_length=1,
    )
    title: Optional[str] = Field(
        default=None,
        description="Document title (default: filename). Ignored if path is a directory.",
        max_length=500,
    )
    doc_type: Optional[str] = Field(
        default=None,
        description=(
            "Document type for filtering "
            "(e.g., 'resolution', 'ordinance', 'manual', 'legislation')"
        ),
        max_length=100,
    )


class ListDocumentsInput(BaseModel):
    """Parameters for document listing."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    limit: int = Field(
        default=20,
        description="Maximum number of results (1-100)",
        ge=1,
        le=100,
    )
    offset: int = Field(
        default=0,
        description="Offset for pagination",
        ge=0,
    )
    doc_type: Optional[str] = Field(
        default=None,
        description="Filter by document type",
        max_length=100,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    )


class GetDocumentInput(BaseModel):
    """Parameters to fetch document by ID."""

    model_config = ConfigDict(extra="forbid")

    document_id: int = Field(
        ..., description="Numeric document ID", ge=1
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    )


class DeleteDocumentInput(BaseModel):
    """Parameters to delete a document."""

    model_config = ConfigDict(extra="forbid")

    document_id: int = Field(
        ..., description="Numeric ID of the document to delete", ge=1
    )


class StatsInput(BaseModel):
    """Parameters for statistics."""

    model_config = ConfigDict(extra="forbid")

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Output format: 'markdown' or 'json'",
    )


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
async def rag_search(params: SearchInput) -> str:
    """Search documents by semantic similarity using embedding + keyword hybrid search.

    Combines vector search (BGE-M3 dense embeddings) with keyword search,
    applies Reciprocal Rank Fusion and optional cross-encoder reranking.

    Use this tool when you need to find information in the knowledge base,
    answer questions about regulations, laws, procedures, or any
    previously indexed content.

    Args:
        params (SearchInput): Search parameters containing:
            - query (str): Natural language question
            - top_k (int): Number of results (default: 5)
            - use_reranker (bool): Use cross-encoder (default: True)
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Formatted results with relevant excerpts, scores and metadata.
    """
    engine = _get_engine()

    results = engine.search(
        query=params.query,
        top_k=params.top_k,
        use_reranker=params.use_reranker,
    )

    return _format_search_results(results, params.response_format)


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
async def rag_ingest_document(params: IngestInput) -> str:
    """Index a new document in the RAG knowledge base.

    The document will be: chunked, enriched with context,
    converted to vector embeddings (BGE-M3 1024d) and stored
    in Oracle Autonomous DB for semantic search.

    Use this tool to add new documents (laws, resolutions,
    manuals, ordinances) to the knowledge base.

    Args:
        params (IngestInput): Document data containing:
            - title (str): Document title
            - content (str): Full text
            - source (str, optional): Source
            - doc_type (str, optional): Type for filtering
            - metadata (dict, optional): Extra metadata

    Returns:
        str: Confirmation with document ID, chunk count and time.
    """
    engine = _get_engine()

    result = engine.ingest_document(
        title=params.title,
        content=params.content,
        source=params.source,
        doc_type=params.doc_type,
        metadata=params.metadata,
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
async def rag_ingest_file(params: IngestFileInput) -> str:
    """Ingests an existing file on the VM (in /data/) into the RAG knowledge base.

    Supports individual files (.txt, .md, .csv, .json, .pdf) or entire directories.
    For directories, all files will be processed recursively.

    Use this tool after transferring files to the VM via SCP or mounting.
    The file must be in /data/ (volume mounted in the container).

    Args:
        params (IngestFileInput): Containing:
            - path (str): Path in /data/ (e.g., /data/document.pdf or /data/)
            - title (str, optional): Document title (default: filename)
            - doc_type (str, optional): Type for filtering

    Returns:
        str: Summary of ingestion (N documents, total chunks, time)
    """
    # Validation: path must be in /data/
    path = params.path.rstrip("/")
    if not path.startswith("/data"):
        return f"❌ Security error: path must be in /data/, received: {path}"

    engine = _get_engine()
    t_start = time.time()

    # If file
    if os.path.isfile(path):
        try:
            content = _read_file_from_disk(path)
            if not content.strip():
                return f"❌ Empty file: {path}"

            title = params.title or os.path.splitext(os.path.basename(path))[0]
            result = engine.ingest_document(
                title=title,
                content=content,
                source=path,
                doc_type=params.doc_type,
                metadata={"filename": os.path.basename(path), "size_chars": len(content)},
            )
            elapsed = time.time() - t_start
            return (
                f"✅ Arquivo ingerido com sucesso.\n"
                f"- **Arquivo**: {os.path.basename(path)}\n"
                f"- **ID**: {result['document_id']}\n"
                f"- **Chunks**: {result['chunk_count']}\n"
                f"- **Tempo**: {elapsed:.1f}s"
            )
        except Exception as e:
            return f"❌ Error ingesting file: {e}"

    # If directory
    elif os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "**/*.*"), recursive=True))
        files = [f for f in files if os.path.isfile(f)]

        if not files:
            return f"❌ No files found in: {path}"

        total_docs = 0
        total_chunks = 0
        results_lines = [f"📁 Directory ingestion: {path}\n"]

        for file_path in files:
            try:
                content = _read_file_from_disk(file_path)
                if not content.strip():
                    continue

                title = os.path.splitext(os.path.basename(file_path))[0]
                result = engine.ingest_document(
                    title=title,
                    content=content,
                    source=file_path,
                    doc_type=params.doc_type,
                    metadata={"filename": os.path.basename(file_path), "size_chars": len(content)},
                )
                total_docs += 1
                total_chunks += result["chunk_count"]
                results_lines.append(f"  ✅ {os.path.basename(file_path)} (ID: {result['document_id']}, chunks: {result['chunk_count']})")
            except Exception as e:
                results_lines.append(f"  ⚠️ {os.path.basename(file_path)}: {e}")

        elapsed = time.time() - t_start
        results_lines.append(f"\n**Summary**: {total_docs} documents, {total_chunks} chunks, {elapsed:.1f}s")
        return "\n".join(results_lines)

    else:
        return f"❌ Path does not exist or is not accessible: {path}"


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
async def rag_list_documents(params: ListDocumentsInput) -> str:
    """Lists indexed documents in the knowledge base with pagination.

    Use to see which documents are available for searching,
    filter by type, or check the base status.

    Args:
        params (ListDocumentsInput): Filters containing:
            - limit (int): Maximum results (default: 20)
            - offset (int): Offset for pagination
            - doc_type (str, optional): Filter by type
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: List of documents with ID, title, type and chunk count.
    """
    db = _get_db()
    data = db.list_documents(
        limit=params.limit,
        offset=params.offset,
        doc_type=params.doc_type,
    )

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2, ensure_ascii=False)

    lines = [f"## Documents ({data['total']} total)\n"]
    for doc in data["items"]:
        lines.append(
            f"- **[{doc['id']}]** {doc['title']} "
            f"({doc['doc_type'] or '—'}, {doc['chunk_count']} chunks, "
            f"{doc['created_at']})"
        )

    if data["has_more"]:
        next_off = params.offset + params.limit
        lines.append(f"\n*Mais resultados disponíveis (offset={next_off}).*")

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
async def rag_get_document(params: GetDocumentInput) -> str:
    """Gets details of a specific document by ID.

    Returns title, source, type, metadata and chunk count.

    Args:
        params (GetDocumentInput): Contains:
            - document_id (int): Document ID
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Document details or error message if not found.
    """
    db = _get_db()
    doc = db.get_document(params.document_id)

    if not doc:
        return f"❌ Document with ID {params.document_id} not found."

    if params.response_format == ResponseFormat.JSON:
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
async def rag_delete_document(params: DeleteDocumentInput) -> str:
    """Deletes a document and all its chunks from the knowledge base.

    ⚠️ Irreversible action. All associated chunks and embeddings will be removed.

    Args:
        params (DeleteDocumentInput): Contains:
            - document_id (int): ID of the document to delete

    Returns:
        str: Deletion confirmation or error if not found.
    """
    db = _get_db()
    deleted = db.delete_document(params.document_id)

    if deleted:
        return f"✅ Document #{params.document_id} deleted successfully (including all chunks)."
    return f"❌ Document #{params.document_id} not found."


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
async def rag_get_stats(params: StatsInput) -> str:
    """Returns general statistics about the knowledge base.

    Includes: total documents, chunks, tokens and distribution by type.

    Args:
        params (StatsInput): Contains:
            - response_format (str): 'markdown' or 'json'

    Returns:
        str: Formatted statistics of the RAG base.
    """
    db = _get_db()
    stats = db.get_stats()

    if params.response_format == ResponseFormat.JSON:
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