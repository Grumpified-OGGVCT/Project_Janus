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
_http_client = httpx.Client(timeout=20, follow_redirects=True, limits=httpx.Limits(max_keepalive_connections=5, max_connections=10))


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
        _embedder = SentenceTransformer("nomic-embed-text")
    return _embedder


def _get_collection():
    """Lazy-load the ChromaDB collection for archival vectors."""
    global _collection
    if _collection is None and EMBEDDINGS_AVAILABLE:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection = client.get_or_create_collection(name=_active_collection_name)
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


_active_collection_name = "stolen_history_nomic"

@app.tool()
def list_collections() -> str:
    """List all available local ChromaDB collections (Websets)."""
    if not EMBEDDINGS_AVAILABLE:
        return "ChromaDB not available."
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collections = client.list_collections()
        return f"Collections: {', '.join([c.name for c in collections])}\nActive: {_active_collection_name}"
    except Exception as e:
        return f"Error listing collections: {e}"

@app.tool()
def switch_collection(name: str) -> str:
    """Switch the active ChromaDB collection used for search and ingest."""
    global _active_collection_name, _collection
    if not EMBEDDINGS_AVAILABLE:
        return "ChromaDB not available."
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        # Verify it exists
        client.get_collection(name=name)
        _active_collection_name = name
        _collection = None # Force reload
        return f"Switched active collection to '{name}'."
    except Exception as e:
        return f"Collection '{name}' not found or error: {e}"

