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

The HermesContext MCP Server exposes 8 tools:

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
- **Asynchronous**: returns a `job_id` immediately, processes in background
- Reads files directly from the container's /data/ volume
- Supports .txt, .md, .csv, .json, .pdf (PDF via PyMuPDF)
- Processes directories recursively (all files ingested)
- Security: path must start with /data/
- **Parameters**: path (required), title (optional, defaults to filename), doc_type (optional), metadata (optional, JSON string)
- **Returns**: `job_id` for tracking progress via `rag_get_ingest_status`
- **Typical latency**: returns immediately; processing takes ~1-10s per file
- **Workflow**: SCP file to ~/docs/ on VM → call `rag_ingest_file` → poll `rag_get_ingest_status` with job_id

### 4. rag_get_ingest_status
**Purpose**: Check the status and progress of an async ingest job
- Tracks jobs started by `rag_ingest_file`
- **Parameters**: job_id (required, string returned by rag_ingest_file)
- **Returns**: status (PENDING/PROCESSING/COMPLETED/FAILED), progress %, document_id, chunk_count, error_message
- **Typical latency**: <100ms

### 5. rag_list_documents
**Purpose**: List indexed documents with pagination
- **Parameters**: limit (1-100), offset, doc_type (filter), response_format
- **Returns**: List of documents with ID, title, type, chunk_count, created_at
- **Typical latency**: <100ms

### 6. rag_get_document
**Purpose**: Get details of a specific document by ID
- **Parameters**: document_id, response_format
- **Returns**: Title, source, type, metadata, chunk_count, created_at
- **Typical latency**: <100ms

### 7. rag_delete_document
**Purpose**: Delete a document and all its chunks
- ⚠️ Irreversible action
- **Parameters**: document_id
- **Returns**: Confirmation message
- **Typical latency**: <500ms

### 8. rag_get_stats
**Purpose**: Get statistics about the RAG knowledge base
- **Parameters**: response_format
- **Returns**: Total documents, chunks, tokens, distribution by type
- **Typical latency**: <100ms

### Resource: rag://config
**Purpose**: Current RAG engine configuration
- embedding_model (BAAI/bge-m3), embedding_dim (1024), reranker_model (ms-marco-MiniLM-L-6-v2)
- chunk_size (512 tokens), chunk_overlap (64 tokens)
- retrieval_top_k (20), rerank_top_k (5)
- vector_weight (0.7), keyword_weight (0.3), rrf_k (60)
- cache_similarity_threshold (0.95), cache_ttl_seconds (3600)

### Search Pipeline
```
Query → Semantic Cache (Redis) → BGE-M3 Embed → Oracle VECTOR Search (k=20)
                                              → Oracle Text Search (k=20)
                                              → RRF Fusion (0.7/0.3)
                                              → Cross-Encoder Reranking → Top 5 Results
```
| Stage | Warm Latency |
|-------|-------------|
| Semantic cache check | ~1ms |
| BGE-M3 query embedding | ~100ms |
| Oracle VECTOR search | ~5ms |
| Oracle Text keyword search | ~5ms |
| RRF fusion + dedup | ~1ms |
| MiniLM cross-encoder reranking | ~150ms |
| **Total (warm, with reranker)** | **~350ms** |

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

## Document Ingestion

Workflow to index new documents into the RAG knowledge base. Requires an active SSH tunnel on port 9090.

### Prerequisite: Verify SSH Tunnel

Confirm the tunnel is active before using MCP tools:

```bash
# Windows
netstat -ano | findstr :9090

# Linux/Mac
ss -tlnp | grep 9090
```

If not active, open the tunnel (see Step 9 above).

### Step 1: Transfer File to VM

Use SCP to upload the local file to `~/docs/` on the VM (mapped to `/data/` in the container):

```bash
# Single file
scp -i $SSH_KEY /local/path/document.pdf ubuntu@$VM_IP:~/docs/

# Multiple files
scp -i $SSH_KEY /local/path/*.pdf ubuntu@$VM_IP:~/docs/

# Entire directory
scp -i $SSH_KEY -r /local/path/folder/ ubuntu@$VM_IP:~/docs/
```

Verify the file arrived on the VM:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "ls -la ~/docs/"
```

### Step 2: Ingest via MCP tool `rag_ingest_file`

With the tunnel active and the file on the VM, call the MCP tool:

**Single file:**
```
rag_ingest_file(path="/data/document.pdf", title="Document Title", doc_type="legislation")
```

**Entire directory** (processes recursively all supported files):
```
rag_ingest_file(path="/data/", doc_type="legislation")
```

**Parameters:**
- `path` (required) — must start with `/data/`
- `title` (optional) — defaults to filename
- `doc_type` (optional) — document category (e.g., `legislation`, `manual`, `report`)
- `metadata` (optional) — custom metadata as JSON string

**Supported formats:** `.txt`, `.md`, `.csv`, `.json`, `.pdf`

### Step 3: Track Ingestion Progress

`rag_ingest_file` is **asynchronous** — it returns a `job_id` immediately:

```
⏳ Ingest started in background.
- **job_id**: `a1b2c3d4-...`
- **File**: /data/document.pdf

Use `rag_get_ingest_status` with the job_id to track progress.
```

Poll the job status until completion:
```
rag_get_ingest_status(job_id="a1b2c3d4-...")
```

Completed response:
```
✅ **Status**: COMPLETED (100%)
- **job_id**: `a1b2c3d4-...`
- **document_id**: 42
- **Chunks**: 18
```

Confirm ingestion with `rag_list_documents` or `rag_get_stats`.

### Alternative: Ingest via CLI (no tunnel)

When the tunnel is not available, use the script directly via SSH:

```bash
# Single file
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.ingest_file /data/document.pdf --title 'Title' --type legislation"

# Entire directory
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.ingest_file /data/ --type legislation"
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

# Get stats (detailed)
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.test_get_stats"

# Ingest document
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.test_ingest_document"

# Search
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.test_search"

# List documents
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.test_list_documents"

# Get document
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.test_get_document"

# Inspect MCP tool schemas
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.check_tools"
```

## Performance Characteristics

| Operation | First Call (Cold) | Subsequent Calls (Warm) |
|-----------|-------------------|------------------------|
| rag_ingest_document | ~10-12 seconds | ~500ms |
| rag_ingest_file | returns immediately | processing: ~1-10s/file |
| rag_get_ingest_status | <100ms | <50ms |
| rag_search | ~12 seconds | ~350ms (with reranker) |
| rag_list_documents | <100ms | <50ms |
| rag_get_document | <100ms | <50ms |
| rag_delete_document | <500ms | <500ms |
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
# Automated health check (MCP, Redis, containers, disk, RAM)
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && bash scripts/health_check.sh"

# Manual checks
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
| Health check | `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && bash scripts/health_check.sh"` |
| Smoke test | `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.smoke_test"` |
| SCP upload | `scp -i $SSH_KEY /local/file.pdf ubuntu@$VM_IP:~/docs/` |
| Ingest file (MCP) | `rag_ingest_file(path="/data/file.pdf", doc_type="legislation")` |
| Check ingest status | `rag_get_ingest_status(job_id="<job_id>")` |
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
