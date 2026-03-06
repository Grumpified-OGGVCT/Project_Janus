"""
Project Janus — Multi-Transport MCP Knowledge Server
=====================================================
Sovereign Archival Intelligence

Transports:
  stdio             : python -m src.mcp_server.server
  Streamable HTTP   : python -m src.mcp_server.server --http
  (or)              : python serve.py

MCP Capabilities:
  TOOLS      — 13 tools across 4 categories
  RESOURCES  — Vault database metadata, config, system status
  PROMPTS    — Pre-built research and analysis templates

Tool Categories:
  Vault      — search_vault, view_thread_timeline, deep_recall,
               vault_similar, vault_stats
  Web        — web_search, extract_page, ingest_url, advanced_search
  Lifecycle  — request_planning, approve_task_completion, get_next_task
  Utility    — summarize_text
"""

import os
import sys
import json
import sqlite3
import hashlib
import datetime
import asyncio
from typing import Optional

import httpx
from bs4 import BeautifulSoup

# Conditional imports for heavy deps (graceful fallback)
try:
    import chromadb
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    DDGS_AVAILABLE = False

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Fallback for environments without FastMCP
    from mcp.server import Server as FastMCP


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
DB_PATH = os.path.join(DATA_DIR, "vault.db")
CHROMA_PATH = os.path.join(DATA_DIR, "chroma_db")
CONFIG_PATH = os.path.join(PROJECT_ROOT, ".janus_config.json")
DEFAULT_PORT = 8108
USER_AGENT = "Janus/1.0 (Sovereign Archival Intelligence)"


# ---------------------------------------------------------------------------
# Server init
# ---------------------------------------------------------------------------
app = FastMCP(
    "janus",
    instructions=(
        "Janus is a sovereign archival intelligence and knowledge service. "
        "It provides semantic search over locally stored historical archives, "
        "web search, content extraction, real-time crawling and ingestion, "
        "and task lifecycle management. All archival data stays local and "
        "sovereign. External web tools query the public internet."
    ),
)


# ---------------------------------------------------------------------------
# Lazy-loaded shared resources
# ---------------------------------------------------------------------------
_embedder = None
_collection = None
_config_cache = None


