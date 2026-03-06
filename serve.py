"""
serve.py — Janus MCP HTTP Server Launcher
==========================================

Starts the Janus MCP server in Streamable HTTP mode.

Usage:
    python serve.py                  # Default port 8108
    python serve.py --port 9000     # Custom port

External tools connect to:
    http://127.0.0.1:8108/mcp

Examples:
    OpenClaw:  MCP_BASE_URL=http://127.0.0.1:8108/mcp
    Cursor:    Add http://127.0.0.1:8108/mcp in MCP settings
    LangChain: base_url="http://127.0.0.1:8108/v1/"
"""

import sys


def main():
    # Inject --http flag so server.py knows to use HTTP transport
    if "--http" not in sys.argv:
        sys.argv.append("--http")

    from src.mcp_server.server import main as server_main
    server_main()


if __name__ == "__main__":
    main()
