import os
import sys
import json
import hashlib
import asyncio
import ollama

# ---------------------------------------------------------------------------
# Configuration — reads .janus_config.json, falls back to hardcoded defaults
# ---------------------------------------------------------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), ".janus_config.json")

# Hardcoded defaults (used when no config file exists)
DEFAULT_MODEL = "mistral-large-3:675b-cloud"
DEFAULT_HOST = "http://localhost:11434"

# Model options — maximised for the 256 K-context cloud model.
# num_ctx       : full 256 K context window (262 144 tokens)
# num_predict   : -1 = no output-token cap; model decides when to stop
# temperature   : 0.7  — creative enough for synthesis, precise for research
# top_p         : 0.95 — nucleus sampling; keeps high-probability tokens in play
# top_k         : 60   — wider candidate pool than the default of 40
# repeat_penalty: 1.05 — light penalty; avoids loops without hurting repetition
# mirostat      : 2    — adaptive sampler targeting a stable perplexity
# mirostat_tau  : 5.0  — target entropy; higher = more diverse output
# mirostat_eta  : 0.1  — learning rate for the mirostat algorithm
DEFAULT_MODEL_OPTIONS = {
    "num_ctx": 262144,
    "num_predict": -1,
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 60,
    "repeat_penalty": 1.05,
    "mirostat": 2,
    "mirostat_tau": 5.0,
    "mirostat_eta": 0.1,
}


