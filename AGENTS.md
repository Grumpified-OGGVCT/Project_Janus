# Project Janus — Agent Instructions

> **Anti-Reductionist Mandate**: All agents operating on this repository MUST follow these rules without exception.

## Architecture Overview

Project Janus is a sovereign, closed-loop archival system with four core components:

| Component | File | Role |
|-----------|------|------|
| Brain | `run_agent.py` | Mistral Large 3 via Ollama; drives tool-call loop |
| Librarian | `src/mcp_server/server.py` | MCP tools: `search_archives`, `view_thread_history` |
| Thread Harvester | `src/harvester/engine.py` | Per-thread crawl + Wayback CDX snapshots → `vault.db` |
| Site Cloner | `src/harvester/site_cloner.py` | Full-domain Markdown mirror with rewritten links |
| Vault | `src/vault/schema.sql` | SQLite schema with temporal versioning |
| Demo Page | `docs/index.html` | GitHub Pages demo with live Ollama API calls |
| Demo Script | `scripts/run_demo.py` | Canned query runner for CI demo output |

## Mandatory Rules

### 1. Anti-Reductionist Mandate

**NEVER** do any of the following:
- ❌ Remove imports (even if they appear unused — they may be used dynamically)
- ❌ Delete files or directories
- ❌ Remove or simplify test cases
- ❌ Replace working code with simplified stubs
- ❌ Remove comments or docstrings
- ❌ Reduce function signatures or parameters
- ❌ "Optimize" by removing error handling paths
- ❌ Delete configuration options or environment variable support

**ALWAYS** do the following:
- ✅ Add new functionality additively
- ✅ Expand test coverage (test count must be >= previous baseline)
- ✅ Preserve all existing imports, even if adding new ones
- ✅ Keep all error handling paths
- ✅ Maintain or increase code documentation
- ✅ Add type hints where missing (never remove existing ones)

### 2. Security Invariants

- **Read-only vault**: The MCP server MUST always open `vault.db` in `mode=ro`. Never modify this.
- **SHA-256 integrity**: Content hashing for deduplication must be preserved.
- **Local-only AI**: No external API calls to OpenAI, Anthropic, or similar. All inference via Ollama.
- **No credential exposure**: Never hardcode API keys, tokens, or secrets.
- **Input sanitization**: All user inputs in the demo page must be escaped before rendering.

### 3. PR Checklist (Mandatory for All PRs)

Before submitting any PR, verify:

- [ ] No files deleted
- [ ] No tests removed or simplified
- [ ] No imports removed
- [ ] Test count >= previous baseline
- [ ] All existing functionality preserved
- [ ] New code includes docstrings and type hints
- [ ] Security invariants maintained
- [ ] `pytest tests/ -v` passes

### 4. Code Quality Standards

- Python: Follow PEP 8, use type hints, write docstrings
- HTML/JS: Use semantic HTML5, include ARIA labels, escape user input
- CSS: Use CSS custom properties (variables), mobile-first responsive design
- Tests: Use pytest, aim for > 80% coverage, never mock when integration tests are feasible

### 5. Maintenance Task Guidelines

When performing maintenance tasks:
1. **Read this file first** — understand the architecture before making changes
2. **Check existing tests** — run `pytest tests/ -v` before AND after changes
3. **Additive only** — enhance, don't replace
4. **Document changes** — update README.md if adding new features
5. **Security scan** — check for hardcoded secrets, SQL injection, XSS vulnerabilities

## File Structure

```
Project_Janus/
├── AGENTS.md              ← You are here
├── README.md              ← Project documentation
├── main.py                ← Entry point (harvest → clone → agent)
├── run_agent.py           ← AI agent with tool-call loop
├── requirements.txt       ← Python dependencies
├── data/                  ← Runtime data (vault.db, chroma_db, site_mirror)
├── docs/
│   ├── index.html         ← GitHub Pages demo page
│   └── latest_run.json    ← Auto-updated demo output
├── scripts/
│   └── run_demo.py        ← CI demo script (REST API)
├── src/
│   ├── harvester/
│   │   ├── engine.py      ← Thread harvester
│   │   └── site_cloner.py ← Full-site Markdown cloner
│   ├── mcp_server/
│   │   └── server.py      ← MCP tool server (read-only)
│   └── vault/
│       └── schema.sql     ← SQLite schema
├── tests/                 ← Test suite
└── .github/
    ├── agents/
    │   └── hats.agent.md  ← 11-Hat review agent
    └── workflows/
        ├── ci.yml         ← CI pipeline
        ├── demo.yml       ← Weekly demo runner
        └── maintenance.yml← Weekly maintenance
```
