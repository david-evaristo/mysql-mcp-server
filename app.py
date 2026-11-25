"""Entry point ASGI — Hugging Face Space."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.initialization import mcp

mcp_path = os.getenv("MCP_HTTP_PATH", "/mcp")
app = mcp.http_app(path=mcp_path, transport="streamable-http")