@app.tool()
def create_collection(name: str) -> str:
    """Create a new isolated ChromaDB collection for a specific research topic."""
    if not EMBEDDINGS_AVAILABLE:
        return "ChromaDB not available."
    try:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        client.get_or_create_collection(name=name)
        return f"Created collection '{name}'. Use switch_collection to use it."
    except Exception as e:
        return f"Error creating collection: {e}"

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
            resp = _http_client.get(
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
def generate_knowledge_graph(topic: Optional[str] = None, max_nodes: int = 20) -> str:
    """Generates a JSON representation of a knowledge graph for visual rendering.
    Maps out relationships between documents in the active Webset based on semantic similarity.

    Args:
        topic: Optional topic to center the graph around. If None, maps the whole vault.
        max_nodes: Maximum number of nodes (documents) to return.
    """
    collection = _get_collection()
    if not collection:
        return "{\"error\": \"ChromaDB not available\"}"

    try:
        if topic:
            embedder = _get_embedder()
            if not embedder:
                return "{\"error\": \"Embeddings not available\"}"
            vector = embedder.encode(topic).tolist()
            results = collection.query(query_embeddings=[vector], n_results=max_nodes, include=["metadatas", "distances", "documents", "embeddings"])
            if not results["ids"][0]:
                return "{\"nodes\": [], \"edges\": []}"
            ids = results["ids"][0]
            metadatas = results["metadatas"][0]
        else:
            results = collection.get(limit=max_nodes, include=["metadatas", "embeddings"])
            ids = results["ids"]
            metadatas = results["metadatas"]

        nodes = []
        for i, doc_id in enumerate(ids):
            meta = metadatas[i] if metadatas and i < len(metadatas) else {}
            title = meta.get("title", doc_id)
            source = meta.get("source", "unknown")
            nodes.append({"id": doc_id, "label": title[:30] + "...", "source": source})

        # Generate edges based on actual semantic similarity and shared sources
        edges = []
        import numpy as np
        from numpy.linalg import norm

        # If we have embeddings, compute semantic similarity edges
        embeddings = results.get("embeddings", [])
        if embeddings and len(embeddings) > 0:
            embeddings_array = np.array(embeddings[0] if topic else embeddings)

            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    # 1. Check for shared sources
                    if nodes[i]["source"] == nodes[j]["source"] and nodes[i]["source"] != "unknown":
                        edges.append({"source": nodes[i]["id"], "target": nodes[j]["id"], "type": "shared_source"})

                    # 2. Check semantic similarity
                    vec1 = embeddings_array[i]
                    vec2 = embeddings_array[j]

                    # Compute cosine similarity
                    if norm(vec1) > 0 and norm(vec2) > 0:
                        sim = np.dot(vec1, vec2) / (norm(vec1) * norm(vec2))
                        # Create an edge if similarity is above a certain threshold (e.g., 0.75)
                        if sim > 0.75:
                            edges.append({
                                "source": nodes[i]["id"],
                                "target": nodes[j]["id"],
                                "type": "semantic_link",
                                "weight": float(sim)
                            })
        else:
            # Fallback to just metadata-based edges if embeddings aren't included in the query
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    if nodes[i]["source"] == nodes[j]["source"] and nodes[i]["source"] != "unknown":
                        edges.append({"source": nodes[i]["id"], "target": nodes[j]["id"], "type": "shared_source"})

        import json
        return json.dumps({"nodes": nodes, "edges": edges})
    except Exception as e:
        import json
        return json.dumps({"error": str(e)})

@app.tool()
def save_knowledge_graph(filename: str = "knowledge_graph.json", topic: Optional[str] = None, max_nodes: int = 50) -> str:
    """Headlessly generate and save the 3D knowledge graph structure to a file for persistent tracking.

    Args:
        filename: Name of the file to save (e.g., 'graph.json').
        topic: Optional topic to center the graph around.
        max_nodes: Maximum number of nodes to include.
    """
    import json
    import os

    graph_data_str = generate_knowledge_graph(topic=topic, max_nodes=max_nodes)

    try:
        graph_data = json.loads(graph_data_str)
        if "error" in graph_data:
            return f"Failed to generate graph: {graph_data['error']}"

        filepath = os.path.join(DATA_DIR, filename)
        with open(filepath, 'w') as f:
            json.dump(graph_data, f, indent=2)

        return f"Successfully saved knowledge graph ({len(graph_data.get('nodes', []))} nodes, {len(graph_data.get('edges', []))} edges) to {filepath}"
    except Exception as e:
        return f"Error saving graph: {e}"

@app.tool()
@app.tool()
def add_knowledge_node(name: str, type: str, content: str) -> str:
    """Explicitly add a specific knowledge node (entity) to the graph. (Memory MCP Style)

    Args:
        name: The unique identifier/name of the node (e.g. 'Project_Janus_Core').
        type: The category of the node (e.g. 'Concept', 'Person', 'CodeFile').
        content: The detailed information stored in this node.
    """
    embedder = _get_embedder()
    collection = _get_collection()
    if not embedder or not collection:
        return "⚠ Graph mutation unavailable — embeddings not loaded."

    import hashlib
    doc_id = f"node_{hashlib.md5(name.encode()).hexdigest()[:12]}"
    vector = embedder.encode(content).tolist()

    collection.upsert(
        ids=[doc_id],
        documents=[content],
        metadatas=[{"source": f"memory_{type}", "title": name, "author": "janus_memory", "type": "explicit_node"}],
        embeddings=[vector]
    )
    return f"Added/Updated node: {name} ({type})"

@app.tool()
def index_local_codebase() -> str:
    """Automatically crawls and indexes the entire Project Janus codebase into the active knowledge graph.
    This allows the Infinite RAG and autonomous loops to understand the system's own architecture.
    """
    import os
    embedder = _get_embedder()
    collection = _get_collection()
    if not embedder or not collection:
        return "⚠ Codebase indexing unavailable — embeddings not loaded."

    src_dir = os.path.join(PROJECT_ROOT, "src")
    if not os.path.exists(src_dir):
        return "Source directory not found."

    indexed_files = 0
    total_chunks = 0

    for root, _, files in os.walk(src_dir):
        for file in files:
            if not file.endswith(".py"):
                continue
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, PROJECT_ROOT)

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    code = f.read()

                chunk_size = 1500
                chunks = [code[i:i+chunk_size] for i in range(0, len(code), chunk_size)]

                ids = []
                docs = []
                metas = []

                for i, chunk in enumerate(chunks):
                    doc_id = f"code_{rel_path.replace('/', '_')}_{i}"
                    ids.append(doc_id)
                    docs.append(f"File: {rel_path}\n\n{chunk}")
                    metas.append({
                        "source": rel_path,
                        "title": file,
                        "author": "codebase_indexer",
                        "type": "code"
                    })

                if chunks:
                    embeddings = [embedder.encode(doc).tolist() for doc in docs]
                    collection.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)
                    indexed_files += 1
                    total_chunks += len(chunks)

            except Exception as e:
                continue

    return f"Successfully indexed codebase: {indexed_files} Python files across {total_chunks} chunks."

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
def web_search(
    query: str,
    max_results: int = 10,
    include_domains: list[str] = None,
    exclude_domains: list[str] = None,
    time_range: str = None
) -> str:
    """Search the public web using DuckDuckGo (no API key needed).
    Returns structured results with title, URL, and snippet.

    Args:
        query: The search query
        max_results: Maximum results to return (default 10, max 25)
        include_domains: List of domains to whitelist (e.g. ['arxiv.org'])
        exclude_domains: List of domains to blacklist
        time_range: 'd' (day), 'w' (week), 'm' (month), 'y' (year)
    """
    if include_domains:
        query += " " + " OR ".join(f"site:{d}" for d in include_domains)
    if exclude_domains:
        query += " " + " ".join(f"-site:{d}" for d in exclude_domains)
    max_results = min(max_results, 25)

    if DDGS_AVAILABLE:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results, timelimit=time_range))
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
        resp = _http_client.get(
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
def search_with_contents(
    query: str,
    extract_text: bool = True,
    max_results: int = 3,
    include_domains: list[str] = None,
    exclude_domains: list[str] = None,
    time_range: str = None,
    summarize: bool = False
) -> str:
    """Combined web search and content extraction.
    Searches the web and automatically extracts the full text of the top results.

    Args:
        query: The search query
        extract_text: Whether to extract full page text (default True)
        max_results: Maximum results to fetch and extract (default 3, max 5)
        include_domains: List of domains to whitelist (e.g. ['arxiv.org'])
        exclude_domains: List of domains to blacklist
        time_range: 'd' (day), 'w' (week), 'm' (month), 'y' (year)
        summarize: If True, uses summarize_text to shorten the content.
    """
    if include_domains:
        query += " " + " OR ".join(f"site:{d}" for d in include_domains)
    if exclude_domains:
        query += " " + " ".join(f"-site:{d}" for d in exclude_domains)
    max_results = min(max_results, 5)

    urls = []

    # Do the search
    if DDGS_AVAILABLE:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results, timelimit=time_range))
            for r in results:
                url = r.get('href', r.get('link'))
                if url:
                    urls.append((r.get('title', 'No title'), url, r.get('body', r.get('snippet', ''))))
        except Exception as exc:
            return f"Search error: {exc}"
    else:
        # Fallback HTML search
        try:
            resp = _http_client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                timeout=10,
                headers={"User-Agent": USER_AGENT},
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            results = soup.select(".result__body")[:max_results]
            for result in results:
                title_el = result.select_one(".result__title a")
                snippet_el = result.select_one(".result__snippet")
                if title_el:
                    url = title_el.get("href")
                    if url:
                        urls.append((
                            title_el.get_text(strip=True),
                            url,
                            snippet_el.get_text(strip=True) if snippet_el else ""
                        ))
        except Exception as exc:
            return f"Search error: {exc}"

    if not urls:
        return f"No web results found for: '{query}'"

    output = f"─── SEARCH WITH CONTENTS: '{query}' ({len(urls)} results) ───\n\n"

    for i, (title, url, snippet) in enumerate(urls, 1):
        output += f"[{i}] {title}\nURL: {url}\n"
        if not extract_text:
            output += f"Snippet: {snippet}\n\n"
            continue

        # Extract the page content sequentially (parallel requires async/threads which adds complexity)
        content_text = extract_page(url, max_chars=10000)
        if summarize:
            content_text = summarize_text(content_text, max_sentences=5)
        output += f"--- Extracted Content ---\n{content_text}\n"
        output += f"-------------------------\n\n"

    return output

