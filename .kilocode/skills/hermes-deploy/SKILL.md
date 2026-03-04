---
name: hermes-deploy
description: Deploy and manage HermesContext MCP Server on Oracle Cloud Always Free infrastructure. This skill should be used when deploying, updating, troubleshooting, or testing the HermesContext RAG application on an Oracle Cloud VM.
---

# Hermes Deploy Skill

Deploy and manage HermesContext MCP Server on Oracle Cloud Always Free infrastructure.

## Configuration

Before using this skill, set the following variables:

```bash
# Set your VM IP address
export VM_IP="147.15.91.57"  # Replace with your Oracle Cloud VM IP

# SSH key path (default)
export SSH_KEY="~/.ssh/id_ed25519"
```

> **Tip**: Add these to your shell profile for convenience:
> ```bash
> echo 'export VM_IP="147.15.91.57"' >> ~/.bashrc
> echo 'export SSH_KEY="~/.ssh/id_ed25519"' >> ~/.bashrc
> source ~/.bashrc
> ```

## Overview

HermesContext is a RAG (Retrieval-Augmented Generation) MCP Server that provides document ingestion, embedding, vector search, and hybrid search capabilities using Oracle Database 23ai and Redis. This skill guides through deploying and maintaining the application on Oracle Cloud's free tier (Always Free).

## When to Use This Skill

Use this skill when:
- Deploying HermesContext from scratch to Oracle Cloud
- Updating an existing deployment with new code
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
ssh -i $SSH_KEY ubuntu@$VM_IP
```

Verify the server is reachable and note the IP address for all subsequent operations.

### Step 2: Pull Latest Code

On the remote server, navigate to the project directory and pull the latest changes:
```bash
cd ~/HermesContext
git pull
```

If the repository has not been cloned yet:
```bash
git clone git@github.com:brunoleos/HermesContext.git
cd HermesContext
```

### Step 3: Configure Environment

Ensure the `.env` file exists with required configuration:
```bash
cp .env.example .env
nano .env
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
ls -la ~/wallet/
cat ~/wallet/sqlnet.ora
```

The sqlnet.ora should point to the correct wallet directory:
```
WALLET_LOCATION = (SOURCE = (METHOD = file) (METHOD_DATA = (DIRECTORY="/home/ubuntu/wallet")))
```

### Step 5: Build Docker Image

Build the Hermes container:
```bash
docker compose build hermes
```

Expected build time: 10-20 minutes on first run (includes downloading ML models).

### Step 6: Start Services

Start all services including Redis and Hermes:
```bash
docker compose up -d
```

Verify containers are running:
```bash
docker compose ps
```

### Step 7: Verify Deployment

Check container logs for successful startup:
```bash
docker compose logs --tail 20 hermes
```

Expected output should contain:
```
INFO: Uvicorn running on http://0.0.0.0:9090
```

### Step 8: Test MCP Endpoint

Test the MCP server is responding:
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "curl -X POST http://localhost:9090/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-03-26\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1.0\"}}}'"
```

A successful response contains `serverInfo` and `capabilities`.

### Step 9: Open SSH Tunnel (Automatic)

The MCP server is not directly accessible via public IP (returns `421 Invalid Host header`). After successful deployment, **automatically** open an SSH tunnel to access it locally.

**The skill will automatically execute the tunnel command.** If you need to open it manually:

**On Linux/Mac:**
```bash
ssh -i $SSH_KEY -L 9090:localhost:9090 -N ubuntu@$VM_IP &
```

**On Windows (PowerShell):**
```powershell
Start-Process -FilePath "ssh" -ArgumentList "-i $env:USERPROFILE\.ssh\id_ed25519 -L 9090:localhost:9090 -N ubuntu@$VM_IP" -WindowStyle Hidden
```

> **Note**: Keep this terminal open or run in background. Each machine that needs access must open its own tunnel.

---

**After successful deployment completion, the skill will automatically execute:**

**Linux/Mac:**
```bash
ssh -i $SSH_KEY -L 9090:localhost:9090 -f -N ubuntu@$VM_IP
```

**Windows:**
```powershell
Start-Process -FilePath "ssh" -ArgumentList "-i $env:USERPROFILE\.ssh\id_ed25519 -L 9090:localhost:9090 -N ubuntu@$VM_IP" -WindowStyle Hidden
```

## Smoke Tests

Run comprehensive tests for all MCP tools using the existing test scripts:

### Test 1: rag_get_stats
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.test_stats"
```

### Test 2: rag_ingest_document
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.test_ingest_document"
```

### Test 3: rag_search
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.test_search"
```

### Test 4: rag_list_documents
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.test_list_documents"
```

