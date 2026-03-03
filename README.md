# Hermes Context
Serviço RAG completo que roda como MCP Server, permitindo que qualquer LLM generativa (Claude, GPT, Gemini, etc.) busque, ingira e gerencie documentos em linguagem natural.

**Hermes Context** é um serviço RAG completo que opera como MCP Server, atuando como uma *camada de mediação de contexto* entre modelos de linguagem, ferramentas e fontes de conhecimento.

**100% self-hosted · Custo zero · Sem rate limit · Interface MCP**

---

## Por que o nome **Hermes Context**?

Na mitologia grega, Hermes é o mensageiro dos deuses, o mediador entre mundos distintos e o guardião das passagens, fronteiras e linguagens. Ele não cria a verdade — ele a transporta, interpreta e entrega corretamente a quem precisa.

Essa metáfora descreve com precisão o papel deste sistema:

- Ele **não gera conhecimento do zero** → recupera, organiza e entrega contexto confiável (RAG)
- Ele **não é a LLM** → atua como intermediário técnico e semântico (MCP)
- Ele **não é o banco de dados** → media o acesso ao conhecimento persistente (Oracle Cloud)

### Leitura arquitetural

> **Hermes Context é uma camada de mediação de contexto entre conhecimento, ferramentas e inteligência.**

Na prática, ele ocupa o espaço entre:

- **LLMs**, que precisam de contexto
- **Fontes de verdade**, que precisam ser consultadas com precisão
- **Ferramentas**, que precisam ser expostas de forma segura e padronizada

O **MCP Server** representa o protocolo de comunicação.
O **RAG** representa a recuperação fundamentada da informação.
O **Oracle Autonomous Database** representa a fonte de verdade persistente.

Hermes não compete com o Oráculo — ele opera a seu serviço.

---

## Stack

| Componente | Tecnologia | RAM |
|-----------|-----------|-----|
| Embedding | BGE-M3 (PyTorch CPU, 1024d, 100+ idiomas) | ~1.5 GB |
| Reranker | ms-marco-MiniLM-L-6-v2 (cross-encoder) | ~90 MB |
| Vector DB | Oracle Autonomous AI Database (Always Free, 20 GB) | 0 (cloud) |
| Cache | Redis 7 (semantic cache + task queue) | ~512 MB |
| Interface | MCP Server (streamable HTTP, porta 9090) | — |

**MMTEB**: BGE-M3 = **63.0** (melhor open-source multilingual ≤1B params, único modelo viável com latência <200ms em CPU ARM sem GPU).

## Tools MCP

| Tool | Descrição | R/W |
|------|-----------|-----|
| `rag_search` | Busca semântica híbrida (vector + keyword + reranking) | Read |
| `rag_ingest_document` | Indexa documento (chunk → embed → store) | Write |
| `rag_list_documents` | Lista documentos com paginação e filtros | Read |
| `rag_get_document` | Detalhes de um documento por ID | Read |
| `rag_delete_document` | Exclui documento e todos os chunks | Write |
| `rag_get_stats` | Estatísticas da base (docs, chunks, tokens) | Read |

## Instalação

### 1. Pré-requisitos
- Oracle Cloud Always Free (VM ARM 4C/24GB + Autonomous DB)
- Docker + Docker Compose
- Oracle Wallet (mTLS) configurado

### 2. Setup
```bash
git clone git@github.com:brunoleos/HermesContext.git
cd HermesContext
cp .env.example .env
# Editar .env com credenciais Oracle

docker compose up -d
```

### 3. Verificar
```bash
# Logs
docker compose logs -f hermes

# Health check (endpoint MCP ativo)
curl -s http://localhost:9090/mcp | head

# Testar via MCP Inspector (script automatizado — abre túnel SSH + browser)
bash scripts/mcp-inspector.sh
```

## Configuração MCP Client

O serviço roda como endpoint HTTP persistente na VM Oracle:

```
http://<vm-ip>:9090/mcp
```

Qualquer LLM ou agente com suporte a MCP conecta diretamente nessa URL.

### Claude Desktop (`claude_desktop_config.json`)

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

### Claude Code (CLI)

```bash
claude mcp add rag --transport http http://<vm-ip>:9090/mcp
```

### Anthropic API (em artifacts / apps)

```javascript
const response = await fetch("https://api.anthropic.com/v1/messages", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "claude-sonnet-4-20250514",
    max_tokens: 1000,
    messages: [{ role: "user", content: "Busque requisitos para progressão de regime" }],
    mcp_servers: [{
      type: "url",
      url: "http://<vm-ip>:9090/mcp",
      name: "rag"
    }]
  })
});
```

### Qualquer SDK MCP (Python)

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
        print(result)
```

### Exemplo de consumo por LLM

A LLM generativa invoca os tools assim:

```
Usuário: "Quais são os requisitos para progressão de regime?"

LLM → chama rag_search(query="requisitos progressão de regime", top_k=5)

MCP Server retorna:
  ## Resultados para: "requisitos progressão de regime"
  *5 resultados de 23 candidatos em 342ms*

  ### 1. LEP - Lei de Execução Penal (score: 0.8923)
  Art. 112. A pena privativa de liberdade será executada em forma
  progressiva com a transferência para regime menos rigoroso...

  ### 2. Resolução SAP 45/2024 (score: 0.8412)
  ...

LLM → sintetiza resposta final para o usuário usando os trechos.
```

## Arquitetura

```
LLM (Claude/GPT/Gemini)
        │ MCP Protocol (HTTP)
        │ http://<vm-ip>:9090/mcp
        ▼
┌──────────────────────┐
│   MCP Server (hermes_mcp)│
│   :9090/mcp          │
│ ┌──────┐ ┌────────┐ │
│ │BGE-M3│ │Reranker│ │     ┌──────────────┐
│ │Embed │ │MiniLM  │ │     │   Redis       │
│ └──┬───┘ └───┬────┘ │     │ Cache + Queue │
│    │         │      │     └──────────────┘
│ ┌──▼─────────▼────┐ │
│ │ Hybrid Retrieval │ │
│ │ Dense+Keyword+RRF│ │
│ └────────┬────────┘ │
└──────────┼──────────┘
           │
  ┌────────▼──────────┐
  │ Oracle Autonomous  │
  │ AI Database        │
  │ (Vector + Text)    │
  └───────────────────┘
```

## Custos

| Recurso | Custo |
|---------|-------|
| VM ARM 4C/24GB | $0 (Oracle Always Free) |
| Autonomous DB 20GB | $0 (Oracle Always Free) |
| BGE-M3 embedding | $0 (MIT, local) |
| Reranker MiniLM | $0 (Apache 2.0, local) |
| Redis | $0 (BSD, local) |
| **Total** | **$0/mês** |

## Performance estimada (ARM Ampere A1)

| Operação | Latência | Throughput |
|----------|----------|------------|
| Embedding (1 chunk) | ~100ms | ~10 chunks/s |
| Reranking (20 docs) | ~150ms | — |
| Vector search (Oracle HNSW) | ~5ms | — |
| **Query completa** (embed + search + rerank) | **~350ms** | ~3 queries/s |
| Ingestão (1 doc, 10 chunks) | ~1.5s | — |
