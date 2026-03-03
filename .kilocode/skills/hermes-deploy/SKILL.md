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

The HermesContext MCP Server exposes 6 tools:

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

### 3. rag_list_documents
**Purpose**: List indexed documents with pagination
- **Parameters**: limit (1-100), offset, doc_type (filter), response_format
- **Returns**: List of documents with ID, title, type, chunk_count, created_at
- **Typical latency**: <100ms

### 4. rag_get_document
**Purpose**: Get details of a specific document by ID
- **Parameters**: document_id, response_format
- **Returns**: Title, source, type, metadata, chunk_count, created_at
- **Typical latency**: <100ms

### 5. rag_delete_document
**Purpose**: Delete a document and all its chunks
- ⚠️ Irreversible action
- **Parameters**: document_id
- **Returns**: Confirmation message
- **Typical latency**: <500ms

### 6. rag_get_stats
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

## Performance Characteristics

Understanding latency helps with troubleshooting:

| Operation | First Call (Cold) | Subsequent Calls (Warm) |
|-----------|-------------------|------------------------|
| rag_ingest_document | ~10-12 seconds | ~500ms |
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

```bash
# Single file
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.ingest_file /data/document.txt --title 'Document Title' --type legislacao"

# Directory
ssh -i $SSH_KEY ubuntu@$VM_IP "docker compose exec hermes python -m scripts.ingest_file /docs/ --type legislacao"
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
1. Restarts the Inspector on the VM (kills previous processes on ports 6274/6277)
2. Captures the auth token from logs
3. Opens a local SSH tunnel
4. Opens the browser with the full URL

Run the script from your local machine:
```bash
bash scripts/mcp-inspector.sh
```

The script uses these default values:
- SSH Host: ubuntu@$VM_IP
- SSH Key: $HOME/.ssh/id_ed25519
- MCP URL: http://localhost:9090/mcp
- Inspector ports: 6274 (web), 6277 (proxy)

### Manual MCP Inspector Setup

If you need to run the Inspector manually:

**Step 1: Start Inspector on VM**
```bash
ssh -i $SSH_KEY ubuntu@$VM_IP
pkill -f '@modelcontextprotocol/inspector' 2>/dev/null || true
npx @modelcontextprotocol/inspector http://localhost:9090/mcp
```

**Step 2: Get Auth Token**
The Inspector will output a URL with a token, e.g.:
```
MCP Inspector is up and running at:
   http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>
```

**Step 3: Create SSH Tunnel**
```bash
ssh -i $SSH_KEY -L 6274:localhost:6274 -L 6277:localhost:6277 -N ubuntu@$VM_IP
```

**Step 4: Open Browser**
Navigate to:
```
http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>
```

> **Important**: In the Inspector interface, the server URL should be `http://localhost:9090/mcp` (not the public IP). The proxy runs on the same VM as the MCP server, so localhost works.

### What to Test with Inspector

Use the Inspector to:
- View all 6 available tools
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

## Additional Resources

For complete deployment documentation including initial Oracle Cloud setup, VM provisioning, and database configuration, refer to:
- `DEPLOY_GUIDE.md` - Complete deployment guide with all phases
- `ARCHITECTURE.md` - System architecture details
- `scripts/` - Utility scripts for deployment and maintenance
- `src/server.py` - MCP server implementation with all tools
