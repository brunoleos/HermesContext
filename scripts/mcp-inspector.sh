#!/bin/bash
# MCP Inspector — Workflow automatizado (VM + local)
# Uso: bash scripts/mcp-inspector.sh

SSH_HOST="ubuntu@147.15.91.57"
SSH_KEY="$HOME/.ssh/id_ed25519"
MCP_URL="http://localhost:9090/mcp"
INSPECTOR_LOG="/tmp/mcp-inspector.log"

cleanup() {
  echo ""
  echo "Encerrando túnel SSH..."
  [ -n "${TUNNEL_PID:-}" ] && kill $TUNNEL_PID 2>/dev/null
  exit 0
}
trap cleanup INT TERM

echo "=== MCP Inspector Workflow ==="
echo ""

# 1. Matar inspector antigo na VM e reiniciar
echo "[1/4] Reiniciando Inspector na VM..."
ssh -i "$SSH_KEY" "$SSH_HOST" "pkill -9 node 2>/dev/null; true" 2>/dev/null
sleep 2
ssh -i "$SSH_KEY" "$SSH_HOST" "rm -f $INSPECTOR_LOG && nohup npx @modelcontextprotocol/inspector $MCP_URL > $INSPECTOR_LOG 2>&1 &" 2>/dev/null
sleep 4

# 2. Aguardar token no log
echo "[2/4] Aguardando token de autenticação..."
TOKEN=""
for i in $(seq 1 30); do
  TOKEN=$(ssh -i "$SSH_KEY" "$SSH_HOST" "grep -oE 'MCP_PROXY_AUTH_TOKEN=[^&]+' $INSPECTOR_LOG 2>/dev/null | cut -d= -f2 | head -1" 2>/dev/null)
  if [ -n "$TOKEN" ]; then break; fi
  printf " ."
  sleep 2
done
echo ""

if [ -z "$TOKEN" ]; then
  echo "ERRO: Token não encontrado após 60s."
  echo "--- Log da VM ---"
  ssh -i "$SSH_KEY" "$SSH_HOST" "cat $INSPECTOR_LOG 2>/dev/null" || true
  exit 1
fi

# 3. Abrir túnel SSH
echo "[3/4] Abrindo túnel SSH local (portas 6274/6277)..."
ssh -i "$SSH_KEY" \
  -L 6274:localhost:6274 \
  -L 6277:localhost:6277 \
  -N "$SSH_HOST" &
TUNNEL_PID=$!
sleep 2

# 4. Abrir browser
URL="http://localhost:6274/?MCP_PROXY_AUTH_TOKEN=$TOKEN"
echo "[4/4] Abrindo browser..."
echo ""
echo "  URL: $URL"
echo ""
cmd //c start "$URL" 2>/dev/null || echo "  Abra manualmente: $URL"

echo "Túnel SSH ativo (Ctrl+C para encerrar)..."
wait $TUNNEL_PID