### Test 5: rag_get_document
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.test_get_document"
```

### Test 6: rag_delete_document
```bash
# First, get a document ID to delete
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -c \"
from src.database import Database
db = Database()
db.connect()
docs = db.list_documents(limit=1)
if docs['items']:
    print(docs['items'][0]['id'])
db.close()
\""

# Then delete it (replace <document_id> with the actual ID)
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -c \"
from src.database import Database
db = Database()
db.connect()
result = db.delete_document(<document_id>)
print(f'Deleted: {result}')
db.close()
\""
```

### Test 7: rag_get_stats (Final State)
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.test_stats"
```

### Test 8: rag://config Resource
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -c \"
from src.config import settings
import json
config = {
    'embedding_model': settings.embedding_model,
    'embedding_dim': settings.embedding_dim,
    'reranker_model': settings.reranker_model,
    'chunk_size': settings.chunk_size,
    'chunk_overlap': settings.chunk_overlap,
    'retrieval_top_k': settings.retrieval_top_k,
    'rerank_top_k': settings.rerank_top_k,
    'vector_weight': settings.vector_weight,
    'keyword_weight': settings.keyword_weight,
    'cache_ttl_seconds': settings.cache_ttl_seconds,
}
print(json.dumps(config, indent=2))
\""
```

### Full Pipeline Smoke Test (Recommended)
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose exec hermes python -m scripts.smoke_test"
```

This comprehensive test:
1. Ingests a test document (LEP)
2. Tests embedding generation
3. Tests vector search
4. Tests hybrid search with reranking
5. Verifies statistics
6. Cleans up test data

---

## Automatic SSH Tunnel (Post-Deploy)

After successful deployment completion, the skill **automatically** executes the SSH tunnel command:

### Linux/Mac - Auto Open
```bash
ssh -i $SSH_KEY -L 9090:localhost:9090 -f -N ubuntu@$VM_IP
```

### Windows - Auto Open
```powershell
Start-Process -FilePath "ssh" -ArgumentList "-i $env:USERPROFILE\.ssh\id_ed25519 -L 9090:localhost:9090 -N ubuntu@$VM_IP" -WindowStyle Hidden
```

### Tunnel Status Verification

After the tunnel is opened (automatically or manually), verify it's working:

**Linux/Mac:**
```bash
# Check if port 9090 is listening
ss -tlnp | grep 9090
# or
lsof -i :9090
```

**Windows:**
```powershell
netstat -ano | findstr :9090
```

**Remote server check:**
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "ss -tlnp | grep 9090"
```

If the tunnel is active, you should see output indicating port 9090 is listening.

### Stop Tunnel Command

If you need to stop the tunnel:

**Linux/Mac:**
```bash
# Kill by process match
pkill -f "ssh.*-L 9090"

# Or kill specific PID
pkill -f "ssh.*ubuntu@$VM_IP"
```

**Windows (PowerShell):**
```powershell
# Find and kill ssh process
Get-Process -Name ssh | Stop-Process -Force

# Or by port
netstat -ano | findstr :9090
taskkill /F /PID <PID>
```

**Windows (CMD):**
```cmd
taskkill /F /IM ssh.exe
```

---

## Performance Characteristics

Understanding latency helps with troubleshooting:

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
# MCP Server logs
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose logs -f hermes"

# All services
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose logs -f"

# Last 100 lines
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose logs --tail 100 hermes"
```

### Restart Services

```bash
# Restart all
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose restart"

# Restart only Hermes
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose restart hermes"

# Full rebuild and restart
ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && docker compose build hermes && docker compose up -d hermes"
```

### Health Check

```bash
# Run health check script
ssh -i $SSH_KEY ubuntu@$VM_IP "chmod +x scripts/health_check.sh && ./scripts/health_check.sh"

# Or use Docker stats
ssh -i $SSH_KEY ubuntu@$VM_IP "docker stats --no-stream"

# System resources
ssh -i $SSH_KEY ubuntu@$VM_IP "free -h"
ssh -i $SSH_KEY ubuntu@$VM_IP "df -h /"
```

### Database Operations

```bash
# Test database connection
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose run --rm hermes python -m scripts.test_connection"

# Initialize/update schema
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose run --rm hermes python -m scripts.init_db"

# Warm up ML models
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose run --rm hermes python -m scripts.warmup_models"
```

### Ingest Documents

**Via MCP tool** (recomendado, com SSH tunnel ativo):

Após transferir arquivos via SCP para `~/docs/` na VM, usar a tool `rag_ingest_file`:
```text
rag_ingest_file(path="/data/document.pdf", title="Document Title", doc_type="legislacao")
rag_ingest_file(path="/data/", doc_type="legislacao")  # diretório inteiro
```

