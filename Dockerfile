# ══════════════════════════════════════════════════════════════
# Project Janus — Container Deployment
# Sovereign Archival Intelligence
# ══════════════════════════════════════════════════════════════
#
# Build:  docker build -t janus .
# Run:    docker run -p 8108:8108 janus
# Test:   curl http://localhost:8108/mcp
#
# The MCP server runs in Streamable HTTP mode, exposing
# all tools, resources, and prompts for external agents.
# ══════════════════════════════════════════════════════════════

FROM python:3.11-slim

# System deps for lxml, chromadb compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create data directories
RUN mkdir -p data/chroma_db

# Expose MCP HTTP port
EXPOSE 8108

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s \
    CMD python -c "import httpx; httpx.get('http://localhost:8108/mcp')" || exit 1

# Run in HTTP mode
CMD ["python", "serve.py"]
