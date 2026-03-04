---
name: hermes-context
description: Deploy, manage, and ingest documents into the HermesContext MCP Server on Oracle Cloud Always Free infrastructure. Use this skill when deploying, updating, troubleshooting, testing, or ingesting documents into the HermesContext RAG application on an Oracle Cloud VM.
---

# HermesContext Skill

Deploy, manage, and ingest documents into the HermesContext MCP Server on Oracle Cloud Always Free infrastructure.

## Configuration

Before using this skill, set the following variables:

```bash
export VM_IP="147.15.91.57"       # Oracle Cloud VM IP
export SSH_KEY="~/.ssh/id_ed25519" # SSH key path
```

> **Tip**: Add to shell profile: `echo 'export VM_IP="147.15.91.57"' >> ~/.bashrc`

## Overview

HermesContext is a RAG (Retrieval-Augmented Generation) MCP Server providing document ingestion, embedding, vector search, and hybrid search using Oracle Database 23ai and Redis. Deployed on Oracle Cloud Always Free (ARM Ampere A1).

## When to Use This Skill

- Deploying HermesContext from scratch to Oracle Cloud
- Updating an existing deployment with new code
- **Ingesting documents into the RAG knowledge base** (SCP upload + MCP tool)
- Troubleshooting deployment issues
- Performing maintenance tasks (restart, health check, logs)
- Testing the MCP server after deployment
- Running smoke tests to verify all MCP tools

## MCP Server Tools

The HermesContext MCP Server exposes 7 tools:

### 1. rag_search
**Purpose**: Semantic search using embedding + keyword hybrid search
- Combines vector search (BGE-M3 dense embeddings) with keyword search
- Applies Reciprocal Rank Fusion
- Optional cross-encoder reranking for improved precision
- **Parameters**: query, top_k (1-20), use_reranker (bool), response_format (markdown/json)
- **Typical latency**: 4-12000ms (first call slower due to model loading)

### 2. rag_ingest_document
**Purpose**: Index a new document in the RAG knowledge base
- Chunks document into smaller pieces
- Generates embeddings using BGE-M3 (1024d)
- Stores in Oracle Autonomous DB for semantic search
- **Parameters**: title, content, source (optional), doc_type (optional), metadata (optional)
- **Returns**: document_id, chunk_count, elapsed_ms
- **Typical latency**: 10000-12000ms (first call slower due to model loading)

### 3. rag_ingest_file
**Purpose**: Ingest a file or directory already on the VM (in /data/) into the RAG knowledge base
- Reads files directly from the container's /data/ volume
- Supports .txt, .md, .csv, .json, .pdf (PDF via PyMuPDF)
- Processes directories recursively (all files ingested)
- Security: path must start with /data/
- **Parameters**: path (required), title (optional, defaults to filename), doc_type (optional)
- **Returns**: Summary with document_id, chunk_count, elapsed time
- **Typical latency**: ~1-10s per file (depends on file size)
- **Workflow**: SCP file to ~/docs/ on VM → call rag_ingest_file(path="/data/filename.pdf")

### 4. rag_list_documents
**Purpose**: List indexed documents with pagination
- **Parameters**: limit (1-100), offset, doc_type (filter), response_format
- **Returns**: List of documents with ID, title, type, chunk_count, created_at
- **Typical latency**: <100ms

### 5. rag_get_document
**Purpose**: Get details of a specific document by ID
- **Parameters**: document_id, response_format
- **Returns**: Title, source, type, metadata, chunk_count, created_at
- **Typical latency**: <100ms

### 6. rag_delete_document
**Purpose**: Delete a document and all its chunks
- ⚠️ Irreversible action
- **Parameters**: document_id
- **Returns**: Confirmation message
- **Typical latency**: <500ms

### 7. rag_get_stats
**Purpose**: Get statistics about the RAG knowledge base
- **Parameters**: response_format
- **Returns**: Total documents, chunks, tokens, distribution by type
- **Typical latency**: <100ms

### Resource: rag://config
**Purpose**: Current RAG engine configuration
- embedding_model, embedding_dim, reranker_model, chunk_size, chunk_overlap
- retrieval_top_k, rerank_top_k, vector_weight, keyword_weight, cache_ttl_seconds

## Prerequisites

Before using this skill, ensure:
- Oracle Cloud account with access
- SSH key pair generated (`ssh-keygen -t ed25519`)
- Wallet file downloaded from Oracle Autonomous Database
- GitHub repository access configured
- VM_IP environment variable set