def _load_config():
    """Load Janus config from .janus_config.json."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    try:
        with open(CONFIG_PATH, "r") as f:
            _config_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _config_cache = {}
    return _config_cache


def _get_embedder():
    """Lazy-load the sentence transformer model for embeddings."""
    global _embedder
    if _embedder is None and EMBEDDINGS_AVAILABLE:
        _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedder


def _get_collection():
    """Lazy-load the ChromaDB collection for archival vectors."""
    global _collection
    if _collection is None and EMBEDDINGS_AVAILABLE:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection = client.get_or_create_collection(name="stolen_history")
    return _collection


def _get_db():
    """Open vault.db in read-only mode."""
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


# ---------------------------------------------------------------------------
# MCP Task Lifecycle State (in-memory, per-session)
# ---------------------------------------------------------------------------
task_state = {
    "current_task": None,
    "history": [],
}


# ═══════════════════════════════════════════════════════════════
#  VAULT TOOLS — Local archival search and analysis
# ═══════════════════════════════════════════════════════════════

@app.tool()
def search_vault(query: str, n_results: int = 5) -> str:
    """Semantic search across the local Janus vault. Uses embedding similarity
    to find archival content matching a concept, name, or topic.

    Args:
        query: The concept, name, or topic to search for
        n_results: Number of results to return (default 5, max 50)
    """
    embedder = _get_embedder()
    collection = _get_collection()

    if not embedder or not collection:
        return (
            "⚠ Vault search unavailable — embeddings not loaded.\n"
            "Install: pip install sentence-transformers chromadb"
        )

    n_results = min(n_results, 50)
    vector = embedder.encode(query).tolist()
    results = collection.query(query_embeddings=[vector], n_results=n_results)

    if not results["documents"][0]:
        return f"No vault results for: '{query}'"

    output = f"─── VAULT SEARCH: '{query}' ({len(results['documents'][0])} results) ───\n"
    for i, (doc, meta) in enumerate(
        zip(results["documents"][0], results["metadatas"][0]), 1
    ):
        output += (
            f"[{i}] Author: {meta.get('author', 'N/A')} "
            f"| Source: {meta.get('source', 'N/A')}\n"
            f"{doc}\n{'─' * 60}\n"
        )
    return output


@app.tool()
def view_thread_timeline(url: str) -> str:
    """Reconstruct a forum thread across all stored snapshots (live + Wayback).
    Shows how content changed over time. Deleted posts are flagged.

    Args:
        url: The URL of the forum thread to reconstruct
    """
    conn = _get_db()
    if conn is None:
        return "⚠ Vault database not found. Run the harvester first."

    try:
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT p.author, p.content_clean, p.source_type,
                   p.snapshot_date, p.is_deleted
            FROM posts p
            JOIN threads t ON p.thread_id = t.id
            WHERE t.url = ?
            ORDER BY p.post_external_id, p.snapshot_date
            """,
            (url,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return f"No thread data found for: {url}"

    output = f"─── THREAD TIMELINE: {url} ───\n"
    for author, content, source, date, is_deleted in rows:
        flag = " [DELETED]" if is_deleted else ""
        output += f"[{source.upper()} | {date}]{flag} {author}: {content}\n"
    return output


@app.tool()
def deep_recall(
    query: str, n_results: int = 10, scope: Optional[str] = None
) -> str:
    """Deep semantic retrieval with expanded context (Infinite RAG pattern).
    Retrieves more results with full metadata for comprehensive analysis.

    Args:
        query: The concept or question to deeply research
        n_results: Number of results (default 10, max 100)
        scope: Optional filter by source domain
    """
    embedder = _get_embedder()
    collection = _get_collection()

    if not embedder or not collection:
        return "⚠ Deep recall unavailable — embeddings not loaded."

    n_results = min(n_results, 100)
    vector = embedder.encode(query).tolist()

    where_filter = None
    if scope:
        where_filter = {"source": {"$contains": scope}}

    results = collection.query(
        query_embeddings=[vector],
        n_results=n_results,
        where=where_filter,
    )

    if not results["documents"][0]:
        return f"No deep recall results for: '{query}'"

    output = f"─── DEEP RECALL: '{query}' ({len(results['documents'][0])} results) ───\n"
    for i, (doc, meta) in enumerate(
        zip(results["documents"][0], results["metadatas"][0]), 1
    ):
        output += (
            f"[{i}] Author: {meta.get('author', 'N/A')} "
            f"| Source: {meta.get('source', 'N/A')}\n"
            f"{doc}\n{'─' * 60}\n"
        )
    return output


@app.tool()
def vault_similar(text_or_url: str, n_results: int = 5) -> str:
    """Find archival content semantically similar to given text or a URL's content.
    If a URL is provided, it is fetched first and its content used for matching.

    Args:
        text_or_url: Raw text to match against, or a URL to fetch and match
        n_results: Number of similar results (default 5, max 30)
    """
    embedder = _get_embedder()
    collection = _get_collection()

    if not embedder or not collection:
        return "⚠ Similarity search unavailable — embeddings not loaded."

    n_results = min(n_results, 30)
    text = text_or_url

    # If it looks like a URL, fetch and extract its content first
    if text_or_url.startswith(("http://", "https://")):
        try:
            resp = httpx.get(
                text_or_url, timeout=15, follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)[:3000]
        except Exception as exc:
            return f"Could not fetch URL for similarity: {exc}"

    vector = embedder.encode(text).tolist()
    results = collection.query(query_embeddings=[vector], n_results=n_results)

    if not results["documents"][0]:
        return "No similar content found in vault."

    output = f"─── SIMILAR CONTENT ({len(results['documents'][0])} results) ───\n"
    for i, (doc, meta) in enumerate(
        zip(results["documents"][0], results["metadatas"][0]), 1
    ):
        output += (
            f"[{i}] Author: {meta.get('author', 'N/A')} "
            f"| Source: {meta.get('source', 'N/A')}\n"
            f"{doc[:500]}...\n{'─' * 60}\n"
        )
    return output


@app.tool()
def vault_stats() -> str:
    """Get statistics about the vault: total threads, posts, sources,
    snapshot dates, and embedding count. Useful for understanding coverage."""
    output = "─── VAULT STATISTICS ───\n"

    # SQLite stats
    conn = _get_db()
    if conn:
        try:
            cur = conn.cursor()
            threads = cur.execute("SELECT COUNT(*) FROM threads").fetchone()[0]
            posts = cur.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
            sources = cur.execute(
                "SELECT source_type, COUNT(*) FROM posts GROUP BY source_type"
            ).fetchall()
            dates = cur.execute(
                "SELECT MIN(snapshot_date), MAX(snapshot_date) FROM posts"
            ).fetchone()
            deleted = cur.execute(
                "SELECT COUNT(*) FROM posts WHERE is_deleted = 1"
            ).fetchone()[0]

            output += f"Threads:    {threads}\n"
            output += f"Posts:      {posts} ({deleted} flagged deleted)\n"
            for src_type, count in sources:
                output += f"  {src_type}: {count}\n"
            if dates[0]:
                output += f"Date range: {dates[0]} → {dates[1]}\n"
        finally:
            conn.close()
    else:
        output += "SQLite vault: not found\n"

    # ChromaDB stats
    collection = _get_collection()
    if collection:
        count = collection.count()
        output += f"Embeddings: {count} vectors\n"
    else:
        output += "Embeddings: not available\n"

    return output


# ═══════════════════════════════════════════════════════════════
#  WEB TOOLS — Internet search, extraction, and ingestion
# ═══════════════════════════════════════════════════════════════

@app.tool()
def web_search(query: str, max_results: int = 10) -> str:
    """Search the public web using DuckDuckGo (no API key needed).
    Returns structured results with title, URL, and snippet.

    Args:
        query: The search query
        max_results: Maximum results to return (default 10, max 25)
    """
    max_results = min(max_results, 25)

    if DDGS_AVAILABLE:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            if not results:
                return f"No web results for: '{query}'"

            output = f"─── WEB SEARCH: '{query}' ({len(results)} results) ───\n"
            for i, r in enumerate(results, 1):
                output += (
                    f"[{i}] {r.get('title', 'No title')}\n"
                    f"    URL: {r.get('href', r.get('link', 'N/A'))}\n"
                    f"    {r.get('body', r.get('snippet', ''))}\n\n"
                )
            return output
        except Exception as exc:
            return f"Search error: {exc}"

    # Fallback: httpx + DDG HTML
    return _web_search_html(query, max_results)


def _web_search_html(query: str, max_results: int = 10) -> str:
    """Fallback web search using httpx + DuckDuckGo HTML endpoint."""
    try:
        resp = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            timeout=10,
            headers={"User-Agent": USER_AGENT},
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results = soup.select(".result__body")[:max_results]

        if not results:
            return f"No web results for: '{query}'"

        output = f"─── WEB SEARCH: '{query}' ({len(results)} results) ───\n"
        for i, result in enumerate(results, 1):
            title_el = result.select_one(".result__title a")
            snippet_el = result.select_one(".result__snippet")
            title = title_el.get_text(strip=True) if title_el else "No title"
            url = title_el.get("href", "N/A") if title_el else "N/A"
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            output += f"[{i}] {title}\n    URL: {url}\n    {snippet}\n\n"
        return output
    except Exception as exc:
        return f"Search error: {exc}"


@app.tool()
def advanced_search(
    query: str,
    max_results: int = 10,
    region: str = "wt-wt",
    time_range: Optional[str] = None,
    site: Optional[str] = None,
) -> str:
    """Advanced web search with filtering options. Supports region, time range,
    and site-specific filtering.

    Args:
        query: The search query
        max_results: Maximum results (default 10, max 25)
        region: Region code (default 'wt-wt' = worldwide). Examples: us-en, uk-en, de-de
        time_range: Optional time filter: 'd' (day), 'w' (week), 'm' (month), 'y' (year)
        site: Optional domain to restrict search (e.g. 'stolenhistory.net')
    """
    max_results = min(max_results, 25)

    # Build enhanced query with site filter
    search_query = query
    if site:
        search_query = f"site:{site} {query}"

    if not DDGS_AVAILABLE:
        return _web_search_html(search_query, max_results)

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(
                search_query,
                max_results=max_results,
                region=region,
                timelimit=time_range,
            ))

        if not results:
            return f"No results for advanced search: '{search_query}'"

        output = f"─── ADVANCED SEARCH: '{query}' ───\n"
        if site:
            output += f"Site: {site}\n"
        if time_range:
            output += f"Time: {time_range}\n"
        output += f"Region: {region} | {len(results)} results\n\n"

        for i, r in enumerate(results, 1):
            output += (
                f"[{i}] {r.get('title', 'No title')}\n"
                f"    URL: {r.get('href', r.get('link', 'N/A'))}\n"
                f"    {r.get('body', r.get('snippet', ''))}\n\n"
            )
        return output
    except Exception as exc:
        return f"Advanced search error: {exc}"


