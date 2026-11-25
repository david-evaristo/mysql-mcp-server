"""Entry point stdio — Cursor, Claude Desktop.

Thin shim kept for local development (`python main.py`); the recommended way to run
this server is the `mysql-mcp-server` console script installed via pyproject.toml
(see src/cli.py), which is what `uvx --from git+<url>@<tag> mysql-mcp-server` invokes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli import main

if __name__ == "__main__":
    main()