## Deployment Steps

### Step 1: Verify Remote Server Connectivity

Test SSH connection to the remote server:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "uname -a"
```

### Step 2: Pull Latest Code

On the remote server, navigate to the project directory and pull the latest changes:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && git pull"
```

If the repository has not been cloned yet:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "git clone git@github.com:brunoleos/HermesContext.git ~/HermesContext"
```

### Step 3: Configure Environment

Ensure the `.env` file exists with required configuration:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "ls ~/HermesContext/.env"
```

Required environment variables:
- `ORACLE_DSN` - Connection string from Oracle Autonomous Database
- `ORACLE_USER` - Database username (typically ADMIN)
- `ORACLE_PASSWORD` - Database password
- `ORACLE_WALLET_DIR` - Path to wallet directory (e.g., /wallet)
- `REDIS_URL` - Redis connection string
- `EMBEDDING_MODEL` - Embedding model (default: BAAI/bge-m3)
- `RERANKER_MODEL` - Reranker model (default: cross-encoder/ms-marco-MiniLM-L-6-v2)
- `MCP_TRANSPORT` - Transport protocol (streamable_http)
- `MCP_HOST` - Host binding (0.0.0.0)
- `MCP_PORT` - Server port (9090)

### Step 4: Verify Wallet Configuration

Ensure the Oracle wallet is properly configured:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "ls -la ~/wallet/ && cat ~/wallet/sqlnet.ora"
```

The sqlnet.ora should contain:
```
WALLET_LOCATION = (SOURCE = (METHOD = file) (METHOD_DATA = (DIRECTORY="/home/ubuntu/wallet")))
```

### Step 5: Build Docker Image

Build the Hermes container:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose build hermes"
```

Expected build time: 10-20 minutes on first run (includes downloading ML models).

### Step 6: Start Services

Start all services including Redis and Hermes:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose up -d"
```

Verify containers are running:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose ps"
```

### Step 7: Verify Deployment

Check container logs for successful startup:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose logs --tail 20 hermes"
```

Expected output should contain:
```
INFO: Uvicorn running on http://0.0.0.0:9090
```

### Step 8: Test MCP Endpoint

Test the MCP server is responding:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "curl -s -X POST http://localhost:9090/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-03-26\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1.0\"}}}'"
```

A successful response contains `serverInfo` and `capabilities`.

### Step 9: Open SSH Tunnel (Automatic)

The MCP server is not directly accessible via public IP (returns `421 Invalid Host header`). After successful deployment, **automatically** open an SSH tunnel to access it locally.

**Windows (execute via PowerShell):**
```powershell
Start-Process -FilePath "ssh" -ArgumentList "-i $env:USERPROFILE\.ssh\id_ed25519 -L 9090:localhost:9090 -N ubuntu@147.15.91.57" -WindowStyle Hidden
```

**Linux/Mac:**
```bash
ssh -i $SSH_KEY -L 9090:localhost:9090 -f -N ubuntu@$VM_IP
```

Verify tunnel is active:
- Windows: `netstat -ano | findstr :9090`
- Linux/Mac: `ss -tlnp | grep 9090`

Once active, the MCP server is available at `http://localhost:9090/mcp`.

## Ingest de Documentos

Workflow para indexar novos documentos na base de conhecimento RAG. Requer túnel SSH ativo na porta 9090.

### Pré-requisito: Verificar túnel SSH

Confirmar que o túnel está ativo antes de usar as MCP tools:

```bash
# Windows
netstat -ano | findstr :9090

# Linux/Mac
ss -tlnp | grep 9090
```

Se não estiver ativo, abrir o túnel (ver Step 9 acima).

### Passo 1: Transferir arquivo para a VM

Usar SCP para enviar o arquivo local para o diretório `~/docs/` na VM (mapeado para `/data/` no container):

```bash
# Arquivo único
scp -i $SSH_KEY /caminho/local/documento.pdf ubuntu@$VM_IP:~/docs/

# Múltiplos arquivos
scp -i $SSH_KEY /caminho/local/*.pdf ubuntu@$VM_IP:~/docs/

# Diretório inteiro
scp -i $SSH_KEY -r /caminho/local/pasta/ ubuntu@$VM_IP:~/docs/
```