@app.tool()
def extract_page(url: str, max_chars: int = 8000) -> str:
    """Extract clean readable text from any URL. Strips navigation, scripts,
    ads, and boilerplate — keeps only the meaningful content.

    Args:
        url: The URL to extract content from
        max_chars: Maximum characters to return (default 8000)
    """
    try:
        resp = httpx.get(
            url, timeout=20, follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
    except Exception as exc:
        return f"Failed to fetch: {exc}"

    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove non-content elements
    for tag in soup(
        ["script", "style", "nav", "header", "footer", "aside",
         "form", "iframe", "noscript", "svg", "button"]
    ):
        tag.decompose()

    # Try to find main content area
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_="content")
        or soup.find("body")
    )
    if main is None:
        return "Could not extract content from page."

    text = main.get_text(separator="\n", strip=True)

    # Extract metadata
    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else "Unknown"

    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc = meta_desc.get("content", "") if meta_desc else ""

    meta_author = soup.find("meta", attrs={"name": "author"})
    author = meta_author.get("content", "") if meta_author else ""

    # Extract links from the page
    links = []
    for a in (main.find_all("a", href=True) if main else [])[:20]:
        href = a.get("href", "")
        link_text = a.get_text(strip=True)
        if href.startswith("http") and link_text:
            links.append(f"  • {link_text}: {href}")

    output = f"─── PAGE: {title_text} ───\n"
    if author:
        output += f"Author: {author}\n"
    if desc:
        output += f"Description: {desc}\n"
    output += f"URL: {url}\n"
    output += f"{'─' * 60}\n"
    output += text[:max_chars]
    if len(text) > max_chars:
        output += f"\n...[truncated at {max_chars} of {len(text)} chars]"

    if links:
        output += f"\n\n─── LINKS ({len(links)}) ───\n"
        output += "\n".join(links)

    return output


