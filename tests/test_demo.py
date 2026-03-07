"""tests/test_demo.py

Integration tests for scripts/run_demo.py.

These tests call the real Ollama API — no mocking.

Required environment variable (same as the demo script):
  OLLAMA_HOST    — URL of the remote Ollama server.

Optional:
  OLLAMA_API_KEY — Bearer token for authenticated endpoints.

All tests are skipped automatically when OLLAMA_HOST is not set, so the
suite still passes in environments without credentials (local dev).
"""

import json
import os
import sys

import pytest
import requests

# Make `scripts/` importable from the project root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import scripts.run_demo as demo

# ---------------------------------------------------------------------------
# Skip marker — applied to every live test
# ---------------------------------------------------------------------------
_raw_host = os.getenv("OLLAMA_HOST", "").strip()
OLLAMA_HOST = demo._normalize_host(_raw_host) if _raw_host else ""


@pytest.fixture(scope="module")
def require_ollama():
    """Fixture to dynamically check if the Ollama server is reachable."""
    if not OLLAMA_HOST:
        pytest.skip("OLLAMA_HOST not set — skipping live API tests")
    try:
        resp = requests.get(
            f"{OLLAMA_HOST}/api/tags",
            timeout=1,
            headers=demo._build_headers()
        )
        if resp.status_code != 200:
            pytest.skip(f"Ollama server returned status {resp.status_code} — skipping live API tests")
    except requests.exceptions.RequestException as e:
        pytest.skip(f"Ollama server not reachable ({e}) — skipping live API tests")


# ---------------------------------------------------------------------------
# Structural / static tests (no API call needed)
# ---------------------------------------------------------------------------

def test_normalize_host():
    """Unit tests for host scheme normalization."""
    assert demo._normalize_host("0.0.0.0:11434") == "http://0.0.0.0:11434"
    assert demo._normalize_host("http://localhost:11434") == "http://localhost:11434"
    assert demo._normalize_host("https://example.com") == "https://example.com"
    assert demo._normalize_host("127.0.0.1/") == "http://127.0.0.1"
    assert demo._normalize_host("") == ""

def test_demo_does_not_use_ollama_library():
    """Verify the demo no longer imports or uses the ollama Python library."""
    with open(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "run_demo.py"),
        encoding="utf-8",
    ) as fh:
        source = fh.read()
    assert "import ollama" not in source, "run_demo.py must not import the ollama library"
    assert "ollama.Client" not in source, "run_demo.py must not use ollama.Client"


def test_main_exits_when_ollama_host_missing(tmp_path, monkeypatch):
    """main() must sys.exit(1) when OLLAMA_HOST is not set."""
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        demo.main()
    assert exc_info.value.code == 1


def test_main_exits_when_ollama_host_empty(tmp_path, monkeypatch):
    """main() must sys.exit(1) when OLLAMA_HOST is an empty string."""
    monkeypatch.setenv("OLLAMA_HOST", "")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        demo.main()
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Live API tests — real calls to the Ollama endpoint
# ---------------------------------------------------------------------------

@pytest.mark.usefixtures("require_ollama")
def test_run_query_returns_nonempty_string():
    """run_query() must return a non-empty string from the live Ollama API."""
    result = demo.run_query(OLLAMA_HOST)
    assert isinstance(result, str)
    assert len(result) > 0, "Expected a non-empty response from the model"


@pytest.mark.usefixtures("require_ollama")
def test_run_query_response_is_text_not_error():
    """The live response must not contain a top-level error field."""
    url = f"{OLLAMA_HOST.rstrip('/')}/api/chat"
    payload = {
        "model": demo.MODEL,
        "messages": [
            {"role": "user", "content": "Reply with one word: ready"},
        ],
        "stream": False,
    }
    resp = requests.post(url, json=payload, headers=demo._build_headers(), timeout=60)
    resp.raise_for_status()
    data = resp.json()
    assert "message" in data, f"Expected 'message' key in response: {data}"
    assert "content" in data["message"], f"Expected 'content' in message: {data['message']}"
    assert len(data["message"]["content"]) > 0


@pytest.mark.usefixtures("require_ollama")
def test_main_writes_valid_json_with_response(tmp_path, monkeypatch):
    """main() must write docs/latest_run.json with a real response and no error."""
    monkeypatch.setenv("OLLAMA_HOST", _raw_host)
    monkeypatch.chdir(tmp_path)

    demo.main()

    out_path = tmp_path / "docs" / "latest_run.json"
    assert out_path.exists(), "docs/latest_run.json was not created"

    out = json.loads(out_path.read_text(encoding="utf-8"))
    assert out["model"] == demo.MODEL
    assert out["ollama_host"] == OLLAMA_HOST
    assert out["error"] is None, f"Expected no error but got: {out['error']}"
    assert len(out["response"]) > 0, "Expected a non-empty response in the JSON output"
    assert out["query"] == demo.DEMO_QUERY
    # Validate the timestamp is a parseable ISO 8601 string
    from datetime import datetime
    datetime.fromisoformat(out["timestamp"])  # raises ValueError if malformed
