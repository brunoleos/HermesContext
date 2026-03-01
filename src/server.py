"""MCP Server para o RAG Engine.

Expõe ferramentas de busca semântica, ingestão e gestão de documentos
via Model Context Protocol, consumíveis por qualquer LLM generativa.

Roda como serviço HTTP persistente na VM Oracle Always Free.
LLMs conectam via: http://<vm-ip>:9090/mcp

100% self-hosted · custo zero · sem rate limit.
"""

from __future__ import annotations

import json
import logging
import sys
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
    """Formata resultados de busca para a LLM."""
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
        lines.append(f"### {i}. {r.get('document_title', 'Sem título')} (score: {score})")
        lines.append(f"*Doc ID: {r['document_id']} | Chunk ID: {r['chunk_id']}*\n")
        lines.append(r["chunk_text"])
        lines.append("")

    return "\n".join(lines)


# ════════════════════════════════════════════════════
# Tool Input Models (Pydantic v2)
# ════════════════════════════════════════════════════

class SearchInput(BaseModel):
    """Parâmetros de busca semântica no RAG."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(
        ...,
        description=(
            "A pergunta ou consulta em linguagem natural. "
            "Exemplos: 'Qual o procedimento para transferência de preso?', "
            "'requisitos para progressão de regime'"
        ),
        min_length=2,
        max_length=2000,
    )
    top_k: int = Field(
        default=5,
        description="Número de resultados retornados (1–20)",
        ge=1,
        le=20,
    )
    use_reranker: bool = Field(
        default=True,
        description="Aplicar cross-encoder reranking para melhorar precisão",
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Formato de saída: 'markdown' (legível) ou 'json' (estruturado)",
    )


class IngestInput(BaseModel):
    """Parâmetros para ingestão de documento."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(
        ...,
        description="Título do documento (ex: 'Resolução SAP 123/2025')",
        min_length=1,
        max_length=500,
    )
    content: str = Field(
        ...,
        description="Texto completo do documento a ser indexado",
        min_length=10,
    )
    source: Optional[str] = Field(
        default=None,
        description="Origem do documento (ex: 'SAP/SC', 'DEPEN', URL)",
        max_length=1000,
    )
    doc_type: Optional[str] = Field(
        default=None,
        description=(
            "Tipo do documento para filtragem "
            "(ex: 'resolucao', 'portaria', 'manual', 'legislacao')"
        ),
        max_length=100,
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Metadados adicionais em formato chave-valor",
    )


