Inicie o workflow do MCP Inspector para testar o servidor remoto:

1. Execute `bash scripts/mcp-inspector.sh` via Bash tool
2. Aguarde o script reportar a URL com o token
3. Informe ao usuário a URL gerada e confirme que o browser foi aberto
4. Se houver erros, diagnostique e sugira correções

O script automaticamente:
- Mata processos node antigos na VM (`pkill -9 node`) para liberar portas 6274/6277
- Inicia o Inspector em background na VM via `nohup` + `< /dev/null`
- Captura o auth token do log via polling SSH
- Libera portas locais ocupadas (Windows: `netstat -ano` + `taskkill`)
- Abre túnel SSH local (`-L 6274:localhost:6274 -L 6277:localhost:6277 -N`)
- Abre o browser com query params `transport=streamable-http&serverUrl=http://localhost:9090/mcp`

**Nota**: O MCP Inspector abre túnel apenas para as portas do Inspector (6274/6277).
Para que o Claude Code acesse as MCP tools diretamente, é necessário um túnel separado para a porta 9090:

```bash
ssh -i ~/.ssh/id_ed25519 -L 9090:localhost:9090 -N ubuntu@147.15.91.57
```

Com esse túnel ativo, o MCP server fica disponível em `http://localhost:9090/mcp` e as tools podem ser chamadas diretamente pelo agente.
