# Configuração do MCP Server no Claude Code

O servidor MCP roda na VM Oracle (`147.15.91.57:9090`). Para acessá-lo localmente, é necessário um **SSH tunnel**.

## Pré-requisito: Abrir o SSH Tunnel

Abra um terminal separado e mantenha o túnel ativo:

```bash
ssh -i ~/.ssh/id_ed25519 -L 9090:localhost:9090 -N ubuntu@147.15.91.57
```

O MCP Server ficará acessível em `http://localhost:9090/mcp` enquanto o túnel estiver aberto.

> Para testar os tools interativamente via browser, use o MCP Inspector:
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

Com o túnel ativo, os 6 tools estarão disponíveis em todas as conversas deste projeto:

- `rag_search` — busca híbrida (vetor + full-text) com reranking
- `rag_ingest_document` — ingerir documento (aceita texto raw, ideal para documentos pequenos)
- `rag_list_documents` — listar documentos indexados
- `rag_get_document` — obter documento por ID
- `rag_get_stats` — estatísticas (total docs, chunks, embeddings)
- `rag_delete_document` — deletar documento pelo ID

> **Nota:** As MCP tools são para **consulta e gestão** de documentos já indexados. Para **ingerir arquivos grandes** (PDFs, pastas inteiras), use o workflow de ingestão via SSH (ver seção "Workflows" no [README.md](README.md)).