Verificar que o arquivo chegou na VM:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "ls -la ~/docs/"
```

### Passo 2: Ingerir via MCP tool `rag_ingest_file`

Com o túnel ativo e o arquivo na VM, chamar a tool MCP:

**Arquivo único:**
```
rag_ingest_file(path="/data/documento.pdf", title="Título do Documento", doc_type="legislacao")
```

**Diretório inteiro** (processa recursivamente todos os arquivos suportados):
```
rag_ingest_file(path="/data/", doc_type="legislacao")
```

**Parâmetros:**
- `path` (obrigatório) — deve começar com `/data/`
- `title` (opcional) — padrão: nome do arquivo
- `doc_type` (opcional) — categoria do documento (ex: `legislacao`, `manual`, `relatorio`)

**Formatos suportados:** `.txt`, `.md`, `.csv`, `.json`, `.pdf`

### Passo 3: Verificar resultado

A tool retorna:
```json
{
  "document_id": 42,
  "chunk_count": 18,
  "elapsed_ms": 3200,
  "title": "Título do Documento"
}
```

Confirmar ingestão com `rag_list_documents` ou `rag_get_stats`.

### Alternativa: Ingest via CLI (sem túnel)

Quando o túnel não estiver disponível, usar o script diretamente via SSH:

```bash
# Arquivo único
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.ingest_file /data/documento.pdf --title 'Título' --type legislacao"

# Diretório inteiro
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.ingest_file /data/ --type legislacao"
```

## Smoke Tests

Run comprehensive tests for all MCP tools using the existing test scripts:

### Full Pipeline Smoke Test (Recommended)
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.smoke_test"
```

This test: ingests a test document → tests embedding → tests vector search → tests hybrid search with reranking → verifies statistics → cleans up.

### Individual Tests

```bash
# Stats
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.test_stats"

# Ingest document
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.test_ingest_document"

# Search
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.test_search"

# List documents
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.test_list_documents"

# Get document
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.test_get_document"
```

## Performance Characteristics

| Operation | First Call (Cold) | Subsequent Calls (Warm) |
|-----------|-------------------|------------------------|
| rag_ingest_document | ~10-12 seconds | ~500ms |
| rag_ingest_file | ~10-12 seconds (first) | ~1-10s (depends on file size) |
| rag_search | ~12 seconds | ~4-50ms |
| rag_list_documents | <100ms | <50ms |
| rag_get_document | <100ms | <50ms |
| rag_get_stats | <100ms | <50ms |

> **Note**: First call latency is higher due to model loading into memory. Models are cached in the container and persist between calls.

## Maintenance Commands

### View Logs

```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose logs --tail 100 hermes"
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose logs -f hermes"
```

### Restart Services

```bash
# Restart only Hermes
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose restart hermes"

# Full rebuild and restart
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose build hermes && docker compose up -d hermes"
```

### Health Check

```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker stats --no-stream"
ssh -i $SSH_KEY ubuntu@$VM_IP "free -h && df -h /"
```

### Database Operations

```bash
# Test database connection
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose run --rm hermes python -m scripts.test_connection"

# Initialize/update schema
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose run --rm hermes python -m scripts.init_db"

# Warm up ML models
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose run --rm hermes python -m scripts.warmup_models"
```

## Troubleshooting

### Connection Issues

If the MCP endpoint is not accessible:
1. Check SSH tunnel is active: `netstat -ano | findstr :9090` (Windows) or `ss -tlnp | grep 9090` (Linux)
2. Verify container is running: `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose ps"`
3. Check container logs: `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose logs hermes | grep 9090"`

### Database Connection

If Oracle connection fails:
1. Verify wallet is in correct location: `ssh -i $SSH_KEY ubuntu@$VM_IP "ls -la ~/wallet/"`
2. Check DSN in .env is correct
3. Ensure Autonomous Database is running (not stopped in Oracle Console)
4. Test connection: `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose run --rm hermes python -m scripts.test_connection"`

### Performance Issues

If embedding is slow (>500ms on warm calls):
- Check CPU usage: `ssh -i $SSH_KEY ubuntu@$VM_IP "docker stats --no-stream hermes"`
- First call cold start is expected (~10-12s)

### Model Download Issues

If models fail to download during build:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose run --rm hermes python -m scripts.warmup_models"
```

### MCP Tools Not Working

If a specific MCP tool fails:
1. Check logs: `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose logs hermes | grep -A 10 'error'"`
2. Run individual tool test from the smoke tests above
3. Verify database connectivity
4. Check if models are loaded: `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose logs hermes | grep 'Modelos'"`

