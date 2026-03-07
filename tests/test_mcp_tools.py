import sqlite3
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# conftest.py has already mocked mcp/chromadb/sentence_transformers.
# We can now safely import server.py.
import src.mcp_server.server as srv

SCHEMA = Path(__file__).parent.parent / "src" / "vault" / "schema.sql"


def _make_test_db(tmp_path: str) -> str:
    db_path = os.path.join(tmp_path, "vault.db")
    conn = sqlite3.connect(db_path)
    with open(SCHEMA) as fh:
        conn.executescript(fh.read())
    conn.execute(
        "INSERT INTO threads (id, url, title) VALUES (1, 'https://example.com/t/1', 'Test Thread')"
    )
    conn.execute(
        """
        INSERT INTO posts
            (thread_id, post_external_id, author, content_clean,
             source_type, snapshot_date, content_hash)
        VALUES (1, 'p1', 'Alice', 'Ancient knowledge here', 'live', '2024-01-01', 'abc123')
        """
    )
    conn.commit()
    conn.close()
    return db_path


# ─── Vault Tool Tests ─────────────────────────────────────

def test_view_thread_timeline_returns_post(tmp_path, monkeypatch):
    """view_thread_timeline should return matching post data."""
    db_path = _make_test_db(str(tmp_path))
    monkeypatch.setattr(
        srv, '_get_db',
        lambda: sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    )

    result = srv.view_thread_timeline(url="https://example.com/t/1")

    assert "Alice" in result
    assert "Ancient knowledge here" in result
    assert "THREAD TIMELINE" in result


def test_view_thread_timeline_unknown_url(tmp_path, monkeypatch):
    """Unknown URL should return 'No thread data found' message."""
    db_path = _make_test_db(str(tmp_path))
    monkeypatch.setattr(
        srv, '_get_db',
        lambda: sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    )

    result = srv.view_thread_timeline(url="https://nowhere.example.com")

    assert "No thread data found" in result
    assert "Alice" not in result


def test_search_vault_returns_results(monkeypatch):
    """search_vault should return formatted results when embeddings work."""
    mock_embedder = MagicMock()
    mock_embedder.encode.return_value.tolist.return_value = [0.1] * 384
    monkeypatch.setattr(srv, '_embedder', mock_embedder)
    # Force _get_embedder to return our mock
    monkeypatch.setattr(srv, '_get_embedder', lambda: mock_embedder)

    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        'documents': [["Ancient pyramid text"]],
        'metadatas': [[{'author': 'Bob', 'source': 'wayback_oldest'}]],
    }
    monkeypatch.setattr(srv, '_collection', mock_collection)
    monkeypatch.setattr(srv, '_get_collection', lambda: mock_collection)

    result = srv.search_vault(query="pyramids")

    assert "VAULT SEARCH" in result
    assert "Ancient pyramid text" in result
    assert "Bob" in result


def test_search_vault_no_embeddings(monkeypatch):
    """search_vault should return warning when embeddings unavailable."""
    monkeypatch.setattr(srv, '_get_embedder', lambda: None)
    monkeypatch.setattr(srv, '_get_collection', lambda: None)

    result = srv.search_vault(query="anything")

    assert "unavailable" in result.lower()


def test_vault_stats_no_db(monkeypatch):
    """vault_stats should handle missing database gracefully."""
    monkeypatch.setattr(srv, '_get_db', lambda: None)
    monkeypatch.setattr(srv, '_get_collection', lambda: None)

    result = srv.vault_stats()

    assert "VAULT STATISTICS" in result
    assert "not found" in result


# ─── Web Tool Tests ─────────────────────────────────────

def test_extract_page_returns_content(monkeypatch):
    """extract_page should strip boilerplate and return clean text."""
    import httpx

    mock_response = MagicMock()
    mock_response.text = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <nav>Navigation</nav>
        <main><p>Important content here.</p></main>
        <footer>Footer stuff</footer>
    </body>
    </html>
    """
    mock_response.raise_for_status = MagicMock()

    monkeypatch.setattr(srv._http_client, 'get', lambda *args, **kwargs: mock_response)

    result = srv.extract_page(url="https://example.com")

    assert "Important content here" in result
    assert "Test Page" in result
    # Nav/footer should be stripped
    assert "Navigation" not in result
    assert "Footer stuff" not in result


def test_summarize_text_reduces():
    """summarize_text should reduce long text to fewer sentences."""
    text = (
        "The first sentence is important. "
        "The second provides context. "
        "The third adds detail. "
        "The fourth is supplementary. "
        "The fifth concludes the topic. "
        "The sixth is extra padding. "
        "The seventh repeats concepts."
    )
    result = srv.summarize_text(text=text, max_sentences=3)

    assert "SUMMARY" in result
    assert "3 of 7" in result


def test_summarize_text_short_passthrough():
    """Short text should pass through unchanged."""
    text = "Only one sentence."
    result = srv.summarize_text(text=text, max_sentences=5)

    assert text == result  # No summarization needed


# ─── Lifecycle Tool Tests ─────────────────────────────────

def test_request_planning_creates_task():
    """request_planning should create a new active task."""
    # Reset state
    srv.task_state["current_task"] = None
    srv.task_state["history"] = []

    result = srv.request_planning()

    assert "Planning initiated" in result
    assert srv.task_state["current_task"] is not None
    assert srv.task_state["current_task"]["status"] == "active"


def test_approve_task_completion():
    """approve_task_completion should mark active task as completed."""
    srv.task_state["current_task"] = None
    srv.task_state["history"] = []
    srv.request_planning()

    result = srv.approve_task_completion()

    assert "completed" in result.lower()
    assert srv.task_state["current_task"] is None


def test_approve_no_active_task():
    """approve_task_completion with no active task should warn."""
    srv.task_state["current_task"] = None
    srv.task_state["history"] = []

    result = srv.approve_task_completion()

    assert "No active task" in result


def test_get_next_task_none_pending():
    """get_next_task should report no pending tasks."""
    srv.task_state["current_task"] = None
    srv.task_state["history"] = []

    result = srv.get_next_task()

    assert "No pending tasks" in result


# ─── Run Agent Tool Dispatch Tests ─────────────────────────

def test_run_mcp_tool_unknown():
    """run_mcp_tool should return error for unknown tools."""
    from run_agent import run_mcp_tool

    result = run_mcp_tool("nonexistent_tool", {})
    assert "Unknown tool" in result


def test_run_mcp_tool_dispatches_vault_stats():
    """run_mcp_tool should dispatch vault_stats correctly."""
    from run_agent import run_mcp_tool

    # vault_stats doesn't need embeddings to return output
    result = run_mcp_tool("vault_stats", {})
    assert "VAULT STATISTICS" in result