**Via SSH + script CLI** (alternativa):

```bash
# Single file
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.ingest_file /data/document.txt --title 'Document Title' --type legislacao"

# Directory
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.ingest_file /data/ --type legislacao"
```

## Troubleshooting

### Connection Issues

If the MCP endpoint is not accessible:
1. Verify Security List allows port 9090 in Oracle Cloud Console
2. Check firewall: `ssh -i $SSH_KEY ubuntu@$VM_IP "sudo iptables -L -n | grep 9090"`
3. Ensure container is listening: `ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose logs hermes | grep 9090"`

### Database Connection

If Oracle connection fails:
1. Verify wallet is in correct location
2. Check DSN in .env is correct
3. Ensure Autonomous Database is running (not stopped)
4. Test connection: `ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose run --rm hermes python -m scripts.test_connection"`

### Performance Issues

If embedding is slow (>500ms):
- Check CPU usage: `ssh -i $SSH_KEY ubuntu@$VM_IP "docker stats --no-stream hermes"`
- Increase CPU limits in docker-compose.yml
- This is normal for first call (cold start)

### Model Download Issues

If models fail to download:
- Run warmup script: `ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose run --rm hermes python -m scripts.warmup_models"`
- Check network connectivity from container

### MCP Tools Not Working

If a specific MCP tool fails:
1. Check logs: `ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose logs hermes | grep -A 10 'error'"`
2. Run individual tool test from the smoke tests above
3. Verify database connectivity
4. Check if models are loaded: `ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose logs hermes | grep 'Modelos'"`

## MCP Inspector

The MCP Inspector is a web-based interface for interactively testing MCP tools. It provides a visual way to call tools and see responses.

### Using the MCP Inspector Script

The project includes an automated script that:

1. Kills old Inspector processes on the VM (`pkill -9 node`) to free ports 6274/6277
2. Starts the Inspector on the VM in background via `nohup` + `< /dev/null` (prevents SSH from blocking)
3. Polls the VM log to capture the auth token automatically
4. Frees local ports if occupied (Windows: `netstat -ano` + `taskkill`)
5. Opens a local SSH tunnel (`-L 6274:localhost:6274 -L 6277:localhost:6277 -N`)
6. Opens the browser with query params that pre-configure `streamable-http` transport

Run the script from your local machine:
```bash
bash scripts/mcp-inspector.sh
```

The browser URL includes transport configuration via query params:
```text
http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>&transport=streamable-http&serverUrl=http://localhost:9090/mcp
```

The script uses these default values:
- SSH Host: ubuntu@$VM_IP
- SSH Key: $HOME/.ssh/id_ed25519
- MCP URL: http://localhost:9090/mcp
- Inspector ports: 6274 (web UI), 6277 (proxy server)

### Manual MCP Inspector Setup

If you need to run the Inspector manually:

**Step 1: Kill old Inspector and start fresh on VM**
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP
pkill -9 node 2>/dev/null; true
npx @modelcontextprotocol/inspector http://localhost:9090/mcp
```

**Step 2: Get Auth Token**
The Inspector will output a URL with a token, e.g.:
```text
MCP Inspector is up and running at:
   http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>
```

**Step 3: Create SSH Tunnel**
```bash
ssh -i $SSH_KEY -L 6274:localhost:6274 -L 6277:localhost:6277 -N ubuntu@$VM_IP
```

**Step 4: Open Browser (with transport pre-configured)**
Navigate to:
```text
http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>&transport=streamable-http&serverUrl=http://localhost:9090/mcp
```

> **Important**: The server URL must be `http://localhost:9090/mcp` (not the public IP). The proxy runs on the same VM as the MCP server, so localhost works. The query params `transport=streamable-http&serverUrl=...` pre-configure the Inspector UI automatically.

### What to Test with Inspector

Use the Inspector to:
- View all 7 available tools
- Call `rag_get_stats` to verify database state
- Test `rag_search` with real queries
- Verify `rag_ingest_document` responses
- Explore tool parameters interactively

## Quick Reference

