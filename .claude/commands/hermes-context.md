Execute o workflow de deploy, ingest de documentos, manutenção ou diagnóstico do HermesContext MCP Server na Oracle Cloud.

## Detecção de Ambiente

Antes de executar qualquer comando, determine se está rodando **localmente na VM** ou **remotamente**:

```bash
test -d ~/HermesContext && echo "LOCAL" || echo "REMOTO"
```

- **Local (na VM)**: Execute comandos diretamente. Não é necessário SSH, túnel ou SCP.
- **Remoto (via SSH)**: Use `ssh -i $SSH_KEY ubuntu@$VM_IP "..."` para envolver os comandos.

## Variáveis de ambiente (apenas remoto)

Necessárias apenas quando acessando remotamente via SSH:
- `VM_IP` — IP da VM Oracle Cloud (padrão: `147.15.91.57`)
- `SSH_KEY` — caminho da chave SSH (padrão: `~/.ssh/id_ed25519`)

Se não estiverem definidas, use os valores padrão hardcoded.

## Workflow de Deploy Completo

Execute as etapas a seguir em ordem. Pare e informe o usuário se qualquer etapa falhar.

### Etapa 1 — Verificar conectividade

**Local (na VM):**
```bash
uname -a
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "uname -a"
```
Resultado esperado: linha com informações do kernel Linux. Se falhar, verifique IP e chave SSH.

### Etapa 2 — Pull do código mais recente

**Local (na VM):**
```bash
cd ~/HermesContext && git pull
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && git pull"
```

### Etapa 3 — Build da imagem Docker

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose build hermes
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose build hermes"
```
Aguardar conclusão. Primeira execução pode levar 10-20 minutos.

### Etapa 4 — Subir serviços

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose up -d
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose up -d"
```

### Etapa 5 — Verificar containers

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose ps
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose ps"
```
Resultado esperado: containers `hermes` e `redis` com status `Up`.

### Etapa 6 — Verificar logs de startup

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose logs --tail 20 hermes
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose logs --tail 20 hermes"
```
Resultado esperado: linha contendo `INFO: Uvicorn running on http://0.0.0.0:9090`.

### Etapa 7 — Testar endpoint MCP

**Local (na VM):**
```bash
curl -s -X POST http://localhost:9090/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "curl -s -X POST http://localhost:9090/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -d '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-03-26\",\"capabilities\":{},\"clientInfo\":{\"name\":\"test\",\"version\":\"1.0\"}}}'"
```
Resultado esperado: JSON contendo `serverInfo` e `capabilities`.

### Etapa 8 — Abrir túnel SSH

> **Apenas remoto** — quando local, o MCP server já está acessível em `http://localhost:9090/mcp`. Pule esta etapa.

Execute via PowerShell (Start-Process não bloqueia):
```powershell
Start-Process -FilePath "ssh" -ArgumentList "-i $env:USERPROFILE\.ssh\id_ed25519 -L 9090:localhost:9090 -N ubuntu@147.15.91.57" -WindowStyle Hidden
```

Linux/Mac:
```bash
ssh -i ~/.ssh/id_ed25519 -L 9090:localhost:9090 -f -N ubuntu@147.15.91.57
```

Verificar se o túnel está ativo:
- Windows: `netstat -ano | findstr :9090`
- Linux/Mac: `ss -tlnp | grep 9090`

Se port 9090 aparecer como LISTENING, o MCP server está acessível em `http://localhost:9090/mcp`.

---

## Workflow de Ingest de Documentos

Use este workflow para indexar novos documentos na base de conhecimento RAG.

### Pré-requisito: Verificar acesso ao MCP

**Local (na VM):**
O MCP server está acessível diretamente em `http://localhost:9090/mcp`. Nenhum túnel necessário.

**Remoto (via SSH):**
Verificar túnel ativo:
```bash
netstat -ano | findstr :9090
```
Se não estiver ativo, executar Etapa 8 do deploy acima antes de continuar.

### Etapa 1 — Transferir arquivo

