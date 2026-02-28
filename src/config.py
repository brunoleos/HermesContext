"""Configuração centralizada via variáveis de ambiente."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    # ── Oracle Autonomous DB ────────────────────────
    oracle_dsn: str = field(default_factory=lambda: os.getenv("ORACLE_DSN", ""))
    oracle_user: str = field(default_factory=lambda: os.getenv("ORACLE_USER", "ADMIN"))
    oracle_password: str = field(default_factory=lambda: os.getenv("ORACLE_PASSWORD", ""))
    oracle_wallet_dir: str = field(default_factory=lambda: os.getenv("ORACLE_WALLET_DIR", "/wallet"))

    # ── Redis ───────────────────────────────────────
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379"))

    # ── Modelos (self-hosted, custo zero) ───────────
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    )
    embedding_dim: int = 1024
    embedding_max_length: int = 512

    reranker_model: str = field(
        default_factory=lambda: os.getenv(
            "RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )
    )

    # ── Chunking ────────────────────────────────────
    chunk_size: int = 512          # tokens
    chunk_overlap: int = 64        # tokens (~12%)
    chunk_separators: tuple[str, ...] = ("\n\n", "\n", ". ", ", ", " ")

    # ── Retrieval ───────────────────────────────────
    retrieval_top_k: int = 20      # candidatos do hybrid search
    rerank_top_k: int = 5          # resultado final pós-reranking
    vector_weight: float = 0.7     # peso do vector search no RRF
    keyword_weight: float = 0.3    # peso do keyword search no RRF
    rrf_k: int = 60               # constante RRF

    # ── Semantic Cache ──────────────────────────────
    cache_similarity_threshold: float = 0.95
    cache_ttl_seconds: int = 3600  # 1 hora

    # ── MCP Server ──────────────────────────────────
    mcp_transport: str = field(
        default_factory=lambda: os.getenv("MCP_TRANSPORT", "streamable_http")
    )
    mcp_host: str = field(
        default_factory=lambda: os.getenv("MCP_HOST", "0.0.0.0")
    )
    mcp_port: int = field(
        default_factory=lambda: int(os.getenv("MCP_PORT", "9090"))
    )


settings = Settings()
