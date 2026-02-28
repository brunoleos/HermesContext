FROM python:3.12-slim AS base

# Oracle Instant Client para ARM64 + deps de build
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgomp1 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[all]" 2>/dev/null || pip install --no-cache-dir \
        "mcp>=1.0.0" \
        "pydantic>=2.0" \
        "sentence-transformers>=3.0.0" \
        "oracledb>=2.0.0" \
        "redis>=5.0.0" \
        "celery[redis]>=5.4.0" \
        "httpx>=0.27.0" \
        "uvicorn>=0.30.0" \
        "numpy>=1.26.0"

COPY src/ src/
COPY scripts/ scripts/

# Pré-download dos modelos durante build (cache no layer)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-m3')" \
    && python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

ENV PYTHONUNBUFFERED=1
ENV MCP_TRANSPORT=streamable_http
ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=9090

EXPOSE 9090

CMD ["python", "-m", "src.server"]