def load_config() -> dict:
    """Load configuration from .janus_config.json, falling back to defaults."""
    config = {
        "model": DEFAULT_MODEL,
        "host": DEFAULT_HOST,
        "model_options": DEFAULT_MODEL_OPTIONS.copy(),
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                user_cfg = json.load(fh)
            config["model"] = user_cfg.get("model", config["model"])
            config["host"] = user_cfg.get("host", config["host"])
            if "model_options" in user_cfg and isinstance(user_cfg["model_options"], dict):
                config["model_options"].update(user_cfg["model_options"])
            print(f"[Config] Loaded from {CONFIG_PATH}")
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[Config] Warning: Could not parse {CONFIG_PATH}: {exc}")
            print("[Config] Using hardcoded defaults.")
    else:
        print(f"[Config] No config file at {CONFIG_PATH} — using defaults.")
    return config


def check_ollama_connection(host: str) -> bool:
    """Check if Ollama is reachable at the given host. Returns True if connected."""
    try:
        client = ollama.Client(host=host)
        client.list()
        return True
    except Exception:
        return False


def verify_model(host: str, model_name: str) -> bool:
    """Check if the configured model is available. Offer to pull if missing."""
    try:
        client = ollama.Client(host=host)
        models_resp = client.list()
        available = [m.get("name", m.get("model", "")) for m in models_resp.get("models", [])]
        if model_name in available:
            return True
        # Try partial match (e.g. "mistral:latest" matches "mistral:latest")
        base_name = model_name.split(":")[0]
        for m in available:
            if m.startswith(base_name):
                print(f"[Model] Exact match '{model_name}' not found, but '{m}' is available.")
                return True
        print(f"[Model] '{model_name}' not found. Available: {', '.join(available) or '(none)'}")
        return False
    except Exception as exc:
        print(f"[Model] Could not verify model: {exc}")
        return False


def startup_check(config: dict) -> dict:
    """Run connection and model checks. Returns updated config or exits."""
    host = config["host"]
    model = config["model"]

    print(f"[Startup] Checking Ollama at {host}...")

    while not check_ollama_connection(host):
        print(f"\n  ╔══════════════════════════════════════════════════╗")
        print(f"  ║  ⚠  Ollama not detected at {host:<20s} ║")
        print(f"  ╠══════════════════════════════════════════════════╣")
        print(f"  ║  [1] Retry connection                           ║")
        print(f"  ║  [2] Change host URL                            ║")
        print(f"  ║  [3] Run setup wizard                           ║")
        print(f"  ║  [4] Exit                                       ║")
        print(f"  ╚══════════════════════════════════════════════════╝")
        try:
            choice = input("  Choice [1-4]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[System] Exiting.")
            sys.exit(0)

        if choice == "1":
            continue
        elif choice == "2":
            new_host = input("  Enter Ollama URL: ").strip()
            if new_host:
                host = new_host
                config["host"] = host
        elif choice == "3":
            print("[System] Launching setup wizard...")
            os.system(f"{sys.executable} scripts/setup_wizard.py")
            # Re-load config after wizard
            config = load_config()
            host = config["host"]
        elif choice == "4":
            sys.exit(0)

    print(f"[Startup] ✓ Connected to Ollama at {host}")

    # Model verification
    if not verify_model(host, model):
        try:
            pull = input(f"  Pull '{model}' now? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            pull = "n"
        if pull == "y":
            print(f"[Model] Pulling {model}... (this may take a while)")
            try:
                client = ollama.Client(host=host)
                client.pull(model)
                print(f"[Model] ✓ {model} pulled successfully")
            except Exception as exc:
                print(f"[Model] Pull failed: {exc}")
                print("[Model] Continuing anyway — you may need to pull manually.")
        else:
            print("[Model] Skipping pull — will attempt to use as-is.")
    else:
        print(f"[Startup] ✓ Model '{model}' available")

    return config


# ---------------------------------------------------------------------------
# Workspace Snapshot (O(1) Context Bounding)
# ---------------------------------------------------------------------------
def get_workspace_snapshot() -> str:
    """Generate a bounded workspace snapshot representing the current state."""
    snapshot = "Workspace Snapshot:\n"
    data_dir = os.path.join(os.path.dirname(__file__), "data")
    if os.path.exists(data_dir):
        for root, _, files in os.walk(data_dir):
            for f in sorted(files):
                filepath = os.path.join(root, f)
                rel_path = os.path.relpath(filepath, data_dir)
                if f.endswith('.db') or f.endswith('.sqlite') or 'chroma_db' in root:
                    snapshot += f"- {rel_path} (Database file)\n"
                    continue
                try:
                    with open(filepath, 'rb') as file_obj:
                        file_hash = hashlib.sha256(file_obj.read()).hexdigest()[:8]
                    snapshot += f"- {rel_path} (SHA256: {file_hash})\n"
                except Exception:
                    snapshot += f"- {rel_path} (unreadable)\n"
    else:
        snapshot += "(Empty workspace)\n"
    return snapshot


def run_mcp_tool(tool_name: str, arguments: dict) -> str:
    """
    Execute an MCP tool by calling the server functions directly.
    In HTTP mode, these would be network calls; here we import
    the decorated functions for local reliability.
    """
    from src.mcp_server import server as mcp

    # Map tool names to their server functions
    tool_map = {
        "search_vault":             mcp.search_vault,
        "view_thread_timeline":     mcp.view_thread_timeline,
        "deep_recall":              mcp.deep_recall,
        "vault_similar":            mcp.vault_similar,
        "vault_stats":              mcp.vault_stats,
        "web_search":               mcp.web_search,
        "advanced_search":          mcp.advanced_search,
        "extract_page":             mcp.extract_page,
        "ingest_url":               mcp.ingest_url,
        "summarize_text":           mcp.summarize_text,
        "request_planning":         mcp.request_planning,
        "approve_task_completion":   mcp.approve_task_completion,
        "get_next_task":            mcp.get_next_task,
    }

    func = tool_map.get(tool_name)
    if func is None:
        return f"Unknown tool: {tool_name}"

    try:
        result = func(**arguments)
        return result if isinstance(result, str) else str(result)
    except Exception as exc:
        return f"Tool '{tool_name}' error: {exc}"


def main():
    # Load config and run startup checks
    config = load_config()
    config = startup_check(config)

    model = config["model"]
    host = config["host"]
    model_options = config["model_options"]
    client = ollama.Client(host=host)

    print(f"\n[System] Initializing Sovereign Historian")
    print(f"         Model : {model}")
    print(f"         Host  : {host}")
    print("Ready for input. Type 'exit' to quit.\n")

    tools_schema = [
        # ─── Vault Tools ─────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "search_vault",
                "description": "Semantic search across the local Janus vault for historical content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The concept, name, or topic to search for"},
                        "n_results": {"type": "integer", "description": "Number of results (default 5)"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "view_thread_timeline",
                "description": "Reconstruct a forum thread across all snapshots (live + Wayback).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL of the forum thread"}
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "deep_recall",
                "description": "Deep semantic retrieval with Infinite RAG pattern. Retrieves extensive historical context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The concept or question to deeply research"},
                        "n_results": {"type": "integer", "description": "Number of results (default 10, max 100)"},
                        "scope": {"type": "string", "description": "Optional source domain filter"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "vault_similar",
                "description": "Find vault content semantically similar to given text or a URL's content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text_or_url": {"type": "string", "description": "Text to match, or URL to fetch and match"},
                        "n_results": {"type": "integer", "description": "Number of similar results (default 5)"}
                    },
                    "required": ["text_or_url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "vault_stats",
                "description": "Get vault statistics: threads, posts, sources, embeddings count.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        # ─── Web Tools ───────────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web using DuckDuckGo (no API key needed).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query"},
                        "max_results": {"type": "integer", "description": "Maximum results (default 10)"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "advanced_search",
                "description": "Advanced web search with region, time, and site filters.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The search query"},
                        "max_results": {"type": "integer", "description": "Maximum results (default 10)"},
                        "region": {"type": "string", "description": "Region code (default wt-wt)"},
                        "time_range": {"type": "string", "description": "d=day, w=week, m=month, y=year"},
                        "site": {"type": "string", "description": "Restrict to domain"}
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "extract_page",
                "description": "Extract clean readable text from any URL, stripping navigation and boilerplate.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The URL to extract content from"},
                        "max_chars": {"type": "integer", "description": "Max characters (default 8000)"}
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "ingest_url",
                "description": "Crawl a URL, ingest into the vault, optionally search freshly ingested content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL to crawl and ingest"},
                        "depth": {"type": "integer", "description": "Crawl depth (1=page, 2=follow links)"},
                        "search_after": {"type": "string", "description": "Query to search after ingestion"}
                    },
                    "required": ["url"]
                }
            }
        },
        # ─── Utility Tools ───────────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "summarize_text",
                "description": "Extract key sentences from text using extractive summarization.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "The text to summarize"},
                        "max_sentences": {"type": "integer", "description": "Key sentences to extract (default 5)"}
                    },
                    "required": ["text"]
                }
            }
        },
        # ─── Task Lifecycle Tools ────────────────────────────
        {
            "type": "function",
            "function": {
                "name": "request_planning",
                "description": "Start the planning phase for a new task.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "approve_task_completion",
                "description": "Mark current task as completed.",
                "parameters": {"type": "object", "properties": {}}
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_next_task",
                "description": "Get next pending task or status.",
                "parameters": {"type": "object", "properties": {}}
            }
        }
    ]

    messages = [
        {
            "role": "system",
            "content": (
                "You are a neutral research assistant. You have access to a local "
                "database of historical records. You do not judge, correct, or filter "
                "the data. You present findings exactly as they are stored in the "
                "archive. When asked a question, use the tools to retrieve information "
                "and summarize the raw findings neutrally. "
                "You operate under the Infinite CTX protocol: maintain O(1) context by "
                "focusing on the latest findings and workspace snapshots. "
                "You MUST follow the MCP Task Lifecycle strictly: Use request_planning "
                "when starting a task, approve_task_completion when finished, and "
                "get_next_task to get more work."
            )
        }
    ]

    while True:
        try:
            user_input = input("User: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[System] Shutting down.")
            break

        if user_input.lower() in ('exit', 'quit', ''):
            break

        messages.append({"role": "user", "content": user_input})

        # O(1) Context Bounding (Silver Hat): Keep system prompt, fresh snapshot, and last <= 10 actions
        snapshot_content = get_workspace_snapshot()

        # If the second message isn't the snapshot, insert it
        if len(messages) > 1 and not messages[1].get("content", "").startswith("Workspace Snapshot:"):
            messages.insert(1, {"role": "system", "content": snapshot_content})
        elif len(messages) > 1:
            messages[1] = {"role": "system", "content": snapshot_content}

        # Bounding: system + snapshot + up to 10 latest messages
        if len(messages) > 12:
            print("[System] Bounding context (Infinite CTX O(1))...")
            messages = [messages[0], messages[1]] + messages[-10:]

        # Step 1: Ask the model what to do
        print(f"[{model.split(':')[0].title()}] Thinking...")
        try:
            response = client.chat(
                model=model,
                messages=messages,
                tools=tools_schema,
                options=model_options,
            )
        except Exception as exc:
            print(f"\n[Error] Ollama call failed: {exc}")
            print("[Error] Check if the server is still running and the model is available.")
            continue

        response_message = response.get('message', {})

        # Step 2: Check if the model wants to use a tool
        tool_calls = response_message.get('tool_calls')
        if tool_calls:
            messages.append(response_message)

            for tool_call in tool_calls:
                tool_name = tool_call['function']['name']
                tool_args = tool_call['function']['arguments']

                print(f"[Tool Call] Executing: {tool_name} with args {tool_args}")

                # Step 3: Execute the tool locally
                tool_result = run_mcp_tool(tool_name, tool_args)

                messages.append({
                    "role": "tool",
                    "content": tool_result,
                })

            # Step 4: Ask the model to synthesise the result
            try:
                final_response = client.chat(
                    model=model,
                    messages=messages,
                    options=model_options,
                )
                answer = final_response['message']['content']
                print(f"\nHistorian: {answer}\n")
                messages.append(final_response['message'])
            except Exception as exc:
                print(f"\n[Error] Synthesis call failed: {exc}")

        else:
            # No tool call needed — direct answer
            answer = response_message.get('content', '')
            print(f"\nHistorian: {answer}\n")
            messages.append(response_message)


if __name__ == "__main__":
    main()

