import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock heavy ML / MCP dependencies BEFORE any test file imports server.py.
# This prevents model downloads (~100 MB) during unit tests.
# ---------------------------------------------------------------------------

# 1. sentence_transformers — encode() returns a fixed-length float list
_st = MagicMock()
_mock_encoder = MagicMock()
_mock_encoder.encode.return_value.tolist.return_value = [0.1] * 384
_st.SentenceTransformer.return_value = _mock_encoder
sys.modules['sentence_transformers'] = _st

# 2. chromadb — query() returns empty result sets by default
_collection = MagicMock()
_collection.query.return_value = {'documents': [[]], 'metadatas': [[]]}
_collection.count.return_value = 0
_chroma = MagicMock()
_chroma.PersistentClient.return_value.get_or_create_collection.return_value = _collection
sys.modules['chromadb'] = _chroma

# 3. mcp — FastMCP as a transparent decorator passthrough
#    The decorators @app.tool(), @app.resource(), @app.prompt() should
#    just return the wrapped function unchanged so tests can call them directly.

class _MockFastMCP:
    """Minimal mock that makes @app.tool() etc. into identity decorators."""
    def __init__(self, name="test", **kwargs):
        self.name = name
        self.settings = MagicMock()
        self._instructions = kwargs.get("instructions", "")

    def tool(self, *args, **kwargs):
        """@app.tool() — return the function unchanged."""
        def decorator(fn):
            return fn
        return decorator

    def resource(self, uri=None, *args, **kwargs):
        """@app.resource("janus://status") — return the function unchanged."""
        def decorator(fn):
            return fn
        return decorator

    def prompt(self, *args, **kwargs):
        """@app.prompt() — return the function unchanged."""
        def decorator(fn):
            return fn
        return decorator

    def run(self, **kwargs):
        pass

_mcp_mod = MagicMock()
_mcp_fastmcp_mod = MagicMock()
_mcp_fastmcp_mod.FastMCP = _MockFastMCP
sys.modules['mcp'] = _mcp_mod
sys.modules['mcp.server'] = MagicMock()
sys.modules['mcp.server.fastmcp'] = _mcp_fastmcp_mod
sys.modules['mcp.server.stdio'] = MagicMock()
sys.modules['mcp.types'] = MagicMock()

# 4. duckduckgo_search — mock to avoid network calls in tests
_ddgs_mock = MagicMock()
sys.modules['duckduckgo_search'] = _ddgs_mock
