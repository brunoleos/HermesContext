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
| `rag_ingest_file` | Ingere arquivo ou diretório já na VM (`/data/`) | Write |
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
```

### 3. Build e Deploy

O projeto suporta **dois modos de build**:

#### Modo Produção (padrão)
```bash
# Build + deploy com pré-download de modelos
docker compose up -d
```
- Modelos ML (BGE-M3, MiniLM) são baixados durante o `docker build`
- Código é copiado na imagem (não pode ser editado em tempo de execução)
- Mais lento na primeira execução (~15-20 min)
- Imagem maior (~2.5 GB com modelos)
- Recomendado para produção

#### Modo Desenvolvimento (hot reload)
```bash
# Build + deploy com hot reload de código
docker compose -f docker-compose.dev.yml up -d
```
- Modelos ML são baixados na primeira execução do servidor (~5 min)
- Código é montado como volume (edições refletem imediatamente)
- Build mais rápido (~2 min)
- Imagem menor (~400 MB)
- Recomendado para desenvolvimento

**Diferenças:** O `Dockerfile` agora usa **multi-stage build** com dois targets:
- `production` (padrão): pré-baixa modelos, copia código
- `development`: instala `watchdog`, usa volumes de código com hot reload

### 4. Verificar

### 3. Verificar
```bash
# Logs (na VM)
docker compose logs -f hermes

# Testar endpoint MCP (na VM, com headers obrigatórios)
curl -X POST http://localhost:9090/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'

# Testar via MCP Inspector (abre túnel SSH + browser para testar os tools)
bash scripts/mcp-inspector.sh
```

## Configuração MCP Client

O serviço roda como endpoint HTTP persistente na VM Oracle. Há duas formas de acessá-lo:

### Acesso via SSH Tunnel (recomendado)

O servidor não é acessível diretamente pelo IP público (retorna `421 Invalid Host header`). Use SSH tunnel:

```bash
# Em um terminal separado, mantenha o túnel ativo:
ssh -i ~/.ssh/id_ed25519 -L 9090:localhost:9090 -N ubuntu@<vm-ip>
```

Após abrir o túnel, o servidor fica acessível em `http://localhost:9090/mcp`.

### Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "rag": {
      "type": "url",
      "url": "http://localhost:9090/mcp"
    }
  }
}
```

### Claude Code (CLI)

```bash
claude mcp add rag --transport http http://localhost:9090/mcp
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

async with streamablehttp_client("http://localhost:9090/mcp") as (r, w, _):
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

## Workflows

### Workflow A: Consulta (via MCP tools)

Para buscar, listar e consultar documentos já indexados:

```bash
# 1. Abrir SSH tunnel (terminal separado, manter ativo)
ssh -i ~/.ssh/id_ed25519 -L 9090:localhost:9090 -N ubuntu@<vm-ip>

# 2. Usar MCP tools normalmente (Claude Code, Claude Desktop, Python SDK)
#    rag_search, rag_list_documents, rag_get_document, rag_get_stats, rag_delete_document
```

### Workflow B: Ingestão de Arquivos (via SCP + MCP tool)

Para ingerir PDFs, textos ou pastas inteiras na base RAG:

```bash
# 1. Criar pasta de docs na VM (uma vez)
ssh -i ~/.ssh/id_ed25519 ubuntu@<vm-ip> "mkdir -p ~/docs"

# 2. Upload do arquivo para a VM via SCP
scp -i ~/.ssh/id_ed25519 documento.pdf ubuntu@<vm-ip>:~/docs/

# 3. Chamar rag_ingest_file via MCP (com túnel SSH ativo em outro terminal)
# Arquivo único:
rag_ingest_file(path="/data/documento.pdf", title="Resolução SAP 45/2024", doc_type="resolucao")

# Ou pasta inteira (recursivo):
rag_ingest_file(path="/data/", doc_type="legislacao")

# 4. Verificar ingestão via MCP
rag_get_stats()
```

**Pré-requisito**: SSH tunnel deve estar ativo (ver Workflow A, passo 1).

> O volume `/data` dentro do container mapeia para `~/docs` na VM. A tool `rag_ingest_file`
> lê arquivos diretamente do `/data/` e os indexa. Formatos suportados: `.txt`, `.md`, `.csv`, `.json`, `.pdf`.

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
