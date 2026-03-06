"""
OpenAI-Compatible API Wrapper for Janus MCP Server
====================================================

Exposes Janus tools through an OpenAI-compatible /v1/ API interface,
allowing any tool that speaks the OpenAI API (LangChain, LlamaIndex,
AutoGen, CrewAI, etc.) to use Janus as a backend.

Endpoints:
    GET  /v1/models              — List available "models" (Janus tools)
    POST /v1/chat/completions    — Chat with tool execution
    POST /v1/completions         — Simple text completions (tool dispatch)
    GET  /v1/health              — Health check

Usage:
    python -m src.mcp_server.openai_compat               # port 8109
    python -m src.mcp_server.openai_compat --port 9000   # custom port

Connect from any OpenAI-compatible client:
    import openai
    client = openai.OpenAI(base_url="http://localhost:8109/v1", api_key="janus")
    response = client.chat.completions.create(
        model="janus",
        messages=[{"role": "user", "content": "search the vault for tartaria"}],
    )
"""

import json
import sys
import time
import uuid
from typing import Optional

try:
    from starlette.applications import Starlette
    from starlette.responses import JSONResponse
    from starlette.requests import Request
    from starlette.routing import Route
    import uvicorn
    ASGI_AVAILABLE = True
except ImportError:
    ASGI_AVAILABLE = False

# Import the Janus MCP tool functions directly
from src.mcp_server import server as mcp


# ---------------------------------------------------------------------------
# Tool registry — maps Janus tools for OpenAI function-calling format
# ---------------------------------------------------------------------------
TOOL_REGISTRY = {
    "search_vault": {
        "func": mcp.search_vault,
        "description": "Semantic search across the local Janus vault",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "n_results": {"type": "integer", "description": "Number of results (default 5)"},
            },
            "required": ["query"],
        },
    },
    "view_thread_timeline": {
        "func": mcp.view_thread_timeline,
        "description": "Reconstruct a forum thread across all snapshots",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Thread URL"},
            },
            "required": ["url"],
        },
    },
    "deep_recall": {
        "func": mcp.deep_recall,
        "description": "Deep semantic retrieval with Infinite RAG pattern",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Research query"},
                "n_results": {"type": "integer", "description": "Number of results"},
                "scope": {"type": "string", "description": "Domain filter"},
            },
            "required": ["query"],
        },
    },
    "vault_similar": {
        "func": mcp.vault_similar,
        "description": "Find vault content similar to text or URL",
        "parameters": {
            "type": "object",
            "properties": {
                "text_or_url": {"type": "string", "description": "Text or URL to match"},
                "n_results": {"type": "integer", "description": "Number of results"},
            },
            "required": ["text_or_url"],
        },
    },
    "vault_stats": {
        "func": mcp.vault_stats,
        "description": "Vault statistics: threads, posts, embeddings",
        "parameters": {"type": "object", "properties": {}},
    },
    "web_search": {
        "func": mcp.web_search,
        "description": "DuckDuckGo web search (no API key needed)",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Max results"},
            },
            "required": ["query"],
        },
    },
    "advanced_search": {
        "func": mcp.advanced_search,
        "description": "Advanced web search with region, time, site filters",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "region": {"type": "string", "description": "Region code"},
                "time_range": {"type": "string", "description": "d/w/m/y"},
                "site": {"type": "string", "description": "Restrict to domain"},
            },
            "required": ["query"],
        },
    },
    "extract_page": {
        "func": mcp.extract_page,
        "description": "Extract clean text from any URL",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to extract"},
                "max_chars": {"type": "integer", "description": "Max characters"},
            },
            "required": ["url"],
        },
    },
    "ingest_url": {
        "func": mcp.ingest_url,
        "description": "Crawl, ingest into vault, optionally search",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to ingest"},
                "depth": {"type": "integer", "description": "Crawl depth"},
                "search_after": {"type": "string", "description": "Search query after ingest"},
            },
            "required": ["url"],
        },
    },
    "summarize_text": {
        "func": mcp.summarize_text,
        "description": "Extractive summarization of text",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to summarize"},
                "max_sentences": {"type": "integer", "description": "Sentences to extract"},
            },
            "required": ["text"],
        },
    },
    "request_planning": {
        "func": mcp.request_planning,
        "description": "Start planning phase for a new task",
        "parameters": {"type": "object", "properties": {}},
    },
    "approve_task_completion": {
        "func": mcp.approve_task_completion,
        "description": "Mark current task as completed",
        "parameters": {"type": "object", "properties": {}},
    },
    "get_next_task": {
        "func": mcp.get_next_task,
        "description": "Get next pending task",
        "parameters": {"type": "object", "properties": {}},
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:12]}"


