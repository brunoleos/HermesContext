Execute o workflow de deploy, ingest de documentos, manutenção ou diagnóstico do HermesContext MCP Server na Oracle Cloud.

## Variáveis de ambiente obrigatórias

Antes de executar qualquer comando, verifique se as variáveis estão definidas no ambiente atual:
- `VM_IP` — IP da VM Oracle Cloud (padrão: `147.15.91.57`)
- `SSH_KEY` — caminho da chave SSH (padrão: `~/.ssh/id_ed25519`)

Se não estiverem definidas, use os valores padrão hardcoded.

## Workflow de Deploy Completo

Execute as etapas a seguir em ordem. Pare e informe o usuário se qualquer etapa falhar.

### Etapa 1 — Verificar conectividade SSH
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "uname -a"
```
Resultado esperado: linha com informações do kernel Linux. Se falhar, verifique IP e chave SSH.

### Etapa 2 — Pull do código mais recente
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && git pull"
```

### Etapa 3 — Build da imagem Docker
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose build hermes"
```
Aguardar conclusão. Primeira execução pode levar 10-20 minutos.

### Etapa 4 — Subir serviços
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose up -d"
```

### Etapa 5 — Verificar containers
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose ps"
```
Resultado esperado: containers `hermes` e `redis` com status `Up`.

### Etapa 6 — Verificar logs de startup
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose logs --tail 20 hermes"
```
Resultado esperado: linha contendo `INFO: Uvicorn running on http://0.0.0.0:9090`.

### Etapa 7 — Testar endpoint MCP
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "curl -s -X POST http://localhost:9090/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-03-26\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1.0\"}}}'"
```
Resultado esperado: JSON contendo `serverInfo` e `capabilities`.

### Etapa 8 — Abrir túnel SSH (automático, Windows)

Execute via PowerShell (Start-Process não bloqueia):
```powershell
Start-Process -FilePath "ssh" -ArgumentList "-i $env:USERPROFILE\.ssh\id_ed25519 -L 9090:localhost:9090 -N ubuntu@147.15.91.57" -WindowStyle Hidden
```

Verificar se o túnel está ativo:
```bash
netstat -ano | findstr :9090
```
Se port 9090 aparecer como LISTENING, o MCP server está acessível em `http://localhost:9090/mcp`.

---

## Workflow de Ingest de Documentos

Use este workflow para indexar novos documentos na base de conhecimento RAG.
**Pré-requisito**: túnel SSH ativo na porta 9090.

### Etapa 1 — Verificar túnel ativo
```bash
netstat -ano | findstr :9090
```
Se não estiver ativo, executar Etapa 8 do deploy acima antes de continuar.

### Etapa 2 — Transferir arquivo para a VM via SCP
```bash
# Arquivo único
scp -i ~/.ssh/id_ed25519 /caminho/local/documento.pdf ubuntu@147.15.91.57:~/docs/

# Múltiplos arquivos
scp -i ~/.ssh/id_ed25519 /caminho/local/*.pdf ubuntu@147.15.91.57:~/docs/

# Diretório inteiro
scp -i ~/.ssh/id_ed25519 -r /caminho/local/pasta/ ubuntu@147.15.91.57:~/docs/
```

Verificar que o arquivo chegou:
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "ls -la ~/docs/"
```

### Etapa 3 — Ingerir via tool MCP `rag_ingest_file`

Com o túnel ativo e o arquivo em `~/docs/` na VM (mapeado para `/data/` no container), chamar a tool:

```
rag_ingest_file(path="/data/documento.pdf", title="Título do Documento", doc_type="legislacao")
```

Para diretório inteiro:
```
rag_ingest_file(path="/data/", doc_type="legislacao")
```

Formatos suportados: `.txt`, `.md`, `.csv`, `.json`, `.pdf`

### Etapa 4 — Verificar resultado

A tool retorna `document_id`, `chunk_count` e `elapsed_ms`. Confirmar com:
```
rag_get_stats()
```
ou
```
rag_list_documents(limit=5)
```

### Alternativa: Ingest via CLI (sem túnel ativo)
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose exec hermes python -m scripts.ingest_file /data/documento.pdf --title 'Título' --type legislacao"
```

---

## Operações de Manutenção

Use estes comandos para tarefas específicas sem executar o deploy completo.

### Health Check
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose ps && docker stats --no-stream"
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "free -h && df -h /"
```

### Ver Logs
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose logs --tail 100 hermes"
```

### Restart do Hermes
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose restart hermes"
```

### Smoke Test
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose exec hermes python -m scripts.smoke_test"
```

### Testar Conexão com Banco
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose run --rm hermes python -m scripts.test_connection"
```

---

## Diagnóstico de Falhas

### MCP não responde localmente
1. Verificar túnel SSH: `netstat -ano | findstr :9090`
2. Se não estiver ativo, abrir túnel (Etapa 8)
3. Testar endpoint diretamente na VM (Etapa 7)

### Ingest falha com erro de path
- Confirmar que o arquivo está em `~/docs/` na VM: `ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "ls ~/docs/"`
- O path na tool deve começar com `/data/` (não `~/docs/`)

### Container não sobe
1. Verificar logs: `ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose logs hermes"`
2. Verificar banco de dados Oracle (deve estar Running no console Oracle Cloud)
3. Verificar wallet: `ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "ls -la ~/wallet/"`

### Erro de banco de dados
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose run --rm hermes python -m scripts.test_connection"
```

### Modelos não carregam
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose run --rm hermes python -m scripts.warmup_models"
```
