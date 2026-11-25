"""Entry point for python -m src.server — selects transport via env."""
import logging
import os

from src.config import get_transport
from src.initialization import mcp
from src.logging_config import configure_logging

if __name__ == "__main__":
    configure_logging()
    transport = get_transport()
    logging.info("MCP transport: %s", transport)
    if transport == "http":
        host = os.getenv("MCP_HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "8000"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run(transport="stdio")