class ListDocumentsInput(BaseModel):
    """Parâmetros para listagem de documentos."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    limit: int = Field(
        default=20,
        description="Máximo de resultados (1–100)",
        ge=1,
        le=100,
    )
    offset: int = Field(
        default=0,
        description="Offset para paginação",
        ge=0,
    )
    doc_type: Optional[str] = Field(
        default=None,
        description="Filtrar por tipo de documento",
        max_length=100,
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Formato de saída: 'markdown' ou 'json'",
    )


class GetDocumentInput(BaseModel):
    """Parâmetros para buscar documento por ID."""

    model_config = ConfigDict(extra="forbid")

    document_id: int = Field(
        ..., description="ID numérico do documento", ge=1
    )
    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Formato de saída: 'markdown' ou 'json'",
    )


class DeleteDocumentInput(BaseModel):
    """Parâmetros para excluir documento."""

    model_config = ConfigDict(extra="forbid")

    document_id: int = Field(
        ..., description="ID numérico do documento a excluir", ge=1
    )


class StatsInput(BaseModel):
    """Parâmetros para estatísticas."""

    model_config = ConfigDict(extra="forbid")

    response_format: ResponseFormat = Field(
        default=ResponseFormat.MARKDOWN,
        description="Formato de saída: 'markdown' ou 'json'",
    )


# ════════════════════════════════════════════════════
# Tools
# ════════════════════════════════════════════════════

@mcp.tool(
    name="rag_search",
    annotations={
        "title": "Busca Semântica RAG",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def rag_search(params: SearchInput) -> str:
    """Busca documentos por similaridade semântica usando embedding + keyword hybrid search.

    Combina busca vetorial (BGE-M3 dense embeddings) com busca por palavras-chave,
    aplica Reciprocal Rank Fusion e opcionalmente reranking com cross-encoder.

    Use esta ferramenta quando precisar encontrar informações na base de
    conhecimento, responder perguntas sobre regulamentos, leis, procedimentos
    ou qualquer conteúdo previamente indexado.

    Args:
        params (SearchInput): Parâmetros de busca contendo:
            - query (str): Pergunta em linguagem natural
            - top_k (int): Número de resultados (default: 5)
            - use_reranker (bool): Usar cross-encoder (default: True)
            - response_format (str): 'markdown' ou 'json'

    Returns:
        str: Resultados formatados com trechos relevantes, scores e metadados.
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
        "title": "Ingerir Documento no RAG",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def rag_ingest_document(params: IngestInput) -> str:
    """Indexa um novo documento na base de conhecimento RAG.

    O documento será: dividido em chunks, enriquecido com contexto,
    convertido em embeddings vetoriais (BGE-M3 1024d) e armazenado
    no Oracle Autonomous DB para busca semântica.

    Use esta ferramenta para adicionar novos documentos (leis, resoluções,
    manuais, portarias) à base de conhecimento.

    Args:
        params (IngestInput): Dados do documento contendo:
            - title (str): Título do documento
            - content (str): Texto completo
            - source (str, opcional): Origem
            - doc_type (str, opcional): Tipo para filtragem
            - metadata (dict, opcional): Metadados extras

    Returns:
        str: Confirmação com ID do documento, quantidade de chunks e tempo.
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
        f"✅ Documento ingerido com sucesso.\n"
        f"- **ID**: {result['document_id']}\n"
        f"- **Título**: {result['title']}\n"
        f"- **Chunks**: {result['chunk_count']}\n"
        f"- **Tempo**: {result['elapsed_ms']}ms"
    )


@mcp.tool(
    name="rag_list_documents",
    annotations={
        "title": "Listar Documentos",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def rag_list_documents(params: ListDocumentsInput) -> str:
    """Lista documentos indexados na base de conhecimento com paginação.

    Use para ver quais documentos estão disponíveis para busca,
    filtrar por tipo, ou verificar o status da base.

    Args:
        params (ListDocumentsInput): Filtros contendo:
            - limit (int): Máximo de resultados (default: 20)
            - offset (int): Offset para paginação
            - doc_type (str, opcional): Filtro por tipo
            - response_format (str): 'markdown' ou 'json'

    Returns:
        str: Lista de documentos com ID, título, tipo e contagem de chunks.
    """
    db = _get_db()
    data = db.list_documents(
        limit=params.limit,
        offset=params.offset,
        doc_type=params.doc_type,
    )

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(data, indent=2, ensure_ascii=False)

    lines = [f"## Documentos ({data['total']} total)\n"]
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
        "title": "Obter Detalhes do Documento",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def rag_get_document(params: GetDocumentInput) -> str:
    """Obtém detalhes de um documento específico por ID.

    Retorna título, fonte, tipo, metadados e quantidade de chunks.

    Args:
        params (GetDocumentInput): Contém:
            - document_id (int): ID do documento
            - response_format (str): 'markdown' ou 'json'

    Returns:
        str: Detalhes do documento ou mensagem de erro se não encontrado.
    """
    db = _get_db()
    doc = db.get_document(params.document_id)

    if not doc:
        return f"❌ Documento com ID {params.document_id} não encontrado."

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(doc, indent=2, ensure_ascii=False)

    meta_str = ""
    if doc["metadata"]:
        meta_str = "\n".join(f"  - {k}: {v}" for k, v in doc["metadata"].items())

    return (
        f"## Documento #{doc['id']}\n"
        f"- **Título**: {doc['title']}\n"
        f"- **Fonte**: {doc['source'] or '—'}\n"
        f"- **Tipo**: {doc['doc_type'] or '—'}\n"
        f"- **Chunks**: {doc['chunk_count']}\n"
        f"- **Criado em**: {doc['created_at']}\n"
        f"{'- **Metadados**:' + chr(10) + meta_str if meta_str else ''}"
    )


@mcp.tool(
    name="rag_delete_document",
    annotations={
        "title": "Excluir Documento",
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def rag_delete_document(params: DeleteDocumentInput) -> str:
    """Exclui um documento e todos os seus chunks da base de conhecimento.

    ⚠️ Ação irreversível. Todos os chunks e embeddings associados serão removidos.

    Args:
        params (DeleteDocumentInput): Contém:
            - document_id (int): ID do documento a excluir

    Returns:
        str: Confirmação de exclusão ou erro se não encontrado.
    """
    db = _get_db()
    deleted = db.delete_document(params.document_id)

    if deleted:
        return f"✅ Documento #{params.document_id} excluído com sucesso (incluindo todos os chunks)."
    return f"❌ Documento #{params.document_id} não encontrado."


@mcp.tool(
    name="rag_get_stats",
    annotations={
        "title": "Estatísticas da Base RAG",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def rag_get_stats(params: StatsInput) -> str:
    """Retorna estatísticas gerais da base de conhecimento.

    Inclui: total de documentos, chunks, tokens e distribuição por tipo.

    Args:
        params (StatsInput): Contém:
            - response_format (str): 'markdown' ou 'json'

    Returns:
        str: Estatísticas formatadas da base RAG.
    """
    db = _get_db()
    stats = db.get_stats()

    if params.response_format == ResponseFormat.JSON:
        return json.dumps(stats, indent=2, ensure_ascii=False)

    by_type = "\n".join(
        f"  - {t}: {c} docs" for t, c in stats["by_type"].items()
    )

    return (
        f"## Estatísticas da Base RAG\n"
        f"- **Documentos**: {stats['documents']}\n"
        f"- **Chunks**: {stats['chunks']}\n"
        f"- **Tokens totais**: {stats['total_tokens']:,}\n"
        f"- **Por tipo**:\n{by_type or '  Nenhum documento.'}\n\n"
        f"*Modelo de embedding: BGE-M3 (1024d, sentence-transformers)*\n"
        f"*Reranker: ms-marco-MiniLM-L-6-v2*"
    )


# ════════════════════════════════════════════════════
# Resources (MCP resources para acesso direto)
# ════════════════════════════════════════════════════

@mcp.resource("rag://config")
async def get_rag_config() -> str:
    """Configuração atual do RAG engine."""
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
    """Inicia o MCP server como serviço HTTP persistente.

    Default: streamable_http em 0.0.0.0:9090
    Endpoint MCP: http://<vm-ip>:9090/mcp
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