@app.tool()
def auto_search(query: str, strategy: str = "auto") -> str:
    """Smart routing search that decides whether to search the vault, the web, or both.

    Args:
        query: The search query
        strategy: 'auto' (decides based on vault hits), 'vault_only', 'web_only', or 'infinite_rag'
    """
    if strategy == "vault_only":
        return search_vault(query, n_results=5)

    if strategy == "infinite_rag":
        return deep_recall(query, n_results=10)

    if strategy == "web_only":
        return web_search(query, max_results=5)

    if strategy == "auto":
        # Check vault first
        vault_res = search_vault(query, n_results=3)
        if "No matching documents" not in vault_res and "embeddings not loaded" not in vault_res:
            # Check if vault has good results (e.g. > 100 chars of actual content)
            if len(vault_res) > 200:
                output = f"─── AUTO SEARCH: Used Vault ───\n{vault_res}\n"
                return output

        # If vault is empty/poor, fallback to web
        web_res = web_search(query, max_results=3)
        output = f"─── AUTO SEARCH: Used Web (Vault was empty) ───\n{web_res}\n"
        return output

    return f"Invalid strategy: {strategy}. Use 'auto', 'vault_only', 'web_only', or 'infinite_rag'."

@app.tool()
def iterative_reasoning_loop(prompt: str, max_iterations: int = 2) -> str:
    """Mimics the deep reasoning loops of an advanced iterative model (like o1).
    It breaks down a complex prompt, retrieves context from both the local Vault
    and the live Web, evaluates the findings, and synthesizes a final reasoned output.

    Args:
        prompt: The complex question or task requiring deep reasoning.
        max_iterations: How many search-evaluate cycles to run.
    """
    output = f"─── 🧠 ITERATIVE REASONING LOOP ───\n"
    output += f"Prompt: '{prompt}'\n\n"

    # Step 1: Hypothesis & Breakdown
    output += "■ STEP 1: Problem Decomposition\n"
    keywords = [w for w in prompt.split() if len(w) > 4]
    core_concept = " ".join(keywords[:3]) if keywords else prompt
    output += f"Identified core concepts: {core_concept}\n\n"

    context_gathered = ""

    # Step 2: Iterative Retrieval
    for i in range(1, max_iterations + 1):
        output += f"■ STEP 2.{i}: Context Retrieval (Iteration {i})\n"

        # Local Vault
        vault_data = search_vault(core_concept, n_results=3)
        if "No matching documents" not in vault_data:
            output += " -> Discovered relevant local historical data.\n"
            context_gathered += f"\n[VAULT]: {vault_data[:500]}..."
        else:
            output += " -> Local historical data is insufficient.\n"

        # Live Web
        web_data = web_search(core_concept, max_results=2)
        if "No web results" not in web_data:
            output += " -> Gathered live web context.\n"
            context_gathered += f"\n[WEB]: {web_data[:500]}..."

        # Tweak concept for next iteration if needed
        core_concept += " analysis"

    # Step 3: Synthesis
    output += "\n■ STEP 3: Synthesis & Conclusion\n"
    if len(context_gathered) < 50:
        output += "Insufficient data gathered to form a robust conclusion.\n"
    else:
        output += f"Processed {len(context_gathered)} characters of context across Vault and Web.\n"
        # We use summarize_text to act as the "distillation" of the context
        distilled = summarize_text(context_gathered, max_sentences=6)
        output += f"\n=== REASONED OUTPUT ===\n{distilled}\n=======================\n"

    return output

