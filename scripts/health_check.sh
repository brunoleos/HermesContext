#!/bin/bash
# Health check — verifica todos os componentes do RAG MCP Server
# Uso: ./scripts/health_check.sh

set -euo pipefail

MCP_URL="${MCP_URL:-http://localhost:9090}"
REDIS_URL="${REDIS_URL:-redis://localhost:6379}"

echo "============================================"
echo "  RAG MCP — Health Check"
echo "============================================"

PASS=0
FAIL=0

check() {
    local name="$1"
    local cmd="$2"
    printf "  %-30s" "$name"
    if eval "$cmd" > /dev/null 2>&1; then
        echo "✅"
        PASS=$((PASS + 1))
    else
        echo "❌"
        FAIL=$((FAIL + 1))
    fi
}

# 1. MCP Server HTTP
check "MCP endpoint acessível" "curl -sf --max-time 5 ${MCP_URL}/mcp"

# 2. Redis
check "Redis respondendo" "redis-cli -u ${REDIS_URL} ping"

# 3. Docker containers
check "Container hermes rodando" "docker compose ps hermes | grep -q 'Up\|running'"
check "Container redis rodando" "docker compose ps redis | grep -q 'Up\|running'"

# 4. Disk
DISK_PCT=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
check "Disco < 90% ($DISK_PCT%)" "[ $DISK_PCT -lt 90 ]"

# 5. RAM
MEM_PCT=$(free | awk '/Mem:/{printf "%d", $3/$2 * 100}')
check "RAM < 85% ($MEM_PCT%)" "[ $MEM_PCT -lt 85 ]"

echo ""
echo "  Resultado: $PASS OK, $FAIL falha(s)"
echo "============================================"

[ $FAIL -eq 0 ] && exit 0 || exit 1
