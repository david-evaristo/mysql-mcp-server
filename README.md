# MySQL MCP Server

Read-only MCP server for querying MySQL databases via **Direct Connection** or **Teleport Database Access**.
Exposes databases and schema metadata to MCP clients (such as Claude Code, Claude Desktop, and Cursor) via the Model Context Protocol.

## Features & Connection Modes

The server supports two connection modes controlled by the `MYSQL_CONNECTION_MODE` environment variable:

1. **`teleport` (default)**: Connects via a local Teleport Database Access tunnel (`127.0.0.1:<port>`). Authentication and TLS encryption are delegated to Teleport mTLS (no password required).
2. **`direct`**: Connects directly to any MySQL host with username and password, with optional SSL/TLS CA verification.

---

## Prerequisites

- Python 3.10+
- [`uv`/`uvx`](https://docs.astral.sh/uv/) installed on the host that will run the server
- If using **Teleport mode**: `tsh` CLI authenticated with an active tunnel (`tsh db login` + `tsh proxy db --tunnel`)
- If using **Direct mode**: Host, port, user, and password for a MySQL account with `SELECT`-only privileges

## Installation

### Recommended — `uvx` (no clone, no `.venv`)

Runs the server directly from a release tag:

```bash
uvx --from git+https://github.com/david-evaristo/mysql-mcp-server.git@v1.1.0 mysql-mcp-server
```

### Local development — `.venv`

```bash
# 1. Clone the repository
git clone https://github.com/david-evaristo/mysql-mcp-server.git
cd mysql-mcp-server

# 2. Create and activate the virtualenv
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# 3. Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
# or: pip install -e ".[dev]"

# 4. Set up environment variables
cp .env.example .env
# edit .env with your local settings
```

## Configure in Claude Code

### Option 1 — Direct Connection (stdio via CLI)

```bash
claude mcp add mysql -s user \
  --env MYSQL_CONNECTION_MODE=direct \
  --env MYSQL_HOST=mysql.example.com \
  --env MYSQL_PORT=3306 \
  --env MYSQL_USER=mcp_readonly \
  --env MYSQL_PASSWORD=secure_password \
  -- uvx --from git+https://github.com/david-evaristo/mysql-mcp-server.git@v1.1.0 mysql-mcp-server
```

### Option 2 — Teleport Mode (stdio via CLI)

```bash
claude mcp add mysql -s user \
  --env MYSQL_CONNECTION_MODE=teleport \
  --env MYSQL_HOST=127.0.0.1 \
  --env MYSQL_PORT=54855 \
  --env MYSQL_USER=db-readonly \
  -- uvx --from git+https://github.com/david-evaristo/mysql-mcp-server.git@v1.1.0 mysql-mcp-server
```

### Option 3 — Configuration file (`~/.claude.json`)

Add to `~/.claude.json` under `mcpServers`:

```json
{
  "mcpServers": {
    "mysql": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/david-evaristo/mysql-mcp-server.git@v1.1.0",
        "mysql-mcp-server"
      ],
      "env": {
        "MYSQL_CONNECTION_MODE": "direct",
        "MYSQL_HOST": "mysql.example.com",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "mcp_readonly",
        "MYSQL_PASSWORD": "secure_password"
      }
    }
  }
}
```

### Option 4 — HTTP Mode (server running independently)

Start the server:
```bash
MCP_TRANSPORT=http python -m src.server
```

Then add to Claude Code:
```bash
claude mcp add mysql --transport http http://127.0.0.1:8000
```

## Configure in Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "mysql": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/david-evaristo/mysql-mcp-server.git@v1.1.0",
        "mysql-mcp-server"
      ],
      "env": {
        "MYSQL_CONNECTION_MODE": "direct",
        "MYSQL_HOST": "mysql.example.com",
        "MYSQL_PORT": "3306",
        "MYSQL_USER": "mcp_readonly",
        "MYSQL_PASSWORD": "secure_password"
      }
    }
  }
}
```

## Running via HTTP

```bash
MCP_TRANSPORT=http python -m src.server
```

Server starts on `http://127.0.0.1:8000`. To change the port:

```bash
MCP_TRANSPORT=http PORT=9000 python -m src.server
```

## Test locally (without Claude Desktop)

```bash
# Inspect available tools interactively
fastmcp dev src/server.py

# Or run directly (stdio)
python main.py
```

## Available Tools

| Tool | Description |
|---|---|
| `list_databases` | Lists all databases in the cluster (excluding system DBs) |
| `list_tables` | Lists tables in a database with size and row count |
| `describe_table` | Returns columns, types, indexes, and constraints |
| `execute_query` | Executes a SELECT — read-only, with automatic row limit |
| `search_tables` | Searches tables by LIKE pattern across the entire cluster |
| `get_table_sample` | Returns a sample of rows to understand data shape |

## Security

- Only `SELECT` queries are accepted — write keywords are blocked (27 blocked keywords including `outfile`, `execute`, `prepare`, `set`, `flush`, `shutdown` and more)
- MySQL session enforces `READ ONLY` at the protocol level via `init_command` (`SET SESSION TRANSACTION READ ONLY`)
- 500-row limit per query (configurable via `MCP_MAX_ROWS`)
- `LIMIT` is automatically injected if absent
- Rate limiting protects against abuse by restricting total tool calls per minute (`MCP_RATE_LIMIT`)
- Credentials are loaded exclusively from environment variables, never hardcoded or logged

## Environment Variables

| Variable | Default | Mode | Description |
|---|---|---|---|
| `MYSQL_CONNECTION_MODE` | `teleport` | Both | `teleport` (tunnel loopback) or `direct` (MySQL host) |
| `MYSQL_HOST` | — | Both | Required. Host of MySQL or Teleport proxy (`127.0.0.1`) |
| `MYSQL_PORT` | `54855` (teleport) / `3306` (direct) | Both | MySQL port |
| `MYSQL_USER` | — | Both | Required. Database user |
| `MYSQL_PASSWORD` | — | `direct` | Required in direct mode. Never exposed in logs or `repr` |
| `MYSQL_DATABASE` | — | Both | Optional default database |
| `MYSQL_SSL_CA` | — | `direct` | Optional path to CA bundle file for TLS validation |
| `MCP_MAX_ROWS` | `500` | Both | Cap on rows returned per query |
| `MCP_TRANSPORT` | `http` | Both | `stdio` or `http` |
| `MCP_HOST` | `127.0.0.1` | Both | Host for HTTP transport |
| `PORT` | `8000` | Both | HTTP port |
| `MCP_QUERY_TIMEOUT` | `30` | Both | Seconds before query is cancelled |
| `MCP_CONNECT_TIMEOUT` | `10` | Both | Seconds before connection attempt times out |
| `MCP_RATE_LIMIT` | `60` | Both | Max tool calls per minute; `0` to disable |
| `MCP_POOL_MIN` / `MCP_POOL_MAX` | `2` / `10` | Both | aiomysql connection pool size |

## MySQL User Setup (run by DBA)

The MySQL user needs `SELECT`-only privileges on the target databases:

```sql
-- Create read-only user
CREATE USER 'mcp_readonly'@'%' IDENTIFIED BY 'secure_password';

-- Grant SELECT on target databases
GRANT SELECT ON `my_database`.* TO 'mcp_readonly'@'%';

-- Allow reading information_schema (required for list_tables / describe_table)
GRANT SELECT ON information_schema.* TO 'mcp_readonly'@'%';

FLUSH PRIVILEGES;
```

## Tags and releases

Releases are cut as semantic Git tags (`v1.0.0`, `v1.1.0`, ...) on this repository:

```bash
git tag v1.1.0
git push origin v1.1.0
```

