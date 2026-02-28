# RAG Oracle Always Free — Versão Final
## 100% Self-Hosted · Custo Zero · Sem Rate Limit · Interface MCP Server

---

## 1. Decisão Final: Embedding Model

### Restrições absolutas
- **Hardware**: ARM Ampere A1 — 4 OCPUs, 24 GB RAM, zero GPU
- **Custo**: $0/mês (nenhuma API paga, nenhum free tier externo)
- **Rate limit**: Nenhum (modelo roda local, throughput ilimitado)
- **Idioma**: PT-BR obrigatório (documentos do sistema penitenciário)

### Modelo selecionado: BGE-M3 (BAAI)

| Atributo | Valor |
|----------|-------|
| **MMTEB Score** | 63.0 (melhor open-source multilingual ≤1B params) |
| **Retrieval (nDCG@10)** | ~68 |
| **Parâmetros** | 567M |
| **Dimensões** | 1024 (reduzível via MRL: 768, 512, 256) |
| **Context Window** | 8192 tokens |
| **Idiomas** | 100+ incluindo PT-BR |
| **RAM (ONNX INT8)** | ~1.2 GB |
| **Latência ARM** | ~80–150 ms/chunk |
| **Features** | Dense + Sparse + ColBERT multi-vector |
| **Licença** | MIT (uso comercial irrestrito) |
| **Sparse Vectors** | ✅ BM25-like nativo (hybrid search sem Oracle Text) |

### Por que não modelos maiores?

| Modelo | MMTEB | RAM Q4 | Latência ARM | Veredito |
|--------|-------|--------|-------------|----------|
| KaLM-Gemma3-12B | 72.3 | ~11 GB | 2–8 s | ❌ Inviável: consome 50% da RAM, latência destrutiva |
| Qwen3-Embedding-8B | 70.6 | ~5 GB | 1–4 s | ❌ Inviável: latência > 1s inaceitável para serving |
| Qwen3-Embedding-4B | ~67 | ~3 GB | 0.5–1 s | ⚠️ Marginal: ~5 pontos a mais, 5–10× mais lento |
| **BGE-M3** | **63.0** | **1.2 GB** | **80–150 ms** | **✅ Melhor trade-off para CPU ARM** |

BGE-M3 é a escolha correta porque:
1. Latência sub-200ms permite UX interativa
2. Sparse vectors nativos eliminam dependência de Oracle Text para keyword search
3. 1.2 GB de RAM deixa 80%+ da VM livre para o restante da stack
4. MIT license sem restrições

---

## 2. Alocação de Recursos (24 GB)

```
┌──────────────────────────────────────────────────────────┐
│  VM ARM Ampere A1: 4 OCPUs / 24 GB RAM / 150 GB disk    │
│                                                          │
│  OS + Docker           2.0 GB                            │
│  BGE-M3 (ONNX INT8)   1.5 GB  ← embedding              │
│  Reranker (MiniLM)     0.5 GB  ← cross-encoder          │
│  RAG API (FastAPI)     2.0 GB  ← app + MCP server       │
│  Ingest Worker         4.0 GB  ← Unstructured + Celery   │
│  Redis                 0.6 GB  ← cache + queue           │
│  Prometheus+Grafana    0.5 GB  ← monitoramento           │
│  ─────────────────────────────────────                   │
│  TOTAL USADO          11.1 GB                            │
│  BUFFER LIVRE         12.9 GB  (54% livre)               │
└──────────────────────────────────────────────────────────┘
```

---

## 3. Arquitetura Completa

```
                         ┌─────────────────────────┐
                         │   LLM Generativa (ext.)  │
                         │  Claude / Gemini / etc.  │
                         └────────────┬────────────┘
                                      │ MCP Protocol (HTTP)
                                      │ http://<vm-ip>:9090/mcp
                         ┌────────────▼────────────┐
                         │     MCP SERVER (Python)   │
                         │     hermes_mcp  :9090        │
                         │                           │
                         │  Tools expostos:           │
                         │  • rag_search             │
                         │  • rag_ingest_document    │
                         │  • rag_list_documents     │
                         │  • rag_get_document       │
                         │  • rag_delete_document    │
                         │  • rag_get_stats          │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │   RAG ENGINE (interno)    │
                         │                           │
                         │  ┌─────────┐ ┌─────────┐ │
                         │  │ BGE-M3  │ │Reranker │ │
                         │  │ Embed   │ │MiniLM   │ │
                         │  └────┬────┘ └────┬────┘ │
                         │       │           │       │
                         │  ┌────▼───────────▼────┐ │
                         │  │   Hybrid Retrieval   │ │
                         │  │ Dense + Sparse + RRF │ │
                         │  └──────────┬──────────┘ │
                         └─────────────┼────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │      Oracle Autonomous AI DB         │
                    │  • VECTOR index (dense, HNSW)       │
                    │  • Oracle Text index (keyword)       │
                    │  • 20 GB Always Free                 │
                    └─────────────────────────────────────┘
```

---

## 4. Oracle DB Schema