**Local (na VM):**
O arquivo já está na VM. Copie para `~/docs/` (mapeado para `/data/` no container):
```bash
cp /caminho/do/documento.pdf ~/docs/

# Verificar
ls -la ~/docs/
```

**Remoto (via SSH):**
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

### Etapa 2 — Ingerir via tool MCP `rag_ingest_file`

Com o MCP server acessível e o arquivo em `~/docs/` na VM (mapeado para `/data/` no container), chamar a tool:

```
rag_ingest_file(path="/data/documento.pdf", title="Título do Documento", doc_type="legislacao")
```

Para diretório inteiro:
```
rag_ingest_file(path="/data/", doc_type="legislacao")
```

Formatos suportados: `.txt`, `.md`, `.csv`, `.json`, `.pdf`

### Etapa 3 — Acompanhar progresso

A tool `rag_ingest_file` é **assíncrona** — retorna um `job_id` imediatamente. Acompanhar com:
```
rag_get_ingest_status(job_id="<job_id>")
```
O retorno inclui barra de progresso ASCII e tempo decorrido.

### Etapa 4 — Verificar resultado

Confirmar com:
```
rag_get_stats()
```
ou
```
rag_list_documents(limit=5)
```

### Alternativa: Ingest via CLI (sem tool MCP)

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose exec hermes python -m scripts.ingest_file /data/documento.pdf --title 'Título' --type legislacao
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose exec hermes python -m scripts.ingest_file /data/documento.pdf --title 'Título' --type legislacao"
```

---

## Operações de Manutenção

Use estes comandos para tarefas específicas sem executar o deploy completo.

### Health Check

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose ps && docker stats --no-stream
free -h && df -h /
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose ps && docker stats --no-stream"
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "free -h && df -h /"
```

### Ver Logs

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose logs --tail 100 hermes
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose logs --tail 100 hermes"
```

### Restart do Hermes

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose restart hermes
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose restart hermes"
```

### Smoke Test

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose exec hermes python -m scripts.smoke_test
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose exec hermes python -m scripts.smoke_test"
```

### Testar Conexão com Banco

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose run --rm hermes python -m scripts.test_connection
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose run --rm hermes python -m scripts.test_connection"
```

---

## Diagnóstico de Falhas

### MCP não responde

**Local (na VM):**
1. Verificar container: `cd ~/HermesContext && docker compose ps`
2. Verificar logs: `cd ~/HermesContext && docker compose logs hermes | grep 9090`
3. Testar endpoint: `curl -s http://localhost:9090/mcp`

**Remoto (via SSH):**
1. Verificar túnel SSH: `netstat -ano | findstr :9090` (Windows) / `ss -tlnp | grep 9090` (Linux)
2. Se não estiver ativo, abrir túnel (Etapa 8)
3. Testar endpoint diretamente na VM (Etapa 7)

### Ingest falha com erro de path
- Confirmar que o arquivo está em `~/docs/` na VM
  - **Local**: `ls ~/docs/`
  - **Remoto**: `ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "ls ~/docs/"`
- O path na tool deve começar com `/data/` (não `~/docs/`)

### Container não sobe

**Local (na VM):**
1. Verificar logs: `cd ~/HermesContext && docker compose logs hermes`
2. Verificar banco de dados Oracle (deve estar Running no console Oracle Cloud)
3. Verificar wallet: `ls -la ~/wallet/`

**Remoto (via SSH):**
1. Verificar logs: `ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose logs hermes"`
2. Verificar banco de dados Oracle (deve estar Running no console Oracle Cloud)
3. Verificar wallet: `ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "ls -la ~/wallet/"`

### Erro de banco de dados

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose run --rm hermes python -m scripts.test_connection
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose run --rm hermes python -m scripts.test_connection"
```

### Modelos não carregam

**Local (na VM):**
```bash
cd ~/HermesContext && docker compose run --rm hermes python -m scripts.warmup_models
```

**Remoto (via SSH):**
```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@147.15.91.57 "cd ~/HermesContext && docker compose run --rm hermes python -m scripts.warmup_models"
```
