# ⚖ Project Janus

> A sovereign, closed-loop archival system — crawl, clone, archive and query
> the web with a fully local AI brain. No external APIs. No censorship.

[![CI](https://github.com/Grumpified-OGGVCT/Project_Janus/actions/workflows/ci.yml/badge.svg)](https://github.com/Grumpified-OGGVCT/Project_Janus/actions/workflows/ci.yml)
[![Demo](https://img.shields.io/badge/demo-GitHub_Pages-blue)](https://grumpified-oggvct.github.io/Project_Janus/)
[![License](https://img.shields.io/github/license/Grumpified-OGGVCT/Project_Janus)](LICENSE)

**[🌐 Live Demo Page →](https://grumpified-oggvct.github.io/Project_Janus/)**

---

### The March 2026 Cloud Model Pipeline (Infinite RAG)
To achieve true "Infinite RAG" over your entire codebase and archival history, Project Janus orchestrates a suite of specialized local/cloud proxy models via Ollama:

1. **`qwen3-coder-next`** - Generates high-quality, code-aware vector embeddings (understands symbols, signatures, docstrings).
2. **`minimax-m2.5`** - Fast, on-device reranking to order the candidates returned by the vector search cheaply and with low latency.
3. **`gemini-3-flash-preview`** - Rapid context compression. When graph walks overflow the context window, this model shrinks chunks to two-sentence summaries.
4. **`devstral-2`** - The 123B parameter heavy-lifter. Provides the strongest multi-file reasoning and tool-use to deliver the final answer based on the distilled graph.

*(Optional side-task models like `qwen3.5`, `glm-5`, or `nemotron-3-nano` can also be pulled if needed).*

## 🌐 The March 2026 Cloud Model Pipeline (Infinite RAG)
To achieve true "Infinite RAG" over your entire codebase and archival history, Project Janus is designed to orchestrate a suite of specialized local/cloud proxy models via Ollama.

**Model-by-model choice:**
1. **`qwen3-coder-next`** - Code-aware embeddings optimized for agentic workflows. Turns function/class sources into high-quality vectors that understand symbols, signatures, and docstrings.
2. **`minimax-m2.5`** - Fast, on-device reranking to order the candidates returned by the vector search cheaply and with low latency.
3. **`gemini-3-flash-preview`** - Context compression. When the graph walk overflows the context window, this model shrinks chunks to two-sentence summaries.
4. **`devstral-2`** - The 123B parameter heavy-lifter. Provides the strongest multi-file reasoning and tool-use to deliver the final answer based on the distilled graph.

*(Optional general-purpose multimodal models: `qwen3.5`, `glm-5`, or `nemotron-3-nano` can also be pulled if needed for side tasks).*

The architecture leverages **Memory-MCP** (`@modelcontextprotocol/server-memory`) and **LanceDB** to explicitly map entities and relations across the repository, allowing `devstral-2` to walk the knowledge graph infinitely during retrieval.

## 🌐 The Code-Awareness Service (Sovereign OS Integration)

Project Janus is not just a standalone script—it acts as the cognitive core inside a broader **Sovereign OS**. The Infinite RAG engine we just wired into the bytecode VM (`MEMORY_STORE` / `MEMORY_RECALL` with confidence tracking, decay, correction chains, hot/warm/cold tiers) is the exact same abstraction that the Code-Awareness Service's graph-walk-and-rerank pipeline uses.

The integration path is clear:
`HLF compiler → bytecode VM → Infinite RAG engine → Janus Code-Awareness API (Port 9345) → Ollama Cloud models.`
One sovereign pipeline from `.hlf` source to enterprise-grade codebase intelligence.

### 📌 1️⃣ Exact Cloud Model Pipeline (March 2026 Catalogue)
To achieve true "Infinite RAG", Janus orchestrates a suite of specialized local/cloud proxy models via Ollama:

1. **`embeddinggemma`** - Dense embedding model from Google. Generates high-quality vectors for every symbol.
2. **`minimax-m2.5:cloud`** - Fast, on-device reranking to order the candidates returned by the vector search cheaply and with low latency.
3. **`gemini-3-flash-preview:cloud`** - Context compression. When the graph walk overflows the context window, this model shrinks chunks to two-sentence summaries.
4. **`devstral-2:123b-cloud`** - The 123B parameter heavy-lifter. Provides the strongest multi-file reasoning and tool-use to deliver the final answer based on the distilled graph.

### 📚 2️⃣ Persistent Knowledge Graph (Memory-MCP & LanceDB)
The architecture leverages **Memory-MCP** (`@modelcontextprotocol/server-memory`) and **LanceDB** to explicitly map entities and relations across the repository, allowing `devstral-2` to walk the knowledge graph infinitely during retrieval.

* **Entities / Relations / Observations:** Stored locally in a JSONL file (`.claude/memory.json`).
* **Vector Store:** LanceDB stores the `embeddinggemma` vectors on-disk.

### ⚙️ 3️⃣ RAM & Resource Mitigation (Stalemate Prevention)
A massive repository will consume **Disk Space, NOT RAM**, while idle. However, to prevent a deep "Infinite RAG" graph walk from causing RAM spikes or out-of-memory (OOM) stalemates during traversal:

* **On-Disk Memory Mapping:** LanceDB utilizes Apache Arrow to memory-map vectors directly from disk, ensuring the DB growth doesn't consume active RAM until a specific chunk is accessed.
* **Bounded BFS Expansion:** The `expand_graph` function enforces a strict `depth` and `max_nodes_per_hop` limit. It only pulls the immediate explicit edges (imports, calls, tests), preventing an exponential explosion of nodes in memory.
* **Hot/Warm/Cold Tiering:** Active memories requested via `MEMORY_RECALL` bytecode are cached in Hot RAM. Older archives decay to Cold disk storage.
* **Aggressive Context Compression:** Before the final context is handed to the 123B `devstral-2` model, the ultra-fast `gemini-3-flash-preview` model shrinks any overflow chunks into dense 2-sentence summaries. This guarantees the context window is respected without losing the semantic map.

### 🐳 4️⃣ Deployment (Port 9345)
The entire Code-Awareness Service runs as a FastAPI wrapper inside Docker, exposing the API on custom port **9345**. The internal Ollama daemon remains on `11434`. Client SDKs (Python/Node) default to `http://localhost:9345` to interface seamlessly with the OS bridge.


## Architecture

```
User Prompt
    ↓
Mistral Large 3 (Ollama — 256K ctx, native function-calling)
    ↓ tool call          ↑ raw data
MCP Server (read-only librarian)
    ↓ queries            ↑ context
SQLite Vault + ChromaDB (vector index)
    ↑ populated by
Harvester  /  Site Cloner (field agents)
```

### Infinite RAG & O(1) Context Bounding
Project Janus employs an "Infinite RAG" system using the Context7 protocol via the `deep_recall` MCP tool. This allows the agent to semantically search vast historical archives dynamically without overflowing the context window.
It enforces O(1) Context Bounding (the Silver Hat protocol), ensuring the agent's prompt never grows infinitely: the context is strictly bounded to a lightweight workspace snapshot and only the last ~10 actions, while the heavy lifting is handled by massive vector retrieval behind the scenes.

| Component | File | Role |
|-----------|------|------|
| Brain | `run_agent.py` | Mistral Large 3 via Ollama; drives tool-call loop |
| Librarian | `src/mcp_server/server.py` | MCP tools: `search_archives`, `view_thread_history`, `search_with_contents`, `auto_search`, `crawl_and_index`, collection tools |
| Thread Harvester | `src/harvester/engine.py` | Per-thread crawl + Wayback CDX snapshots → `vault.db` |
| **Site Cloner** | `src/harvester/site_cloner.py` | **Full-domain Markdown mirror with rewritten links** |
| Vault | `src/vault/schema.sql` | SQLite schema with temporal versioning |

---

## Site Cloner — Full Markdown Mirror

The `SiteCloner` crawls an entire domain and produces a **fully navigable
Markdown clone** that works in GitHub, Obsidian, VS Code, or any Markdown
renderer:

```
data/site_mirror/your-site.net/
  _index.md               ← generated sitemap / navigation tree
  index.md                ← home page
  threads/
    some-thread.md
    another-thread.md
  forums/
    general.md
```

Every internal link is **rewritten to a relative `.md` path** so you can
navigate the entire mirror offline exactly as you would the live site.

```python
from src.harvester.site_cloner import SiteCloner

cloner = SiteCloner(output_dir="data/site_mirror", max_pages=1000)
cloner.clone("https://your-site.net/")
```

Or configure it in `main.py`:

```python
TARGET_SITE     = "https://your-site.net/"
CLONE_MAX_PAGES = 1000
```

---

## Features

- **Full-site Markdown clone** — entire domain mirrored as linked `.md` files; `_index.md` navigation tree auto-generated
- **Temporal versioning** — `live`, `wayback_oldest`, `wayback_recent` captures stored side-by-side
- **Immutable vault** — SHA-256 content hashes; MCP server always opens DB in `mode=ro`
- **Semantic search** — `nomic-embed-text` embeddings + ChromaDB, entirely local
- **Infinite RAG** — Context7 deep retrieval via `deep_recall` allowing infinite scalability with bounded memory
- **100% local AI** — zero OpenAI / Anthropic; all inference via Ollama
- **Native tool-calling** — Mistral Large 3 function-calling drives the MCP tool loop
- **CI-tested** — unit tests run on every push via GitHub Actions
- **Org-secret demo** — weekly auto-demo commits fresh output to the GitHub Pages demo site

---

## Prerequisites

- Python 3.12+ with `pip`
- An Ollama endpoint with `mistral-large-3:675b-cloud` available; set `OLLAMA_HOST` (and `OLLAMA_API_KEY` if required) to point at it. Defaults to `http://localhost:11434`.
- Writable `data/` directory; the harvester will materialise `data/vault.db` from `src/vault/schema.sql`.

---

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/Grumpified-OGGVCT/Project_Janus.git
cd Project_Janus
pip install -r requirements.txt

# 2. Configure targets (edit main.py)
TARGET_URLS = ["https://your-site.net/threads/example.123/"]  # per-thread harvest
TARGET_SITE = "https://your-site.net/"                        # full-site clone

# 2a. Point at your Ollama host (if not local)
export OLLAMA_HOST="https://ollama.example.com"
# Optional: export OLLAMA_API_KEY="your-token"

# 3. Run (harvest → clone → launch AI agent)
python main.py

# Agent only
python run_agent.py
```

---

## GitHub Actions

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `CI` | Every push / PR | Install deps, run unit tests |
| `Live Demo` | Manual + weekly (Mon 00:00 UTC) | Run canned Ollama query, commit updated demo page |

### Required organisation secret

| Secret | Value |
|--------|-------|
| `OLLAMA_HOST` | URL of your remote Ollama server, e.g. `https://ollama.example.com` |

### Enable the demo page (one-time setup)

```
GitHub Repo → Settings → Pages
  Source: Deploy from branch → main → /docs → Save
```

The demo page will then be live at:
`https://grumpified-oggvct.github.io/Project_Janus/`

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```