## MCP Inspector

The MCP Inspector is a web-based interface for interactively testing MCP tools.

### Automated Script (Recommended)

Run the automated script from the local machine:
```bash
bash scripts/mcp-inspector.sh
```

The script automatically:
1. Kills old Inspector processes on the VM (`pkill -9 node`) to free ports 6274/6277
2. Starts the Inspector on the VM in background via `nohup`
3. Polls the VM log to capture the auth token
4. Frees local ports if occupied (Windows: `netstat -ano` + `taskkill`)
5. Opens a local SSH tunnel (`-L 6274:localhost:6274 -L 6277:localhost:6277 -N`)
6. Opens the browser with pre-configured `streamable-http` transport

Browser URL format:
```
http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>&transport=streamable-http&serverUrl=http://localhost:9090/mcp
```

### Manual Setup

**Step 1: Start Inspector on VM**
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "pkill -9 node 2>/dev/null; nohup npx @modelcontextprotocol/inspector http://localhost:9090/mcp > /tmp/inspector.log 2>&1 < /dev/null &"
```

**Step 2: Get Auth Token**
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "sleep 5 && cat /tmp/inspector.log | grep MCP_PROXY_AUTH_TOKEN"
```

**Step 3: Open SSH Tunnel**
```bash
ssh -i $SSH_KEY -L 6274:localhost:6274 -L 6277:localhost:6277 -N ubuntu@$VM_IP
```

**Step 4: Open Browser**
Navigate to `http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>&transport=streamable-http&serverUrl=http://localhost:9090/mcp`

> **Important**: The Inspector also requires the port 9090 tunnel to be active for MCP tools to work. Open it separately if not already running.

## SSH Tunnel Management

### Start Tunnel

**Linux/Mac:**
```bash
ssh -i $SSH_KEY -L 9090:localhost:9090 -f -N ubuntu@$VM_IP
```

**Windows (PowerShell):**
```powershell
Start-Process -FilePath "ssh" -ArgumentList "-i $env:USERPROFILE\.ssh\id_ed25519 -L 9090:localhost:9090 -N ubuntu@$VM_IP" -WindowStyle Hidden
```

### Check Tunnel Status

```bash
# Linux/Mac
ss -tlnp | grep 9090

# Windows
netstat -ano | findstr :9090
```

### Stop Tunnel

```bash
# Linux/Mac
pkill -f "ssh.*-L 9090"

# Windows CMD
taskkill /F /IM ssh.exe
```

> **Note**: Port conflicts — if 9090 is in use locally, use `-L 9091:localhost:9090` and adjust the MCP URL accordingly.

## Quick Reference

| Task | Command |
|------|---------|
| Deploy | `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && git pull && docker compose build hermes && docker compose up -d"` |
| Check status | `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose ps"` |
| View logs | `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose logs --tail 20 hermes"` |
| Restart | `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose restart hermes"` |
| Smoke test | `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.smoke_test"` |
| SCP upload | `scp -i $SSH_KEY /local/file.pdf ubuntu@$VM_IP:~/docs/` |
| Ingest file (MCP) | `rag_ingest_file(path="/data/file.pdf", doc_type="legislacao")` |
| MCP Inspector | `bash scripts/mcp-inspector.sh` |
| Tunnel start (Windows) | `Start-Process -FilePath "ssh" -ArgumentList "-i $env:USERPROFILE\.ssh\id_ed25519 -L 9090:localhost:9090 -N ubuntu@147.15.91.57" -WindowStyle Hidden` |
| Tunnel status | `netstat -ano \| findstr :9090` (Windows) / `ss -tlnp \| grep 9090` (Linux) |
| Tunnel stop | `taskkill /F /IM ssh.exe` (Windows) / `pkill -f "ssh.*-L 9090"` (Linux) |

## Additional Resources

- `DEPLOY_GUIDE.md` - Complete deployment guide with all phases (Oracle Cloud provisioning)
- `MCP_SETUP.md` - MCP server connection setup (SSH tunnel + Claude Code)
- `ARCHITECTURE.md` - System architecture details
- `scripts/mcp-inspector.sh` - Automated MCP Inspector launcher
- `src/server.py` - MCP server implementation with all tools
