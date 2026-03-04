# Configuração do MCP Server no Claude Code

O servidor MCP roda na VM Oracle (`147.15.91.57:9090`). Para acessá-lo localmente, é necessário um **SSH tunnel**.

## Build: Produção vs Desenvolvimento

O projeto oferece dois modos de build (ver [README.md](README.md)):

- **Produção**: `docker compose up -d` (pré-baixa modelos, código em imagem)
- **Desenvolvimento**: `docker compose -f docker-compose.dev.yml up -d` (hot reload, volumes de código)

## Pré-requisito: Abrir o SSH Tunnel

Abra um terminal separado e mantenha o túnel ativo:

```bash
ssh -i ~/.ssh/id_ed25519 -L 9090:localhost:9090 -N ubuntu@147.15.91.57
```

O MCP Server ficará acessível em `http://localhost:9090/mcp` enquanto o túnel estiver aberto.

> Para testar os tools interativamente via browser, use o MCP Inspector:
>
> ```bash
> bash scripts/mcp-inspector.sh
> ```

## Configuração (já aplicada)

O servidor MCP já está registrado no Claude Code (`~/.claude.json`) apontando para `http://localhost:9090/mcp`.

Para verificar:

```bash
claude mcp list
# Esperado: rag: http://localhost:9090/mcp (HTTP) - ✓ Connected
```

## Tools Disponíveis

Com o túnel ativo, os 7 tools estarão disponíveis em todas as conversas deste projeto:

- `rag_search` — busca híbrida (vetor + full-text) com reranking
- `rag_ingest_document` — ingerir documento (aceita texto raw, ideal para documentos pequenos)
- `rag_ingest_file` — ingerir arquivo já na VM em `/data/` (suporta PDF, TXT, MD, CSV, JSON; aceita arquivo ou diretório)
- `rag_list_documents` — listar documentos indexados
- `rag_get_document` — obter documento por ID
- `rag_get_stats` — estatísticas (total docs, chunks, embeddings)
- `rag_delete_document` — deletar documento pelo ID

> **Nota:** Para ingerir arquivos grandes (PDFs, pastas inteiras), use `rag_ingest_file` após transferir via SCP.
> Ver seção "Workflows" no [README.md](README.md).
