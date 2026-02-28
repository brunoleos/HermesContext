# Guia de Deploy — RAG MCP Server no Oracle Cloud Always Free

Passo a passo completo: do zero ao `http://<vm-ip>:9090/mcp` funcionando.

---

## Pré-requisitos

- Conta Oracle Cloud (cadastro em [cloud.oracle.com](https://cloud.oracle.com))
- Um domínio (opcional, para HTTPS)
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
   - **Display name**: `ragdb`
   - **Database name**: `ragdb`
   - **Workload type**: Transaction Processing (ou Data Warehouse — ambos suportam VECTOR)
   - **Deployment type**: Serverless
   - **Always Free**: ✅ **Marque esta opção**
   - **Database version**: 23ai (obrigatório para suporte a VECTOR)
   - **OCPU count**: 1 (Always Free máximo)
   - **Storage**: 20 GB (Always Free máximo)
   - **Password**: defina uma senha forte (ex: `RagMcp2026!Seguro`)
     - **Guarde esta senha**, será usada no `.env`
   - **Network Access**: Secure access from everywhere (com mTLS via wallet)
   - **License type**: License Included
4. Clique **Create Autonomous Database**
5. Aguarde status **Available** (~3 min)

### Passo 1.6 — Baixar o Wallet (credenciais mTLS)

1. Na página do Autonomous DB (`ragdb`), clique **DB Connection**
2. Clique **Download Wallet**
3. Defina um password para o wallet (pode ser o mesmo da senha do DB)
4. Salve o arquivo `Wallet_ragdb.zip`
5. **Não descompacte no seu PC** — será enviado direto para a VM

### Passo 1.7 — Obter a Connection String (DSN)

1. Ainda em **DB Connection**, na seção **Connection Strings**
2. Selecione **TLS Authentication: Mutual TLS**
3. Copie a connection string **`ragdb_low`** (perfil de baixo consumo, ideal para Always Free)
4. O formato será algo como:

```
(description=(retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1522)(host=adb.sa-saopaulo-1.oraclecloud.com))(connect_data=(service_name=xxxxxxxxxxxx_ragdb_low.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))
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
```

### Passo 2.3 — Upload e configuração do Wallet

No seu **PC local**, envie o wallet para a VM:

```bash
scp -i ~/.ssh/id_ed25519 Wallet_ragdb.zip ubuntu@<vm-ip>:~/
```

Na **VM**, descompacte:

```bash
mkdir -p ~/wallet
cd ~/wallet
unzip ~/Wallet_ragdb.zip
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
git clone git@github.com:brunoleos/HermesContext.git rag-mcp-server
cd rag-mcp-server

cp .env.example .env
nano .env
```

Preencha o `.env` com os valores reais:

```bash
# Valores de exemplo — substitua pelos seus
ORACLE_DSN=(description=(retry_count=20)(...o DSN completo copiado no Passo 1.7...))
ORACLE_USER=ADMIN
ORACLE_PASSWORD=RagMcp2026!Seguro
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

### Passo 3.1 — Build das imagens Docker

```bash
cd ~/rag-mcp-server
docker compose build
```

> ⏱️ Primeiro build leva **10–20 minutos** no ARM (compilação de dependências nativas). Builds subsequentes usam cache e são rápidos.

### Passo 3.2 — Subir somente o Redis primeiro

```bash
docker compose up -d redis
docker compose logs redis
# Deve mostrar "Ready to accept connections"
```

### Passo 3.3 — Testar conexão com Oracle DB

```bash
docker compose run --rm rag-mcp python -m scripts.test_connection
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

[2/4] Conectando...
       ✅ Conexão OK

[3/4] Versão do banco...
       Oracle Database 23ai ...

[4/4] Testando suporte a VECTOR...
       ✅ VECTOR suportado (distância teste: 1.0000)

✅ Todos os testes passaram.
```

> ❌ Se falhar em [2/4], verifique: DSN copiado corretamente, senha sem caracteres especiais mal-escapados, wallet descompactado.
> ❌ Se falhar em [4/4], o DB precisa ser versão 23ai. Recrie selecionando a versão correta.

### Passo 3.4 — Inicializar o schema (tabelas + índices)

```bash
docker compose run --rm rag-mcp python -m scripts.init_db
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

> Este script é idempotente. Pode rodar múltiplas vezes sem problemas.

### Passo 3.5 — Baixar modelos de ML (warmup)

```bash
docker compose run --rm rag-mcp python -m scripts.warmup_models
```

> ⏱️ Primeiro download: **~5 minutos** (BGE-M3 ~1.2 GB + MiniLM ~90 MB).
> Downloads ficam no volume Docker `models-cache` e persistem entre rebuilds.

Saída esperada:
```
============================================
  RAG MCP — Download e Warmup dos Modelos
============================================

[1/3] Baixando BGE-M3 (BAAI/bge-m3)...
       ✅ Carregado em 45.2s

       Warmup: embedding de teste...
       ✅ Dimensão: 1024, latência: 132ms

[2/3] Baixando BGE-M3 Sparse (Qdrant/bm25)...
       ✅ Carregado em 3.1s

[3/3] Baixando Reranker (cross-encoder/ms-marco-MiniLM-L-6-v2)...
       ✅ Carregado em 8.4s

       Warmup: reranking de teste...
       ✅ Scores: [3.2145, -8.9231], latência: 87ms

============================================
  ✅ Todos os modelos prontos.
  Cache em: /root/.cache (1.3 GB)
============================================
```

### Passo 3.6 — Smoke test (pipeline completo)

```bash
docker compose run --rm rag-mcp python -m scripts.smoke_test
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
       ✅ Doc ID: 1, Chunks: 3, 1842ms

[2/5] Teste de embedding...
       ✅ Dimensão: 1024, latência: 105ms

[3/5] Vector search...
       ✅ 3 resultados, 12ms

[4/5] Busca híbrida + reranking...
       ✅ 3 resultados de 3 candidatos, 287ms
       Top resultado: score=4.2318
       Preview: Art. 112. A pena privativa de liberdade será executada em forma progressiva...

[5/5] Estatísticas...
       Documentos: 1
       Chunks: 3

  🧹 Limpando documento de teste (ID: 1)...
       ✅ Documento de teste removido.

============================================
  ✅ SMOKE TEST PASSOU — pipeline RAG funcionando!
============================================
```

---

## Fase 4 — Subir o MCP Server

### Passo 4.1 — Iniciar todos os serviços

```bash
cd ~/rag-mcp-server
docker compose up -d
```

### Passo 4.2 — Verificar que o endpoint está acessível

```bash
# Da própria VM
curl -s http://localhost:9090/mcp | head

# Logs do MCP server
docker compose logs -f rag-mcp
# Deve mostrar: "Iniciando RAG MCP Server — transport=streamable_http, host=0.0.0.0, port=9090"
```

Do **seu PC local** (substitua `<vm-ip>` pelo IP real):

```bash
curl -s http://<vm-ip>:9090/mcp | head
```

> ❌ Se não responder: verifique a Security List (Passo 1.3) e o firewall do Ubuntu:
> ```bash
> sudo iptables -L -n | grep 9090
> # Se não aparecer regra, adicione:
> sudo iptables -I INPUT -p tcp --dport 9090 -j ACCEPT
> ```

### Passo 4.3 — Testar via MCP Inspector (opcional)

No seu PC local:

```bash
npx @modelcontextprotocol/inspector http://<vm-ip>:9090/mcp
```

Isso abre uma interface web onde você pode listar tools, chamar `rag_search`, `rag_get_stats`, etc.

---

## Fase 5 — Ingestão dos Documentos Reais

### Passo 5.1 — Upload de documentos para a VM

No seu **PC local**:

```bash
# Arquivo único
scp -i ~/.ssh/id_ed25519 resolucao_45.txt ubuntu@<vm-ip>:~/docs/

# Diretório inteiro
scp -ri ~/.ssh/id_ed25519 ./documentos/ ubuntu@<vm-ip>:~/docs/
```

### Passo 5.2 — Ingerir arquivo único

```bash
docker compose exec rag-mcp python -m scripts.ingest_file \
    /data/resolucao_45.txt \
    --title "Resolução SAP 45/2024" \
    --type resolucao
```

> O diretório `/data` dentro do container mapeia para o volume `ingest-data`.
> Alternativamente, monte o diretório `~/docs` adicionando ao docker-compose:
> ```yaml
> volumes:
>   - /home/ubuntu/docs:/docs:ro
> ```
> E use `/docs/resolucao_45.txt` como path.

### Passo 5.3 — Ingerir diretório inteiro

```bash
docker compose exec rag-mcp python -m scripts.ingest_file \
    /docs/ \
    --type legislacao
```

> Cada arquivo vira um documento separado. O título é inferido do nome do arquivo.

### Passo 5.4 — Verificar ingestão

```bash
docker compose exec rag-mcp python -c "
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

---

## Fase 6 — Conectar a LLM

### Opção A: Claude Desktop

Edite `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac) ou `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "rag": {
      "type": "url",
      "url": "http://<vm-ip>:9090/mcp"
    }
  }
}
```

Reinicie o Claude Desktop. Os 6 tools RAG aparecem na interface.

### Opção B: Claude Code (CLI)

```bash
claude mcp add rag --transport http http://<vm-ip>:9090/mcp
```

### Opção C: Qualquer agente MCP (Python)

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client("http://<vm-ip>:9090/mcp") as (r, w, _):
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
docker compose logs -f rag-mcp

# Todos os serviços
docker compose logs -f

# Últimas 100 linhas
docker compose logs --tail 100 rag-mcp
```

### Reiniciar serviços

```bash
# Tudo
docker compose restart

# Só o MCP server (sem derrubar Redis/worker)
docker compose restart rag-mcp
```

### Atualizar código

```bash
cd ~/rag-mcp-server
git pull
docker compose build rag-mcp
docker compose up -d rag-mcp
```

### Re-rodar schema (após mudanças)

```bash
docker compose run --rm rag-mcp python -m scripts.init_db
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
*/5 * * * * /home/ubuntu/rag-mcp-server/scripts/health_check.sh >> /var/log/rag-health.log 2>&1
```

---

## Resumo: Ordem de Execução dos Scripts

| # | Quando | Comando | O que faz |
|---|--------|---------|-----------|
| 1 | Após configurar `.env` e wallet | `python -m scripts.test_connection` | Valida conectividade Oracle + suporte VECTOR |
| 2 | Uma vez (ou após mudança de schema) | `python -m scripts.init_db` | Cria tabelas e índices no Oracle |
| 3 | Uma vez (ou após rebuild Docker) | `python -m scripts.warmup_models` | Baixa BGE-M3 + MiniLM para o cache |
| 4 | Uma vez (validação pré-produção) | `python -m scripts.smoke_test` | Testa pipeline inteiro e limpa dados de teste |
| 5 | Sempre que tiver documentos novos | `python -m scripts.ingest_file <path>` | Ingere documentos na base RAG |
| 6 | Periódico (cron a cada 5 min) | `./scripts/health_check.sh` | Verifica saúde de todos os componentes |

> Todos os scripts `python -m scripts.*` devem ser executados via `docker compose run --rm rag-mcp` ou `docker compose exec rag-mcp` quando o serviço já está rodando.

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
docker stats --no-stream rag-mcp
```
Se a CPU está constantemente em 100%, aumente o limite no `docker-compose.yml`.

### "VECTOR type not supported"

O Autonomous DB precisa ser versão **23ai**. Verifique:
```sql
SELECT banner FROM v$version;
```
Se for versão anterior, recrie o DB selecionando 23ai no console.

### MCP endpoint não acessível externamente

Verifique nesta ordem:
1. Security List da VCN tem regra para porta 9090
2. Firewall do Ubuntu: `sudo iptables -L -n | grep 9090`
3. Container está ouvindo: `docker compose logs rag-mcp | grep 9090`
4. Teste local primeiro: `curl http://localhost:9090/mcp`