@app.tool()
def autonomous_research_loop(topic: str, breadth: int = 2, depth: int = 1) -> str:
    """Multi-step research loop. It searches the vault, searches the web, extracts pages,
    and ingests them to build a comprehensive context base for the given topic.

    Args:
        topic: The research topic
        breadth: Number of different web search queries to try (max 3)
        depth: Number of top results to extract and ingest per query (max 3)
    """
    breadth = min(breadth, 3)
    depth = min(depth, 3)

    output = f"─── AUTONOMOUS RESEARCH LOOP: '{topic}' ───\n"

    # 1. Check local knowledge first
    output += "1. Checking local vault (Infinite RAG)\n"
    vault_res = deep_recall(topic, n_results=5)
    output += f"Local knowledge found.\n" if "Failed" not in vault_res and len(vault_res) > 200 else "Local knowledge is sparse.\n"

    # 2. Web searches based on breadth
    queries = [topic]
    if breadth > 1:
        queries.append(f"{topic} analysis OR overview")
    if breadth > 2:
        queries.append(f"{topic} latest developments")

    extracted_urls = set()
    ingested_count = 0

    for i, q in enumerate(queries, 1):
        output += f"\n--- Query {i}/{len(queries)}: '{q}' ---\n"

        # Web Search
        if DDGS_AVAILABLE:
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(q, max_results=depth))
            except Exception:
                results = []
        else:
            try:
                resp = _http_client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": q},
                    timeout=10,
                    headers={"User-Agent": USER_AGENT},
                )
                soup = BeautifulSoup(resp.text, "html.parser")
                raw_results = soup.select(".result__body")[:depth]
                results = []
                for result in raw_results:
                    title_el = result.select_one(".result__title a")
                    if title_el and title_el.get("href"):
                        results.append({'href': title_el.get("href")})
            except Exception:
                results = []

        # Extract and Ingest
        for r in results:
            url = r.get('href', r.get('link'))
            if url and url not in extracted_urls:
                extracted_urls.add(url)
                # Ingest into active webset
                ingest_res = ingest_url(url, depth=1)
                if "Failed" not in ingest_res and "unavailable" not in ingest_res:
                    ingested_count += 1
                    output += f"Ingested: {url}\n"
                else:
                    output += f"Failed to ingest: {url}\n"

    output += f"\nResearch loop complete. Ingested {ingested_count} new documents into the active Webset.\n"
    output += f"Use auto_search('{topic}', strategy='infinite_rag') or deep_recall('{topic}') to synthesize the combined knowledge."
    return output

