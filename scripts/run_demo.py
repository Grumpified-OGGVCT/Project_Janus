"""scripts/run_demo.py

Run a single canned query against the Mistral Large 3 cloud model via the
Ollama REST API and write the result to docs/latest_run.json for the GitHub
Pages demo page.

Required environment variable:
  OLLAMA_HOST    — URL of the remote Ollama server (e.g. https://ollama.example.com)
                   The script exits with an error if this is not set or is empty.

Optional environment variable:
  OLLAMA_API_KEY — Bearer token for authenticated Ollama endpoints.
                   Sent as "Authorization: Bearer <key>" when present.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

MODEL = "mistral-large-3:675b-cloud"
DEMO_QUERY = (
    "Describe Project Janus: what it archives, how the Harvester collects data, "
    "how the MCP Server exposes it as tools, and how Mistral Large 3 reasons "
    "over the results to produce neutral, unfiltered answers."
)
SYSTEM_PROMPT = (
    "You are a neutral technical assistant for Project Janus, a sovereign archival "
    "system. Describe the architecture clearly and concisely."
)


def _build_headers() -> dict:
    """Return request headers, including Authorization if OLLAMA_API_KEY is set."""
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("OLLAMA_API_KEY", "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _normalize_host(host: str) -> str:
    """Ensure the host has an http(s):// scheme prefix."""
    host = host.strip().rstrip("/")
    if host and not host.startswith(("http://", "https://")):
        host = f"http://{host}"
    return host


def run_query(host: str) -> str:
    """Call the Ollama /api/chat endpoint and return the assistant message text."""
    url = f"{_normalize_host(host)}/api/chat"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": DEMO_QUERY},
        ],
        "stream": False,
    }
    resp = requests.post(url, json=payload, headers=_build_headers(), timeout=300)
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"]


def main():
    raw_host = os.getenv("OLLAMA_HOST", "").strip()
    if not raw_host:
        print("[demo] Error: OLLAMA_HOST environment variable is not set or is empty.")
        print("[demo] Set OLLAMA_HOST to the URL of your remote Ollama server.")
        sys.exit(1)

    host = _normalize_host(raw_host)

    print(f"[demo] Connecting to Ollama at : {host}")
    print(f"[demo] Model                   : {MODEL}")
    print(f"[demo] Query                   : {DEMO_QUERY}\n")

    output = {
        "model": MODEL,
        "ollama_host": raw_host,
        "query": DEMO_QUERY,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "response": "",
        "error": None,
    }

    try:
        output["response"] = run_query(host)
        print(f"[demo] Response received ({len(output['response'])} chars)")
    except Exception as exc:
        output["error"] = str(exc)
        print(f"[demo] Error: {exc}")

    os.makedirs("docs", exist_ok=True)
    out_path = os.path.join("docs", "latest_run.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    print(f"[demo] Written to {out_path}")


if __name__ == "__main__":
    main()
