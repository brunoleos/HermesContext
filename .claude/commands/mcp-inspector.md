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