@app.tool()
def extract_page(url: str, max_chars: int = 8000) -> str:
    """Extract clean readable text from any URL. Strips navigation, scripts,
    ads, and boilerplate — keeps only the meaningful content.

    Args:
        url: The URL to extract content from
        max_chars: Maximum characters to return (default 8000)
    """
    try:
        resp = _http_client.get(
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
def crawl_and_index(url: str, depth: int = 1, follow_same_domain: bool = True) -> str:
    """Deep recursive crawl of a site to ingest into the active webset (collection).
    Skips already indexed URLs based on ChromaDB metadata checks.

    Args:
        url: The starting URL
        depth: How many levels of links to follow (max 2)
        follow_same_domain: Restrict to links on the same domain
    """
    depth = min(depth, 2)
    collection = _get_collection()
    if not collection:
        return "⚠ Ingestion unavailable — embeddings not loaded."

    try:
        from urllib.parse import urlparse, urljoin
    except ImportError:
        pass

    base_domain = urlparse(url).netloc

    visited = set()
    to_visit = [(url, 0)]

    ingested_count = 0
    skipped_count = 0

    while to_visit:
        curr_url, curr_depth = to_visit.pop(0)

        if curr_url in visited:
            continue
        visited.add(curr_url)

        # Check if already indexed
        try:
            url_hash = f"ingest_{hashlib.md5(curr_url.encode()).hexdigest()[:12]}_0"
            existing = collection.get(ids=[url_hash])
            if existing and existing.get('ids') and len(existing['ids']) > 0:
                skipped_count += 1
                continue
        except Exception:
            pass

        # Call the actual ingest function for this page
        ingest_res = ingest_url(curr_url, depth=1)
        if "Failed" not in ingest_res and "unavailable" not in ingest_res:
            ingested_count += 1

        if curr_depth < depth:
            try:
                resp = _http_client.get(
                    curr_url, timeout=10, follow_redirects=True,
                    headers={"User-Agent": USER_AGENT},
                )
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    full_url = urljoin(curr_url, href)
                    if full_url.startswith("http"):
                        link_domain = urlparse(full_url).netloc
                        if follow_same_domain and link_domain != base_domain:
                            continue
                        to_visit.append((full_url, curr_depth + 1))
            except Exception:
                pass

    return f"Crawled {url} at depth {depth}. Ingested {ingested_count} new pages. Skipped {skipped_count} already indexed pages."

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
        resp = _http_client.get(
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
                cr = _http_client.get(
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
def janus_help() -> str:
    """Master reference for Project Janus capabilities.
    Returns a structured guide to all available tools and powerful 'super-combo' workflows
    you can execute to achieve complex tasks. Use this when you need ideas on how to proceed.
    """
    return """
╔══════════════════════════════════════════════════════════════════╗
║                    PROJECT JANUS — MASTER HELP                   ║
╚══════════════════════════════════════════════════════════════════╝

─── CORE TOOL CATEGORIES ───

1. VAULT & MEMORY (Local Knowledge)
   - search_vault()            : Standard semantic search of local archives.
   - deep_recall()             : Infinite RAG capability for massive context retrieval.
   - vault_similar()           : Find archival material similar to a specific URL/text.
   - get_vault_stats()         : Check DB size and metadata.
   - list_collections()        : View available isolated knowledge bases (Websets).
   - switch_collection()       : Change the active local knowledge base.

2. WEB INTELLIGENCE (Live Discovery)
   - web_search()              : DuckDuckGo search (supports domains, time limits).
   - advanced_search()         : Granular regional/site search.
   - search_with_contents()    : Search AND instantly extract full text/summaries.
   - auto_search()             : Smart-routes between Vault and Web depending on knowledge.

3. INGESTION & CRAWLING (Building Knowledge)
   - extract_page()            : Pull clean, readable text from any URL.
   - ingest_url()              : Save a URL (and optionally its children) to the Vault.
   - crawl_and_index()         : Deep recursive background crawler with Chroma deduplication.
   - autonomous_research_loop(): Super-combo: searches web, extracts, and ingests automatically.
   - iterative_reasoning_loop(): Super-combo: mimics o1-style iterative reasoning loops.

4. TASK LIFECYCLE (Planning)
   - request_planning()        : Start a new objective.
   - approve_task_completion() : Mark a task as done.
   - get_next_task()           : Check what's pending.


─── 🚀 SUPER-COMBOS & WORKFLOWS ───

A) The "Deep Dive" (Build an instant knowledge base):
   1. create_collection('new_topic') -> switch_collection('new_topic')
   2. autonomous_research_loop('my topic', breadth=3, depth=3)
   3. auto_search('my topic details', strategy='infinite_rag')

B) The "Fact Checker" (Verify web claims against archives):
   1. extract_page('news_url')
   2. vault_similar(extracted_text)
   3. Compare the live text against the historical Vault hits.

C) The "Cognitive Emulator" (Deep reasoning task):
   1. iterative_reasoning_loop('complex query', max_iterations=3)
   2. Use the output as highly synthesized, grounded context.

D) The "Domain Mirror" (Archive a whole site):
   1. crawl_and_index('https://example.com', depth=2, follow_same_domain=True)
   2. get_vault_stats() to verify chunk ingestion.
"""

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