@app.tool()
def ingest_url(
    url: str,
    depth: int = 1,
    search_after: Optional[str] = None,
) -> str:
    """Crawl a URL, ingest its content into the local vault, and optionally
    search the freshly ingested data. Turns Janus into a real-time research
    tool — crawl now, search immediately.

    Args:
        url: The URL to crawl and ingest into the vault
        depth: Number of link-follow levels (1 = single page, 2 = follow links)
        search_after: Optional query to run on the freshly ingested content
    """
    embedder = _get_embedder()
    collection = _get_collection()

    if not embedder or not collection:
        return "⚠ Ingestion unavailable — embeddings not loaded."

    # Step 1: Fetch the page
    try:
        resp = httpx.get(
            url, timeout=20, follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
    except Exception as exc:
        return f"Failed to crawl: {exc}"

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "aside"]):
        tag.decompose()

    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else url
    text = soup.get_text(separator="\n", strip=True)

    if not text:
        return f"No text content at {url}"

    # Step 2: Collect child URLs for depth > 1
    child_texts = []
    if depth > 1:
        child_urls = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and len(child_urls) < 10:
                child_urls.add(href)
        for child_url in child_urls:
            try:
                cr = httpx.get(
                    child_url, timeout=10, follow_redirects=True,
                    headers={"User-Agent": USER_AGENT},
                )
                cs = BeautifulSoup(cr.text, "html.parser")
                for tag in cs(["script", "style", "nav", "footer"]):
                    tag.decompose()
                ct = cs.get_text(separator="\n", strip=True)
                if ct:
                    child_texts.append((child_url, ct))
            except Exception:
                continue

    # Step 3: Chunk and ingest into ChromaDB
    all_pages = [(url, text)] + child_texts
    total_chunks = 0

    for page_url, page_text in all_pages:
        chunk_size = 1000
        chunks = [page_text[i : i + chunk_size] for i in range(0, len(page_text), chunk_size)]

        ids = []
        documents = []
        metadatas = []
        for i, chunk in enumerate(chunks):
            doc_id = f"ingest_{hashlib.md5(page_url.encode()).hexdigest()[:12]}_{i}"
            ids.append(doc_id)
            documents.append(chunk)
            metadatas.append({
                "source": page_url,
                "author": "janus_ingest",
                "title": title_text,
                "chunk_index": i,
                "total_chunks": len(chunks),
                "ingested_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            })

        embeddings = [embedder.encode(doc).tolist() for doc in documents]
        collection.upsert(
            ids=ids, documents=documents,
            metadatas=metadatas, embeddings=embeddings,
        )
        total_chunks += len(chunks)

    output = f"─── INGESTED: {title_text} ───\n"
    output += f"URL: {url}\n"
    output += f"Pages: {len(all_pages)} | Chunks: {total_chunks} | Chars: {sum(len(t) for _, t in all_pages)}\n"

    # Step 4: Optionally search freshly ingested content
    if search_after:
        vector = embedder.encode(search_after).tolist()
        results = collection.query(query_embeddings=[vector], n_results=5)
        output += f"\n─── SEARCH: '{search_after}' ───\n"
        for i, (doc, meta) in enumerate(
            zip(results["documents"][0], results["metadatas"][0]), 1
        ):
            output += f"[{i}] {meta.get('source', 'N/A')}: {doc[:400]}...\n"

    return output


@app.tool()
def summarize_text(text: str, max_sentences: int = 5) -> str:
    """Extract the most important sentences from a block of text using
    extractive summarization (frequency-based, no LLM needed).

    Args:
        text: The text to summarize
        max_sentences: Number of key sentences to extract (default 5)
    """
    # Simple extractive summarization using sentence scoring
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) <= max_sentences:
        return text

    # Score sentences by word frequency
    words = re.findall(r"\w+", text.lower())
    freq = {}
    for w in words:
        if len(w) > 3:  # Skip short words
            freq[w] = freq.get(w, 0) + 1

    scored = []
    for i, s in enumerate(sentences):
        score = sum(freq.get(w, 0) for w in re.findall(r"\w+", s.lower()))
        # Boost early sentences (usually more important)
        score *= 1.0 + (0.5 / (i + 1))
        scored.append((score, i, s))

    # Pick top sentences, sorted by original position
    top = sorted(scored, key=lambda x: x[0], reverse=True)[:max_sentences]
    top = sorted(top, key=lambda x: x[1])

    output = "─── SUMMARY ───\n"
    output += " ".join(s for _, _, s in top)
    output += f"\n\n[Extracted {max_sentences} of {len(sentences)} sentences]"
    return output


# ═══════════════════════════════════════════════════════════════
#  TASK LIFECYCLE TOOLS — Planning and completion tracking
# ═══════════════════════════════════════════════════════════════

@app.tool()
def request_planning() -> str:
    """Start the planning phase for a new task. Creates a tracked task entry."""
    task_id = len(task_state["history"]) + 1
    task_entry = {
        "id": task_id,
        "phase": "planning",
        "status": "active",
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "completed_at": None,
    }
    task_state["current_task"] = task_entry
    task_state["history"].append(task_entry)
    return (
        f"Planning initiated for Task #{task_id}. "
        f"Phase: planning | Status: active. "
        f"Complete with approve_task_completion when finished."
    )


@app.tool()
def approve_task_completion() -> str:
    """Mark the current task as completed with a timestamp."""
    current = task_state.get("current_task")
    if not current or current["status"] == "completed":
        return "No active task. Use request_planning to start one."

    current["status"] = "completed"
    current["phase"] = "done"
    current["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    task_state["current_task"] = None
    done = sum(1 for t in task_state["history"] if t["status"] == "completed")
    return (
        f"Task #{current['id']} completed. "
        f"Total: {done}/{len(task_state['history'])}. "
        f"Use get_next_task or request_planning to continue."
    )


@app.tool()
def get_next_task() -> str:
    """Get the next pending task or overall task status."""
    current = task_state.get("current_task")
    if current and current["status"] == "active":
        return (
            f"Task #{current['id']} still active (phase: {current['phase']}). "
            f"Complete it first with approve_task_completion."
        )
    pending = [t for t in task_state["history"] if t["status"] == "active"]
    if pending:
        task_state["current_task"] = pending[0]
        return f"Resuming Task #{pending[0]['id']} (phase: {pending[0]['phase']})."

    done = sum(1 for t in task_state["history"] if t["status"] == "completed")
    return f"No pending tasks. {done} completed. Use request_planning to start."


# ═══════════════════════════════════════════════════════════════
#  MCP RESOURCES — Metadata and status exposed to clients
# ═══════════════════════════════════════════════════════════════

@app.resource("janus://status")
def get_status() -> str:
    """Current Janus server status and capabilities."""
    config = _load_config()
    status = {
        "server": "janus",
        "version": "1.0.0",
        "embeddings_available": EMBEDDINGS_AVAILABLE,
        "ddgs_available": DDGS_AVAILABLE,
        "vault_db_exists": os.path.exists(DB_PATH),
        "chroma_db_exists": os.path.exists(CHROMA_PATH),
        "config_loaded": bool(config),
        "active_task": task_state.get("current_task"),
        "completed_tasks": sum(
            1 for t in task_state["history"] if t["status"] == "completed"
        ),
    }
    return json.dumps(status, indent=2)


@app.resource("janus://config")
def get_config() -> str:
    """Current Janus configuration."""
    config = _load_config()
    # Mask any API keys
    safe = {k: ("***" if "key" in k.lower() else v) for k, v in config.items()}
    return json.dumps(safe, indent=2)


# ═══════════════════════════════════════════════════════════════
#  MCP PROMPTS — Pre-built research templates
# ═══════════════════════════════════════════════════════════════

@app.prompt()
def research_topic(topic: str) -> str:
    """Pre-built prompt for deep research on a historical topic.
    Combines vault search + web search for comprehensive coverage."""
    return (
        f"Research the topic: '{topic}'\n\n"
        f"1. First search the local vault using search_vault('{topic}')\n"
        f"2. Then do a deep_recall('{topic}', n_results=10) for expanded context\n"
        f"3. Search the web using web_search('{topic}') for current information\n"
        f"4. If relevant URLs found, use extract_page() to get full content\n"
        f"5. Use vault_similar() to find related archival material\n"
        f"6. Synthesize all findings into a comprehensive analysis\n"
    )


@app.prompt()
def ingest_and_analyze(url: str) -> str:
    """Pre-built prompt to ingest a URL and analyze its content relative
    to existing vault knowledge."""
    return (
        f"Analyze and ingest: {url}\n\n"
        f"1. Use extract_page('{url}') to get the content\n"
        f"2. Use ingest_url('{url}') to add it to the vault\n"
        f"3. Use vault_similar() with the page content to find related material\n"
        f"4. Compare the new content with existing vault knowledge\n"
        f"5. Identify any contradictions or corroborations\n"
    )


@app.prompt()
def compare_timelines(thread_url: str) -> str:
    """Pre-built prompt to analyze content changes in a thread over time."""
    return (
        f"Timeline analysis for: {thread_url}\n\n"
        f"1. Use view_thread_timeline('{thread_url}') to see all snapshots\n"
        f"2. Identify which posts were deleted and when\n"
        f"3. Note any content that changed between snapshots\n"
        f"4. Use search_vault() to find related discussions\n"
        f"5. Build a narrative of how the thread evolved\n"
    )


# ═══════════════════════════════════════════════════════════════
#  Entry point — dual transport support
# ═══════════════════════════════════════════════════════════════

def main():
    """Run the Janus MCP server in stdio or HTTP mode."""
    if "--http" in sys.argv or "--streamable-http" in sys.argv:
        port = DEFAULT_PORT
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])

        print(f"┌──────────────────────────────────────────────┐")
        print(f"│  Janus MCP Server — Streamable HTTP          │")
        print(f"│  http://127.0.0.1:{port}/mcp{' ' * (20 - len(str(port)))}│")
        print(f"├──────────────────────────────────────────────┤")
        print(f"│  Tools:     13                               │")
        print(f"│  Resources: 2                                │")
        print(f"│  Prompts:   3                                │")
        print(f"│  Vault DB:  {'yes' if os.path.exists(DB_PATH) else 'no ':3s}                            │")
        print(f"│  Embeddings: {'yes' if EMBEDDINGS_AVAILABLE else 'no ':3s}                           │")
        print(f"└──────────────────────────────────────────────┘")

        app.settings.port = port
        app.settings.host = "127.0.0.1"
        app.run(transport="streamable-http")
    else:
        # stdio mode — local use (Claude Desktop, run_agent.py, etc.)
        app.run(transport="stdio")


if __name__ == "__main__":
    main()