def _timestamp() -> int:
    return int(time.time())


def _tools_as_openai_functions() -> list:
    """Convert tool registry to OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": info["description"],
                "parameters": info["parameters"],
            },
        }
        for name, info in TOOL_REGISTRY.items()
    ]


def _execute_tool(name: str, arguments: dict) -> str:
    """Execute a registered Janus tool and return the result."""
    entry = TOOL_REGISTRY.get(name)
    if not entry:
        return f"Unknown tool: {name}"
    try:
        result = entry["func"](**arguments)
        return result if isinstance(result, str) else str(result)
    except Exception as exc:
        return f"Tool '{name}' error: {exc}"


def _detect_tool_intent(message: str) -> Optional[tuple]:
    """Simple heuristic to detect if a user message implies a tool call.
    Returns (tool_name, args) or None.
    """
    msg = message.lower().strip()

    # Direct tool invocation: "tool:search_vault query=tartaria"
    if msg.startswith("tool:"):
        parts = msg[5:].strip().split(maxsplit=1)
        tool_name = parts[0]
        if tool_name in TOOL_REGISTRY:
            # Try to parse key=value pairs
            args = {}
            if len(parts) > 1:
                for pair in parts[1].split():
                    if "=" in pair:
                        k, v = pair.split("=", 1)
                        args[k] = v
                if not args:
                    # If no key=value, assume first required param
                    req = TOOL_REGISTRY[tool_name]["parameters"].get("required", [])
                    if req:
                        args[req[0]] = parts[1]
            return (tool_name, args)

    # Natural language heuristics
    search_terms = ["search", "find", "look up", "query"]
    web_terms = ["web search", "google", "internet", "online"]
    extract_terms = ["extract", "get page", "read url", "fetch"]
    stats_terms = ["stats", "statistics", "how many", "count"]

    if any(t in msg for t in stats_terms) and ("vault" in msg or "archive" in msg):
        return ("vault_stats", {})

    if any(t in msg for t in web_terms):
        # Extract the query after the keyword
        for term in web_terms:
            if term in msg:
                query = msg.split(term, 1)[1].strip().strip('"\'')
                if query:
                    return ("web_search", {"query": query})

    if any(t in msg for t in extract_terms) and ("http" in msg):
        import re
        urls = re.findall(r'https?://\S+', message)
        if urls:
            return ("extract_page", {"url": urls[0]})

    if any(t in msg for t in search_terms) and not any(t in msg for t in web_terms):
        for term in search_terms:
            if term in msg:
                query = msg.split(term, 1)[1].strip().strip('"\'')
                if query:
                    return ("search_vault", {"query": query})

    return None


# ---------------------------------------------------------------------------
# ASGI Application (Starlette + Uvicorn)
# ---------------------------------------------------------------------------

if ASGI_AVAILABLE:

    async def list_models(request: Request) -> JSONResponse:
        """GET /v1/models — List Janus as an available model."""
        return JSONResponse({
            "object": "list",
            "data": [
                {
                    "id": "janus",
                    "object": "model",
                    "created": _timestamp(),
                    "owned_by": "project-janus",
                    "permission": [],
                    "root": "janus",
                    "parent": None,
                },
                # Also expose individual tools as "models"
                *[
                    {
                        "id": f"janus-{name}",
                        "object": "model",
                        "created": _timestamp(),
                        "owned_by": "project-janus",
                        "root": "janus",
                        "parent": "janus",
                    }
                    for name in TOOL_REGISTRY
                ],
            ],
        })

    async def chat_completions(request: Request) -> JSONResponse:
        """POST /v1/chat/completions — Chat with tool execution."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        messages = body.get("messages", [])
        model = body.get("model", "janus")
        stream = body.get("stream", False)

        if stream:
            return JSONResponse(
                {"error": "Streaming not yet supported. Set stream=false."},
                status_code=501,
            )

        if not messages:
            return JSONResponse({"error": "No messages provided"}, status_code=400)

        # Get the last user message
        user_msg = None
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break

        if not user_msg:
            return JSONResponse({"error": "No user message found"}, status_code=400)

        # Check if model targets a specific tool (e.g., model="janus-web_search")
        specific_tool = None
        if model.startswith("janus-"):
            tool_name = model[6:]  # strip "janus-"
            if tool_name in TOOL_REGISTRY:
                specific_tool = tool_name

        # Execute tool
        if specific_tool:
            # Direct tool call via model name
            req_params = TOOL_REGISTRY[specific_tool]["parameters"].get("required", [])
            args = {}
            if req_params:
                args[req_params[0]] = user_msg
            result = _execute_tool(specific_tool, args)
        else:
            # Try heuristic detection
            intent = _detect_tool_intent(user_msg)
            if intent:
                tool_name, args = intent
                result = _execute_tool(tool_name, args)
            else:
                # No tool detected — return guidance
                tools_list = ", ".join(TOOL_REGISTRY.keys())
                result = (
                    f"Janus Knowledge Server — available tools: {tools_list}\n\n"
                    f"Use 'tool:<name> <query>' for direct tool calls, or phrase "
                    f"your request naturally (e.g., 'search the vault for tartaria').\n\n"
                    f"Available tool-specific models: "
                    + ", ".join(f"janus-{n}" for n in TOOL_REGISTRY)
                )

        return JSONResponse({
            "id": _make_id(),
            "object": "chat.completion",
            "created": _timestamp(),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result,
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(user_msg.split()),
                "completion_tokens": len(result.split()),
                "total_tokens": len(user_msg.split()) + len(result.split()),
            },
        })

    async def completions(request: Request) -> JSONResponse:
        """POST /v1/completions — Simple text completions via tool dispatch."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        prompt = body.get("prompt", "")
        model = body.get("model", "janus")

        if not prompt:
            return JSONResponse({"error": "No prompt provided"}, status_code=400)

        # Same logic as chat completions
        specific_tool = None
        if model.startswith("janus-"):
            tool_name = model[6:]
            if tool_name in TOOL_REGISTRY:
                specific_tool = tool_name

        if specific_tool:
            req_params = TOOL_REGISTRY[specific_tool]["parameters"].get("required", [])
            args = {}
            if req_params:
                args[req_params[0]] = prompt
            result = _execute_tool(specific_tool, args)
        else:
            intent = _detect_tool_intent(prompt)
            if intent:
                tool_name, args = intent
                result = _execute_tool(tool_name, args)
            else:
                result = f"Janus: No tool matched. Available: {', '.join(TOOL_REGISTRY.keys())}"

        return JSONResponse({
            "id": _make_id(),
            "object": "text_completion",
            "created": _timestamp(),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "text": result,
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(result.split()),
                "total_tokens": len(prompt.split()) + len(result.split()),
            },
        })

    async def health_check(request: Request) -> JSONResponse:
        """GET /v1/health — Server health check."""
        return JSONResponse({
            "status": "ok",
            "server": "janus-openai-compat",
            "tools_available": len(TOOL_REGISTRY),
            "tools": list(TOOL_REGISTRY.keys()),
            "endpoints": ["/v1/models", "/v1/chat/completions", "/v1/completions"],
        })

    async def openai_tools(request: Request) -> JSONResponse:
        """GET /v1/tools — List available tools in OpenAI function format."""
        return JSONResponse({
            "object": "list",
            "data": _tools_as_openai_functions(),
        })

    # Starlette app
    openai_app = Starlette(
        routes=[
            Route("/v1/models", list_models, methods=["GET"]),
            Route("/v1/chat/completions", chat_completions, methods=["POST"]),
            Route("/v1/completions", completions, methods=["POST"]),
            Route("/v1/health", health_check, methods=["GET"]),
            Route("/v1/tools", openai_tools, methods=["GET"]),
        ],
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

DEFAULT_PORT = 8109  # One above the MCP server port


def main():
    """Run the OpenAI-compatible API server."""
    if not ASGI_AVAILABLE:
        print("Error: starlette and uvicorn are required.")
        print("Install: pip install starlette uvicorn")
        sys.exit(1)

    port = DEFAULT_PORT
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])

    print(f"┌──────────────────────────────────────────────┐")
    print(f"│  Janus — OpenAI-Compatible API               │")
    print(f"│  http://127.0.0.1:{port}/v1{' ' * (19 - len(str(port)))}│")
    print(f"├──────────────────────────────────────────────┤")
    print(f"│  Tools:     {len(TOOL_REGISTRY):2d}                             │")
    print(f"│  Endpoints: models, chat, completions        │")
    print(f"│                                              │")
    print(f"│  Usage:                                      │")
    print(f"│    base_url = http://127.0.0.1:{port}/v1{' ' * (5 - len(str(port)))}   │")
    print(f"│    api_key  = 'janus' (any value works)      │")
    print(f"└──────────────────────────────────────────────┘")

    uvicorn.run(openai_app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