```sql
CREATE TABLE documents (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title           VARCHAR2(500) NOT NULL,
    source          VARCHAR2(1000),
    doc_type        VARCHAR2(100),
    metadata        JSON,
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE TABLE chunks (
    id              NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id     NUMBER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index     NUMBER NOT NULL,
    chunk_text      VARCHAR2(4000) NOT NULL,
    enriched_text   VARCHAR2(4000),
    token_count     NUMBER,
    embedding       VECTOR(1024, FLOAT32),
    created_at      TIMESTAMP DEFAULT SYSTIMESTAMP,
    CONSTRAINT uq_doc_chunk UNIQUE (document_id, chunk_index)
);

CREATE VECTOR INDEX idx_chunk_embedding ON chunks(embedding)
    ORGANIZATION NEIGHBOR PARTITIONS
    WITH DISTANCE COSINE
    WITH TARGET ACCURACY 95;

CREATE INDEX idx_chunk_text ON chunks(chunk_text)
    INDEXTYPE IS CTXSYS.CONTEXT;

CREATE INDEX idx_chunk_doc_id ON chunks(document_id);

-- Hybrid Search: vector + keyword em SQL único
-- Chamado pelo RAG engine internamente
SELECT c.id, c.chunk_text, c.document_id, d.title,
       VECTOR_DISTANCE(c.embedding, :query_vec, COSINE) AS vec_dist,
       SCORE(1) AS text_score
FROM chunks c
JOIN documents d ON c.document_id = d.id
WHERE CONTAINS(c.chunk_text, :keyword_query, 1) > 0
ORDER BY (0.7 * (1 - VECTOR_DISTANCE(c.embedding, :query_vec, COSINE))
        + 0.3 * SCORE(1)) DESC
FETCH FIRST :top_k ROWS ONLY;
```

---

## 5. Docker Compose

```yaml
services:
  hermes:
    build: .
    command: python -m src.server
    env_file: .env
    volumes:
      - /home/ubuntu/wallet:/wallet:ro
      - models-cache:/root/.cache
    deploy:
      resources:
        limits:
          cpus: "3.0"
          memory: 8G
    ports:
      - "9090:9090"
    restart: unless-stopped
    depends_on:
      - redis

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 600M
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  models-cache:
  redis-data:
```

---

## 6. Interface MCP Server

### 6.1 Tools expostos

O serviço expõe 6 ferramentas via MCP Protocol que qualquer LLM generativa pode invocar:

| Tool | Descrição | Tipo | Annotations |
|------|-----------|------|-------------|
| `rag_search` | Busca semântica híbrida com reranking | Read | readOnly, idempotent |
| `rag_ingest_document` | Indexa documento (chunk→embed→store) | Write | not readOnly |
| `rag_list_documents` | Lista documentos com paginação | Read | readOnly, idempotent |
| `rag_get_document` | Detalhes de um documento por ID | Read | readOnly, idempotent |
| `rag_delete_document` | Exclui documento + chunks | Write | destructive, idempotent |
| `rag_get_stats` | Estatísticas da base RAG | Read | readOnly, idempotent |

### 6.2 Transporte: HTTP endpoint persistente

O MCP server roda como serviço HTTP na VM Oracle. LLMs conectam direto:

```
Endpoint MCP:  http://<vm-ip>:9090/mcp
```

Com Caddy reverse proxy na VM AMD Micro (HTTPS):

```
Endpoint MCP:  https://rag.meudominio.com/mcp
```

### 6.3 Fluxo de uma query

```
Usuário: "Quais são os requisitos para progressão de regime?"
    │
    ▼
LLM Generativa (Claude / GPT / Gemini / DeepSeek)
    │
    │  Tool call: rag_search(query="requisitos progressão de regime", top_k=5)
    ▼
MCP Server (hermes_mcp)
    │
    ├─ 1. Semantic Cache check (Redis)          ~1ms
    ├─ 2. BGE-M3 embed query (1024d)            ~100ms
    ├─ 3. Oracle Vector Search (HNSW, k=20)     ~5ms
    ├─ 4. Oracle Keyword Search (Text, k=20)    ~5ms
    ├─ 5. RRF Fusion (merge + dedup)            ~1ms
    ├─ 6. MiniLM Reranking (top 20 → top 5)    ~150ms
    │                                     TOTAL ~350ms
    ▼
Resposta MCP → LLM → Resposta final ao usuário
```

### 6.4 Exemplo: Config Claude Desktop

```json
{
  "mcpServers": {
    "rag": {
      "type": "url",
      "url": "http://<vm-ip>:9090/mcp"
    }
  }
}
```

### 6.5 Exemplo: Config Claude Code (CLI)

```bash
claude mcp add rag --transport http http://<vm-ip>:9090/mcp
```

### 6.6 Exemplo: SDK MCP Python (qualquer agente)

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client("http://<vm-ip>:9090/mcp") as (r, w, _):
    async with ClientSession(r, w) as session:
        await session.initialize()
        result = await session.call_tool("rag_search", {
            "query": "requisitos progressão de regime",
            "top_k": 5
        })
```