| Task | Command |
|------|---------|
| Deploy | `ssh -i $SSH_KEY ubuntu@$VM_IP "cd ~/HermesContext && git pull && docker compose build hermes && docker compose up -d"` |
| Check status | `ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose ps"` |
| View logs | `ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose logs --tail 20 hermes"` |
| Test endpoint | `ssh -i $SSH_KEY ubuntu@$VM_IP "curl -X POST http://localhost:9090/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-03-26\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1.0\"}}}'"` |
| Restart | `ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose restart hermes"` |
| Smoke test | `ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.smoke_test"` |
| Get stats | `ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.test_stats"` |
| MCP Inspector | `bash scripts/mcp-inspector.sh` |
| **Tunnel (Auto)** | **Automatically opened after successful deploy** |
| Tunnel status | `netstat -ano | findstr :9090` (Windows) / `ss -tlnp | grep 9090` (Linux) |
| Tunnel stop | `taskkill /F /IM ssh.exe` (Windows) / `pkill -f "ssh.*-L 9090"` (Linux) |

## SSH Tunnel Management

The MCP server is not directly accessible via the public IP (returns `421 Invalid Host header`). An SSH tunnel is required to access it from external machines.

### Tunnel Commands

#### Start Tunnel

**Linux/Mac:**
```bash
# In background (recommended)
ssh -i $SSH_KEY -L 9090:localhost:9090 -N ubuntu@$VM_IP &

# Or with nohup for persistence
nohup ssh -i $SSH_KEY -L 9090:localhost:9090 -N ubuntu@$VM_IP > /dev/null 2>&1 &
```

**Windows (PowerShell):**
```powershell
Start-Process -FilePath "ssh" -ArgumentList "-i $SSH_KEY -L 9090:localhost:9090 -N ubuntu@$VM_IP" -WindowStyle Hidden
```

**Windows (CMD):**
```cmd
start /B ssh -i %SSH_KEY% -L 9090:localhost:9090 -N ubuntu@%VM_IP%
```

#### Check Tunnel Status

**Local machine:**
```bash
# Linux/Mac
ss -tlnp | grep 9090
# or
lsof -i :9090

# Windows
netstat -ano | findstr :9090
```

**Remote server:**
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP "ss -tlnp | grep 9090"
```

#### Stop Tunnel

**Linux/Mac:**
```bash
# Kill by process
pkill -f "ssh.*-L 9090"

# Or kill specific PID
pkill -f "ssh.*ubuntu@$VM_IP"
```

**Windows:**
```powershell
# Find and kill ssh process
Get-Process -Name ssh | Stop-Process -Force

# Or by port
netstat -ano | findstr :9090
taskkill /F /PID <PID>
```

**CMD:**
```cmd
taskkill /F /IM ssh.exe
```

### Tunnel Automation Script

Create a local script `tunnel.sh` for easier tunnel management:

```bash
#!/bin/bash

VM_IP="${VM_IP:-147.15.91.57}"
SSH_KEY="${SSH_KEY:-~/.ssh/id_ed25519}"

case "$1" in
  start)
    echo "Starting SSH tunnel to $VM_IP..."
    ssh -i "$SSH_KEY" -L 9090:localhost:9090 -N -f ubuntu@$VM_IP
    echo "Tunnel started. MCP available at http://localhost:9090/mcp"
    ;;
  stop)
    echo "Stopping SSH tunnel..."
    pkill -f "ssh.*-L 9090"
    echo "Tunnel stopped."
    ;;
  status)
    if ss -tlnp 2>/dev/null | grep -q ':9090'; then
      echo "Tunnel is ACTIVE - MCP available at http://localhost:9090/mcp"
    else
      echo "Tunnel is NOT active"
    fi
    ;;
  *)
    echo "Usage: $0 {start|stop|status}"
    exit 1
    ;;
esac
```

Make it executable and use it:
```bash
chmod +x tunnel.sh
./tunnel.sh start   # Start tunnel
./tunnel.sh status  # Check status
./tunnel.sh stop    # Stop tunnel
```

### Important Notes

- **Keep terminal open**: The tunnel command (`-N`) doesn't open a shell, but the process must remain running
- **Background execution**: Use `&` (Linux/Mac) or `Start-Process` (Windows) to run in background
- **Multiple machines**: Each machine that needs access must open its own tunnel
- **Port conflicts**: If port 9090 is in use locally, use a different local port: `-L 9091:localhost:9090`
- **Reconnection**: If the tunnel drops, reconnect automatically with: `while true; do ssh -L 9090:localhost:9090 -N ubuntu@$VM_IP; sleep 5; done`

## Additional Resources

For complete deployment documentation including initial Oracle Cloud setup, VM provisioning, and database configuration, refer to:
- `DEPLOY_GUIDE.md` - Complete deployment guide with all phases
- `MCP_SETUP.md` - MCP server connection setup (SSH tunnel + Claude Code)
- `ARCHITECTURE.md` - System architecture details
- `scripts/mcp-inspector.sh` - Interactive MCP tool testing via browser
- `src/server.py` - MCP server implementation with all tools
