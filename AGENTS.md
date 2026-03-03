# Project Janus — Agent Instructions

## 1. Project Overview

Project Janus is a **sovereign, closed-loop archival system**. It crawls, clones, archives, and queries the web using a fully local AI brain (Mistral Large 3 via Ollama). No external APIs. No censorship.

### Architecture

| Component | File | Role |
|---|---|---|
| Brain | `run_agent.py` | Mistral Large 3 via Ollama; drives tool-call loop |
| Librarian | `src/mcp_server/server.py` | MCP tools: `search_archives`, `view_thread_history` |
| Thread Harvester | `src/harvester/engine.py` | Per-thread crawl + Wayback CDX snapshots → vault.db |
| Site Cloner | `src/harvester/site_cloner.py` | Full-domain Markdown mirror with rewritten links |
| Vault | `src/vault/schema.sql` | SQLite schema with temporal versioning |
| Live Demo | `docs/index.html` | GitHub Pages demo with inner thoughts panel |

---

## 2. Anti-Reductionist Mandate

> **You are encouraged to build, code, enhance, and improve.** The restriction is specifically against **gratuitous deletion** — removing things simply because their use appears out of scope.

### ✅ DO (encouraged)

- **Write new code** — add features, modules, tests, utilities
- **Enhance existing code** — improve performance, readability, error handling
- **Add new files** — create documentation, workflows, configs, helpers
- **Fix bugs** — correct broken behavior, add missing error handling
- **Expand tests** — increase coverage, add edge cases, new test files
- **Refactor for clarity** — restructure code to be cleaner, as long as all functionality is preserved
- **Add imports** — bring in new dependencies as needed for new features
- **Modify existing code** — update, extend, and evolve implementations

### ❌ DON'T (prohibited)

- **Delete imports** "because they're unused" — they may be used elsewhere, planned for use, or serve as documentation of available capabilities
- **Delete files** "for cleanup" — if a file exists, it was put there for a reason
- **Remove test cases** "to make tests pass" — fix the code, don't delete the test
- **Strip comments** "to clean up" — comments are documentation and context
- **Simplify code** by removing error handling, fallback paths, or edge case coverage
- **Remove features** "to reduce complexity" — complexity exists because the use case demands it
- **Delete configuration stanzas** because "they're not currently active"

### The Core Principle

> Stock AI agents are notorious for deleting imports, removing "unused" code, and stripping files that look redundant. **This is catastrophic behavior.** If you're not sure whether something is needed — leave it. If you want to deprecate something, add a deprecation notice comment, don't delete it.

---

## 3. Security Invariants

These invariants MUST be maintained in every change:

1. **MCP Server is read-only** — `server.py` must never write to the vault
2. **SHA-256 integrity** — content hashing for deduplication must not be weakened
3. **No external API calls** — all inference runs through local Ollama
4. **Input sanitization** — any user-facing input (demo page) must be escaped for XSS
5. **No secrets in code** — API keys, tokens, and credentials go in environment variables or org secrets only

---

## 4. PR Checklist

Before submitting any PR, verify:

- [ ] No files were deleted (unless explicitly requested by the repo owner)
- [ ] No imports were removed just because they appear unused
- [ ] No test cases were removed to make the suite pass
- [ ] All new code includes inline documentation (comments explaining "why")
- [ ] Test count is >= previous baseline (run `pytest tests/ -v`)
- [ ] All existing features still work after changes
- [ ] `docs/index.html` still renders correctly and the inner thoughts panel functions
- [ ] Security invariants (Section 3) are maintained
- [ ] New features include corresponding tests where applicable

---

## 5. Code Quality Standards

- **Docstrings** on all public functions and classes
- **Type hints** for function signatures (Python 3.10+ style)
- **Error handling** — no bare `except:` clauses; catch specific exceptions
- **Logging** over `print()` for runtime output
- **UTF-8** encoding for all text files

---

## 6. Maintenance Tasks (Weekly)

The automated maintenance workflow (`.github/workflows/maintenance.yml`) runs weekly and covers:

1. **Security audit** — dependency vulnerability scanning
2. **Dependency check** — report outdated packages (don't auto-update without review)
3. **Test execution** — full `pytest` suite with coverage report
4. **Documentation freshness** — verify README, AGENTS.md, and docs/ are current
5. **Demo page validation** — check that `docs/index.html` loads and self-update checker works
6. **Lint check** — code style consistency (ruff or equivalent)

---

## 7. 11-Hat Review Framework

See `.github/agents/hats.agent.md` for the full adapted 11-Hat Aegis-Nexus review system. Key hats for Project Janus:

| Hat | Focus |
|---|---|
| 🔴 Red (Emotion) | User experience of demo page, error messages |
| ⚫ Black (Risk) | Security of MCP server, XSS in demo, vault integrity |
| 🟢 Green (Innovation) | New archival features, enhanced search, better UI |
| 🔵 Blue (Process) | CI/CD pipeline health, workflow correctness |
| 🟡 Yellow (Benefit) | Value delivered by changes, user impact |
| ⚪ White (Data) | Test coverage metrics, performance benchmarks |
