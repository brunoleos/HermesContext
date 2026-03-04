# Guia de Deploy — HermesContext no Oracle Cloud Always Free

Passo a passo completo: do zero ao MCP Server funcionando em `http://<vm-ip>:9090/mcp`.

> **Testado em**: Fev/2026 — Oracle Cloud sa-saopaulo-1, Ubuntu 24.04 aarch64, Docker 27.x, Python 3.12.

---

## Pré-requisitos

- Conta Oracle Cloud (cadastro em [cloud.oracle.com](https://cloud.oracle.com))
- Terminal SSH (PuTTY no Windows, ou terminal nativo Linux/Mac)
- Chave SSH gerada (`ssh-keygen -t ed25519`)

---

## Fase 1 — Provisionamento Oracle Cloud (Console Web)

Tudo nesta fase é feito no console web [cloud.oracle.com](https://cloud.oracle.com).

### Passo 1.1 — Criar Compartment

1. Acesse **Identity & Security → Compartments**
2. Clique **Create Compartment**
3. Nome: `rag-ipen`
4. Descrição: `RAG MCP Server para o sistema iPEN`
5. Clique **Create**

> O compartment isola seus recursos. Todos os próximos passos usam este compartment.

### Passo 1.2 — Criar VCN (Virtual Cloud Network)

1. Acesse **Networking → Virtual Cloud Networks**
2. Clique **Start VCN Wizard → Create VCN with Internet Connectivity**
3. Configure:
   - Nome: `vcn-rag`
   - Compartment: `rag-ipen`
   - CIDR Block: `10.0.0.0/16` (default)
4. Clique **Next → Create**
5. Aguarde finalizar (~30 segundos)

### Passo 1.3 — Abrir porta 9090 na Security List

1. Dentro da VCN criada, clique na **Public Subnet**
2. Clique na **Default Security List**
3. **Add Ingress Rules**:

| Source CIDR | Protocol | Dest Port | Descrição |
|-------------|----------|-----------|-----------|
| `0.0.0.0/0` | TCP | `22` | SSH (já existe por default) |
| `0.0.0.0/0` | TCP | `9090` | MCP Server endpoint |

4. Clique **Add Ingress Rules**

> ⚠️ Em produção, restrinja o Source CIDR da porta 9090 aos IPs que precisam acessar o MCP server (ex: IP fixo da sua LLM, VPN corporativa, etc.).

### Passo 1.4 — Criar VM ARM (Ampere A1)

1. Acesse **Compute → Instances → Create Instance**
2. Configure:
   - **Nome**: `vm-rag-arm`
   - **Compartment**: `rag-ipen`
   - **Placement**: qualquer AD disponível
   - **Image**: Ubuntu 24.04 (Canonical)
     - Clique **Change Image → Ubuntu → 24.04 Minimal aarch64**
   - **Shape**: clique **Change Shape**
     - **Ampere** → **VM.Standard.A1.Flex**
     - OCPUs: **4**
     - Memory: **24 GB**
   - **Networking**:
     - VCN: `vcn-rag`
     - Subnet: Public Subnet
     - **Assign a public IPv4 address**: ✅ Yes
   - **SSH Key**: cole sua chave pública (`~/.ssh/id_ed25519.pub`)
   - **Boot volume**: 150 GB (máximo Always Free)
3. Clique **Create**
4. Aguarde status **RUNNING** (~2 min)
5. **Anote o IP público** (será o `<vm-ip>` em todas as URLs)

> 💡 Se a shape A1 mostrar "Out of capacity", tente outro Availability Domain ou tente novamente mais tarde (demanda flutuante). A região `sa-saopaulo-1` costuma ter boa disponibilidade.

### Passo 1.5 — Criar Autonomous Database

1. Acesse **Oracle Database → Autonomous Database**
2. Clique **Create Autonomous Database**
3. Configure:
   - **Compartment**: `rag-ipen`
   - **Display name**: `hermesdb`
   - **Database name**: `hermesdb`
   - **Workload type**: Transaction Processing (ou Data Warehouse — ambos suportam VECTOR)
   - **Deployment type**: Serverless
   - **Always Free**: ✅ **Marque esta opção**
   - **Database version**: 23ai (obrigatório para suporte a VECTOR)
   - **OCPU count**: 1 (Always Free máximo)
   - **Storage**: 20 GB (Always Free máximo)
   - **Password**: defina uma senha forte (ex: `HermesMcp2026!Seguro`)
     - **Guarde esta senha**, será usada no `.env`
   - **Network Access**: Secure access from everywhere (com mTLS via wallet)
   - **License type**: License Included
4. Clique **Create Autonomous Database**
5. Aguarde status **Available** (~3 min)

### Passo 1.6 — Baixar o Wallet (credenciais mTLS)

1. Na página do Autonomous DB (`hermesdb`), clique **DB Connection**
2. Clique **Download Wallet**
3. Defina um password para o wallet (pode ser o mesmo da senha do DB)
4. Salve o arquivo `Wallet_hermesdb.zip`
5. **Não descompacte no seu PC** — será enviado direto para a VM

### Passo 1.7 — Obter a Connection String (DSN)

1. Ainda em **DB Connection**, na seção **Connection Strings**
2. Selecione **TLS Authentication: Mutual TLS**
3. Copie a connection string **`hermesdb_low`** (perfil de baixo consumo, ideal para Always Free)
4. O formato será algo como:

```
(description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1522)(host=adb.sa-saopaulo-1.oraclecloud.com))(connect_data=(service_name=xxxxxxxxxxxx_hermesdb_low.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))
```

5. **Anote esta string** — será o valor de `ORACLE_DSN` no `.env`

---

## Fase 2 — Configuração da VM (SSH)

A partir daqui, tudo é feito via SSH na VM criada.

### Passo 2.1 — Conectar via SSH

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@<vm-ip>
```

### Passo 2.2 — Atualizar sistema e instalar dependências

```bash
sudo apt update && sudo apt upgrade -y

# Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Docker Compose plugin
sudo apt install -y docker-compose-plugin

# Node.js (necessário para MCP Inspector)
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs

# Utilitários
sudo apt install -y git unzip redis-tools curl jq

# Reconectar para aplicar grupo docker
exit
```

```bash
ssh -i ~/.ssh/id_ed25519 ubuntu@<vm-ip>

# Verificar
docker --version
docker compose version
node --version
```

### Passo 2.3 — Upload e configuração do Wallet

No seu **PC local**, envie o wallet para a VM:

```bash
scp -i ~/.ssh/id_ed25519 Wallet_hermesdb.zip ubuntu@<vm-ip>:~/
```

Na **VM**, descompacte:

```bash
mkdir -p ~/wallet
cd ~/wallet
unzip ~/Wallet_hermesdb.zip
ls -la
# Deve conter: cwallet.sso, tnsnames.ora, sqlnet.ora, ewallet.p12, etc.
```

Ajuste o `sqlnet.ora` para apontar para o diretório correto:

```bash
sed -i 's|?/network/admin|/home/ubuntu/wallet|g' ~/wallet/sqlnet.ora

# Verificar
cat ~/wallet/sqlnet.ora
# Deve mostrar: WALLET_LOCATION = (SOURCE = (METHOD = file) (METHOD_DATA = (DIRECTORY="/home/ubuntu/wallet")))
```

### Passo 2.4 — Configurar chave SSH para o GitHub

A VM precisa de uma chave SSH própria para clonar o repositório privado `git@github.com:brunoleos/HermesContext.git`.

**Na VM**, gere uma chave Ed25519:

```bash
ssh-keygen -t ed25519 -C "vm-rag-oracle" -f ~/.ssh/id_ed25519 -N ""
```

Copie a chave pública gerada:

```bash
cat ~/.ssh/id_ed25519.pub
```

Saída será algo como:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI... vm-rag-oracle
```

**Copie essa linha inteira.** Agora vá ao GitHub no seu navegador:

1. Acesse [github.com/settings/keys](https://github.com/settings/keys)
2. Clique **New SSH key**
3. **Title**: `vm-rag-oracle`
4. **Key type**: Authentication Key
5. **Key**: cole a chave pública copiada
6. Clique **Add SSH key**

**De volta na VM**, teste a conexão:

```bash
ssh -T git@github.com
```

Na primeira vez vai perguntar sobre o fingerprint — digite `yes`. Saída esperada:

```
Hi brunoleos! You've successfully authenticated, but GitHub does not provide shell access.
```

> 💡 Alternativa: se não quiser adicionar a chave da VM à sua conta GitHub inteira, use uma **Deploy Key** (acesso somente a este repositório):
> 1. Vá em `github.com/brunoleos/HermesContext/settings/keys`
> 2. Clique **Add deploy key**
> 3. Cole a mesma chave pública
> 4. Deixe **Allow write access** desmarcado (só precisa de leitura)

### Passo 2.5 — Clonar o projeto e configurar .env

```bash
cd ~
git clone git@github.com:brunoleos/HermesContext.git
cd HermesContext

cp .env.example .env
nano .env
```

Preencha o `.env` com os valores reais:

```bash
# Valores de exemplo — substitua pelos seus
ORACLE_DSN=(description=(retry_count=20)(...o DSN completo copiado no Passo 1.7...))
ORACLE_USER=ADMIN
ORACLE_PASSWORD=HermesMcp2026!Seguro
ORACLE_WALLET_DIR=/wallet

REDIS_URL=redis://redis:6379

EMBEDDING_MODEL=BAAI/bge-m3
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2

MCP_TRANSPORT=streamable_http
MCP_HOST=0.0.0.0
MCP_PORT=9090
```

### Passo 2.6 — Verificar docker-compose.yml

O `docker-compose.yml` já vem configurado no repositório. Verifique que o caminho do wallet corresponde ao local onde você descompactou (Passo 2.3):

```bash
cat docker-compose.yml | grep wallet
```

Saída esperada:
```
      - /home/ubuntu/wallet:/wallet:ro
```

> Se o seu wallet está em outro caminho, edite a linha:
> ```bash
> nano docker-compose.yml
> # Altere /home/ubuntu/wallet para o caminho real
> ```

O `.env` já é carregado automaticamente via `env_file: .env`.

---

## Fase 3 — Build e Primeiro Boot

O projeto suporta **dois modos de build**:

### Modo Produção (padrão — recomendado para deploy)

```bash
cd ~/HermesContext
docker compose build
```

> ⏱️ Primeiro build leva **15–20 minutos** no ARM:
> - Compilação de dependências nativas
> - Download dos modelos BGE-M3 (~1.5 GB) e MiniLM (~90 MB)
> - Builds subsequentes usam cache e são rápidos (~1 min)

### Modo Desenvolvimento (opcional — para iteração local)

```bash
cd ~/HermesContext
docker compose -f docker-compose.dev.yml build
```

> ⏱️ Build muito mais rápido (~2 minutos):
> - Modelos são baixados na **primeira execução** do servidor (não no build)
> - Código é montado como volume (hot reload com `watchdog`)
> - Ideal para desenvolvimento e debug

**Diferença técnica**: O `Dockerfile` agora usa multi-stage build:
- **`production`** (padrão): `COPY src/ + COPY scripts/ + pré-download de modelos`
- **`development`**: instala `watchdog`, monta código via volume

### Passo 3.1 — Build das imagens Docker

**Para produção:**
```bash
cd ~/HermesContext
docker compose build
```

> ⚠️ **Warnings normais durante o build** (podem ser ignorados):
> - `position_ids UNEXPECTED` — chave extra no checkpoint do reranker, sem impacto
> - `unauthenticated requests to HF Hub` — download funciona sem token, apenas com rate limit menor

### Passo 3.2 — Subir somente o Redis primeiro

```bash
docker compose up -d redis
docker compose logs redis
# Deve mostrar "Ready to accept connections"
```

### Passo 3.3 — Testar conexão com Oracle DB

```bash
docker compose run --rm hermes python -m scripts.test_connection
```

Saída esperada:
```
============================================
  RAG MCP — Teste de Conexão Oracle
============================================

  DSN:    (description=(...))
  User:   ADMIN
  Wallet: /wallet

[1/4] Verificando wallet...
       ✅ cwallet.sso
       ✅ tnsnames.ora
       ✅ sqlnet.ora

[2/4] Conectando (thin mode, sem Oracle Client)...
       ✅ Conexão OK

[3/4] Versão do banco...
       Oracle Database 23ai ...

[4/4] Testando suporte a VECTOR...
       ✅ VECTOR suportado (distância teste: 1.0000)

✅ Todos os testes passaram.
```

> O driver `oracledb` usa **thin mode** (Python puro) — não precisa de Oracle Client instalado. A conexão mTLS é feita diretamente via wallet.

> ❌ Se falhar em [2/4], verifique: DSN copiado corretamente, senha sem caracteres especiais mal-escapados, wallet descompactado.
> ❌ Se falhar em [4/4], o DB precisa ser versão 23ai. Recrie selecionando a versão correta.

### Passo 3.4 — Inicializar o schema (tabelas + índices)

```bash
docker compose run --rm hermes python -m scripts.init_db
```

Saída esperada:
```
============================================
  RAG MCP — Inicialização do Oracle Autonomous DB
============================================

[1/3] Conectando ao Oracle Autonomous DB...
       ✅ Conexão estabelecida.

[2/3] Criando schema (tabelas + índices)...
       ✅ Schema criado/verificado.

[3/3] Verificando estatísticas...
       Documentos: 0
       Chunks:     0
       Tokens:     0

✅ Banco inicializado com sucesso.
```

> Este script é idempotente — pode rodar múltiplas vezes sem problemas. Cria as tabelas `documents` e `chunks`, o índice vetorial HNSW, o índice Oracle Text (full-text search) e o índice de FK.

### Passo 3.5 — Baixar modelos de ML (warmup)

```bash
docker compose run --rm hermes python -m scripts.warmup_models
```

> ⏱️ Primeiro download: **~5 minutos** (BGE-M3 ~1.5 GB + MiniLM ~90 MB).
> Downloads ficam no volume Docker `models-cache` e persistem entre rebuilds.

Saída esperada:
```
============================================
  HermesContext — Download e Warmup dos Modelos
============================================

[1/2] Baixando BGE-M3 (BAAI/bge-m3)...
       ✅ Carregado em 10.1s

       Warmup: embedding de teste...
       ✅ Dimensão: 1024, latência: 220ms

[2/2] Baixando Reranker (cross-encoder/ms-marco-MiniLM-L-6-v2)...
       ✅ Carregado em 2.0s

       Warmup: reranking de teste...
       ✅ Scores: [-11.2215, -11.0258], latência: 26ms

============================================
  ✅ Todos os modelos prontos.
  Cache em: /root/.cache (8.7 GB)
============================================
```

> **Sobre os scores do reranker**: valores negativos e próximos são normais no warmup. O cross-encoder gera scores em escala arbitrária — o que importa é a ordenação relativa, não o valor absoluto. Com textos reais os scores divergem bastante.

> **Warning `position_ids UNEXPECTED`**: inofensivo — chave extra no checkpoint que o modelo ignora.

> **Cache 8.7 GB**: `sentence-transformers` baixa pesos em FP32. Está no volume Docker `models-cache`, persiste entre restarts e rebuilds.

### Passo 3.6 — Smoke test (pipeline completo)

```bash
docker compose run --rm hermes python -m scripts.smoke_test
```

Este script:
1. Insere um documento LEP de teste
2. Faz embedding
3. Faz vector search
4. Faz busca híbrida com reranking
5. Verifica estatísticas
6. **Remove os dados de teste** (não deixa resíduo)

Saída esperada:
```
============================================
  RAG MCP — Smoke Test (pipeline completo)
============================================

[1/5] Ingestão de documento de teste...
       ✅ Doc ID: 1, Chunks: 1, 18925ms

[2/5] Teste de embedding...
       ✅ Dimensão: 1024, latência: 158ms

[3/5] Vector search...
       ✅ 1 resultados, 4ms

[4/5] Busca híbrida + reranking...
       ✅ 1 resultados de 1 candidatos, 2690ms
       Top resultado: score=-1.8263
       Preview: Lei de Execução Penal - LEP (Lei nº 7.210/1984)
Art. 112. A pena privativa de liberdade será execut...

[5/5] Estatísticas...
       Documentos: 1
       Chunks: 1

  🧹 Limpando documento de teste (ID: 1)...
       ✅ Documento de teste removido.

============================================
  ✅ SMOKE TEST PASSOU — pipeline RAG funcionando!
============================================
```

> **Latência alta na primeira execução**: a ingestão (~19s) e o reranking (~2.7s) são lentos na primeira chamada porque carregam os modelos na memória. Execuções subsequentes são muito mais rápidas (~350ms por query completa).

> **Doc ID > 1**: Se você rodou smoke tests anteriores que falharam, o ID pode ser maior que 1 (ex: 5, 6). Isso é normal — o Oracle usa sequences auto-incrementais. Se quiser limpar documentos órfãos:
> ```bash
> docker compose exec hermes python -c "
> from src.database import Database
> db = Database()
> db.connect()
> with db.get_conn() as conn:
>     cursor = conn.cursor()
>     cursor.execute('DELETE FROM documents d WHERE NOT EXISTS (SELECT 1 FROM chunks c WHERE c.document_id = d.id)')
>     print(f'Removidos: {cursor.rowcount} documentos órfãos')
> db.close()
> "
> ```

---

## Fase 4 — Subir o MCP Server

### Passo 4.1 — Iniciar todos os serviços

```bash
cd ~/HermesContext
docker compose up -d
```

> Se aparecer warning sobre orphan containers de runs anteriores:
> ```bash
> docker compose down --remove-orphans
> docker compose up -d
> ```

### Passo 4.2 — Verificar que o server está rodando

```bash
docker compose logs --tail 10 hermes
```

Saída esperada:
```
hermes-1  | INFO: Iniciando RAG MCP Server — transport=streamable_http, host=0.0.0.0, port=9090
hermes-1  | INFO: Usando streamable_http_app()
hermes-1  | INFO:     Started server process [1]
hermes-1  | INFO:     Waiting for application startup.
hermes-1  | INFO:     StreamableHTTP session manager started
hermes-1  | INFO:     Application startup complete.
hermes-1  | INFO:     Uvicorn running on http://0.0.0.0:9090 (Press CTRL+C to quit)
```

**Testar o endpoint** (na VM):

```bash
curl -X POST http://localhost:9090/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

Se retornar JSON com `serverInfo` e `capabilities`, o MCP server está funcionando.

> ⚠️ **`curl http://localhost:9090/mcp` retorna 406 "Not Acceptable"** — isso é **normal**. O protocolo MCP usa Server-Sent Events e requer headers específicos (`Accept: application/json, text/event-stream`) com método POST. Um GET simples é rejeitado por design.

### Passo 4.3 — Conectar via SSH Tunnel (RECOMENDADO)

Como o servidor MCP está em `0.0.0.0:9090` na VM, use **SSH tunnel** para acesso seguro a partir do seu PC local.

No seu **PC local**, em um terminal separado:

```bash
ssh -i ~/.ssh/id_ed25519 -L 9090:localhost:9090 -N ubuntu@147.15.91.57
```

O servidor estará disponível em: **`http://localhost:9090/mcp`**

Verifique com tunnel ativo (em outro terminal):

```bash
curl -X POST http://localhost:9090/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
```

Configure seu cliente MCP para `http://localhost:9090/mcp` (Claude Code, Claude Desktop, Python SDK, etc.).

**Vantagens:**
- ✅ Criptografia SSH automática
- ✅ Sem expor a VM diretamente na internet
- ✅ Compatível com múltiplos clientes (cada um abre seu próprio túnel)
- ✅ Simples de usar e gerenciar

### Passo 4.4 — Testar via MCP Inspector

O MCP Inspector é uma interface web para testar os tools interativamente. O projeto inclui um script automatizado que gerencia todo o workflow (VM + local).

#### Opção 1: Script automatizado (recomendado)

No seu **PC local**, execute:

```bash
bash scripts/mcp-inspector.sh
```

O script automaticamente:

1. Mata processos antigos do Inspector na VM (libera portas 6274/6277)
2. Inicia o Inspector na VM em background
3. Captura o auth token do log
4. Libera portas locais se ocupadas e abre túnel SSH
5. Abre o browser com transporte `streamable-http` pré-configurado via query params

#### Opção 2: Setup manual

**Na VM**, inicie o Inspector:

```bash
pkill -9 node 2>/dev/null; true
npx @modelcontextprotocol/inspector http://localhost:9090/mcp
```

Saída:
```
⚙️ Proxy server listening on localhost:6277
🔑 Session token: <token>
🚀 MCP Inspector is up and running at:
   http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>
```

> ⚠️ O Inspector roda na VM, mas o browser precisa rodar no seu PC. Use **SSH tunnel**.

**No seu PC local** (PowerShell ou terminal), abra um túnel SSH:

```bash
ssh -i ~/.ssh/id_ed25519 -L 6274:localhost:6274 -L 6277:localhost:6277 ubuntu@<vm-ip>
```

Agora abra no navegador do seu PC (com transporte pré-configurado):
```
http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>&transport=streamable-http&serverUrl=http://localhost:9090/mcp
```

> ⚠️ **Importante**: a URL do server deve ser `http://localhost:9090/mcp` (não o IP público). O proxy do Inspector roda na mesma VM que o MCP server, então `localhost` funciona. Usar o IP público causa erro `421 Invalid Host header`.
>
> **Dica**: os query params `transport=streamable-http&serverUrl=...` configuram o Inspector automaticamente sem precisar alterar na UI.

Na interface do Inspector você pode:
- Ver os 7 tools listados (rag_search, rag_ingest_document, etc.)
- Chamar `rag_get_stats` para verificar o estado do banco
- Testar `rag_search` com queries reais

---

## Fase 5 — Ingestão dos Documentos Reais

> A ingestão pode ser feita de duas formas:
>
> 1. **Via MCP tool `rag_ingest_file`** (recomendado) — após transferir arquivos via SCP, chamar a tool com o caminho em `/data/`
> 2. **Via SSH + script CLI** — executar `scripts/ingest_file.py` diretamente na VM

### Passo 5.1 — Preparar pasta de documentos na VM

```bash
# Na VM (uma vez)
ssh -i ~/.ssh/id_ed25519 ubuntu@<vm-ip> "mkdir -p ~/docs"
```

O `docker-compose.yml` já mapeia `~/docs` para `/data` no container:

```yaml
volumes:
  - /home/ubuntu/docs:/data:ro
```

### Passo 5.2 — Upload de documentos para a VM

No seu **PC local**:

```bash
# Arquivo único (PDF, TXT, MD, CSV, JSON)
scp -i ~/.ssh/id_ed25519 resolucao_45.pdf ubuntu@<vm-ip>:~/docs/

# Diretório inteiro
scp -ri ~/.ssh/id_ed25519 ./documentos/ ubuntu@<vm-ip>:~/docs/
```

### Passo 5.3 — Ingerir arquivo único

Na **VM** (ou via SSH do PC local):

```bash
# Texto simples
docker compose exec hermes python -m scripts.ingest_file \
    /data/resolucao_45.txt \
    --title "Resolução SAP 45/2024" \
    --type resolucao

# PDF (extraído automaticamente via PyMuPDF)
docker compose exec hermes python -m scripts.ingest_file \
    /data/resolucao_45.pdf \
    --title "Resolução SAP 45/2024" \
    --type resolucao
```

Formatos suportados: `.txt`, `.md`, `.csv`, `.json`, `.pdf`

> PDFs são parseados com PyMuPDF (`fitz`), que extrai texto página a página. O texto resultante é dividido em chunks de ~512 tokens, enriquecido com metadados e indexado com embeddings BGE-M3.

### Passo 5.4 — Ingerir diretório inteiro

```bash
docker compose exec hermes python -m scripts.ingest_file \
    /data/ \
    --type legislacao
```

Cada arquivo vira um documento separado. O título é inferido do nome do arquivo. A ingestão é sequencial com estatísticas por arquivo.

> **Alternativa via MCP tool** (com SSH tunnel ativo, ver Passo 4.3):
> Em vez dos passos 5.3/5.4, use a tool `rag_ingest_file` diretamente:
>
> ```text
> rag_ingest_file(path="/data/resolucao_45.pdf", title="Resolução SAP 45/2024", doc_type="resolucao")
> rag_ingest_file(path="/data/", doc_type="legislacao")  # diretório inteiro
> ```

### Passo 5.5 — Verificar ingestão

Via script na VM:

```bash
docker compose exec hermes python -c "
from src.database import Database
db = Database()
db.connect()
stats = db.get_stats()
print(f'Documentos: {stats[\"documents\"]}')
print(f'Chunks:     {stats[\"chunks\"]}')
print(f'Tokens:     {stats[\"total_tokens\"]:,}')
print(f'Por tipo:   {stats[\"by_type\"]}')
db.close()
"
```

Ou via MCP (com SSH tunnel ativo):

```
rag_get_stats → retorna total de documentos, chunks, tokens e distribuição por tipo
```

---

## Fase 6 — Conectar a LLM

> **Pré-requisito**: Abra o SSH tunnel antes de conectar qualquer cliente (ver Passo 4.3).
>
> ```bash
> ssh -i ~/.ssh/id_ed25519 -L 9090:localhost:9090 -N ubuntu@<vm-ip>
> ```

### Opção A: Claude Desktop

Edite `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac) ou `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "hermes": {
      "type": "url",
      "url": "http://localhost:9090/mcp"
    }
  }
}
```

Reinicie o Claude Desktop. Os 7 tools RAG aparecem na interface.

### Opção B: Claude Code (CLI)

```bash
claude mcp add hermes --transport http http://localhost:9090/mcp
```

### Opção C: Qualquer agente MCP (Python)

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client("http://localhost:9090/mcp") as (r, w, _):
    async with ClientSession(r, w) as session:
        await session.initialize()
        result = await session.call_tool("rag_search", {
            "query": "requisitos para progressão de regime",
            "top_k": 5
        })
        print(result)
```

---

## Fase 7 — Manutenção e Operação

### Health check

```bash
# Na VM
chmod +x scripts/health_check.sh
./scripts/health_check.sh
```

### Logs

```bash
# MCP Server
docker compose logs -f hermes

# Todos os serviços
docker compose logs -f

# Últimas 100 linhas
docker compose logs --tail 100 hermes
```

> ⚠️ Rode `docker compose logs` sempre de dentro do diretório `~/HermesContext`. Fora dele retorna `no configuration file provided: not found`.

### Reiniciar serviços

```bash
# Tudo
docker compose restart

# Só o MCP server (sem derrubar Redis)
docker compose restart hermes
```

### Atualizar código

**Em Produção:**
```bash
cd ~/HermesContext
git pull
docker compose build hermes
docker compose up -d hermes
```

> ⚠️ **Rebuild é obrigatório** em produção. O `docker-compose.yml` usa `target: production` que copia os arquivos no build (`COPY src/ src/` + `COPY scripts/ scripts/`).

**Em Desenvolvimento:**
```bash
cd ~/HermesContext
git pull
docker compose -f docker-compose.dev.yml restart hermes
```

> ✅ **Não precisa rebuild**: o `docker-compose.dev.yml` monta `./src:/app/src` e `./scripts:/app/scripts` como volumes. As mudanças são refletidas imediatamente com hot reload via `watchdog`.

### Re-rodar schema (após mudanças)

```bash
docker compose run --rm hermes python -m scripts.init_db
```

### Monitorar uso de recursos

```bash
# RAM por container
docker stats --no-stream

# Disco
df -h /

# RAM do sistema
free -h
```

### Adicionar ao crontab (health check automático)

```bash
crontab -e
```

Adicione:
```
*/5 * * * * /home/ubuntu/HermesContext/scripts/health_check.sh >> /var/log/rag-health.log 2>&1
```

---

## Resumo: Ordem de Execução dos Scripts

| # | Quando | Comando | O que faz |
|---|--------|---------|-----------|
| 1 | Após configurar `.env` e wallet | `python -m scripts.test_connection` | Valida conectividade Oracle + suporte VECTOR |
| 2 | Uma vez (ou após mudança de schema) | `python -m scripts.init_db` | Cria tabelas e índices no Oracle |
| 3 | Uma vez (ou após rebuild Docker) | `python -m scripts.warmup_models` | Baixa BGE-M3 + MiniLM para o cache |
| 4 | Uma vez (validação pré-produção) | `python -m scripts.smoke_test` | Testa pipeline inteiro e limpa dados de teste |
| 5 | Sempre que tiver documentos novos | `rag_ingest_file` (MCP) ou `python -m scripts.ingest_file <path>` (CLI) | Ingere documentos na base RAG |
| 6 | Periódico (cron a cada 5 min) | `./scripts/health_check.sh` | Verifica saúde de todos os componentes |

> Todos os scripts `python -m scripts.*` devem ser executados via `docker compose run --rm hermes` ou `docker compose exec hermes` quando o serviço já está rodando.

---

## Troubleshooting

### "Out of capacity" ao criar VM A1

A região pode estar sem capacidade ARM. Tente outro Availability Domain ou outra região. Algumas alternativas com boa disponibilidade: `us-ashburn-1`, `us-phoenix-1`, `eu-frankfurt-1`.

### Wallet: "ORA-28759: failure to open file"

O `sqlnet.ora` aponta para o diretório errado. Verifique:
```bash
cat ~/wallet/sqlnet.ora
# Deve ter: DIRECTORY="/home/ubuntu/wallet" (na VM) ou DIRECTORY="/wallet" (no container)
```

### "ORA-12170: TNS:Connect timeout"

O Autonomous DB pode estar parado por inatividade (Always Free para automaticamente após 7 dias sem uso). No console Oracle:
1. Acesse o Autonomous DB
2. Clique **More Actions → Start**
3. Aguarde status **Available**

### Embedding lento (>500ms)

Verifique que o container tem os limites de CPU adequados:
```bash
docker stats --no-stream hermes
```
Se a CPU está constantemente em 100%, aumente o limite no `docker-compose.yml`.

### "VECTOR type not supported"

O Autonomous DB precisa ser versão **23ai**. Verifique:
```sql
SELECT banner FROM v$version;
```
Se for versão anterior, recrie o DB selecionando 23ai no console.

### "ORA-01484: arrays can only be bound to PL/SQL statements"

O driver `oracledb` em thin mode não aceita `list[float]` como bind para colunas VECTOR. A solução é converter para `array.array('f', embedding)` antes do bind. Isso já está implementado no método `Database._to_vector()`.

### "ORA-30600: Oracle Text error — DRG-10599: column is not indexed"

O índice Oracle Text não foi criado. Rode:
```bash
docker compose run --rm hermes python -m scripts.init_db
```

### "ORA-30600: Oracle Text error — DRG-50901: text query parser syntax error"

Caracteres especiais na query (`?`, `&`, `!`, etc.) causam erro no parser Oracle Text. O `keyword_search` já sanitiza a query automaticamente, extraindo apenas palavras e usando `{palavra} OR {palavra}` para evitar interpretação de operadores.

### MCP endpoint não acessível externamente

Verifique nesta ordem:
1. Security List da VCN tem regra para porta 9090
2. Firewall do Ubuntu: `sudo iptables -L -n | grep 9090`
3. Container está ouvindo: `docker compose logs hermes | grep 9090`
4. Teste local primeiro: `curl -X POST http://localhost:9090/mcp -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'`

### "FastMCP.run() got an unexpected keyword argument 'host'"

A versão do pacote `mcp` instalada não suporta `host` no `run()`. O server já usa `uvicorn.run()` diretamente com `mcp.streamable_http_app()` para controle total de host/port.

### "app_lifespan() takes 0 positional arguments but 1 was given"

O FastMCP passa a instância do server como argumento para o lifespan. A assinatura correta é `async def app_lifespan(app: Any)`.

### MCP Inspector: "421 Invalid Host header"

O Inspector deve conectar via `http://localhost:9090/mcp`, não via IP público. Use o script automatizado que já configura tudo:
```bash
bash scripts/mcp-inspector.sh
```

Se preferir manualmente, use SSH tunnel e acesse com query params de transporte:
```bash
ssh -i ~/.ssh/id_ed25519 -L 6274:localhost:6274 -L 6277:localhost:6277 ubuntu@<vm-ip>
```

```text
http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=<token>&transport=streamable-http&serverUrl=http://localhost:9090/mcp
```

### `docker compose logs` retorna "no configuration file provided"

Rode o comando de dentro do diretório do projeto:
```bash
cd ~/HermesContext
docker compose logs --tail 20 hermes
```

### curl no Windows PowerShell não funciona com `http://`

O `curl` do PowerShell é um alias para `Invoke-WebRequest`. Use:
```powershell
curl.exe http://<vm-ip>:9090/mcp
# ou
Invoke-WebRequest -Uri http://<vm-ip>:9090/mcp -UseBasicParsing
```
