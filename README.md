# MySQL MCP Server

Read-only MCP server for querying a MySQL cluster via a Teleport Database Access tunnel.
Exposes cluster databases and schema metadata to MCP clients (such as Claude Code, Claude Desktop, and Cursor) via the Model Context Protocol.

## Prerequisites

- Python 3.10+
- [`uv`/`uvx`](https://docs.astral.sh/uv/) installed on the host that will run the server (recommended way to invoke it — see below)
- Teleport CLI (`tsh`) authenticated, with a Teleport Database Access tunnel open on `127.0.0.1` (`tsh db login` + `tsh proxy db --tunnel`)
- A Teleport role with `SELECT`-only permission on the target databases (e.g. `db-readonly`)

## Installation

### Recommended — `uvx` (no clone, no `.venv`)

Runs the server directly from a tagged release of the repository, on any host with `uv`/`uvx` installed:

```bash
uvx --from git+https://github.com/<owner>/<repo>.git@<tag> mysql-mcp-server
```

Replace `<tag>` with the latest released tag (e.g. `v1.0.0`, see [Tags and releases](#tags-and-releases)).

### Local development — `.venv`

Only needed if you are developing this repository itself (running tests, linting, etc.):

```bash
# 1. Clone the repository
git clone https://github.com/<owner>/<repo>.git
cd <repo>

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

Choose one of the options below:

### Option 1 — stdio via CLI (recommended)

```bash
claude mcp add mysql -s user \
  --env MYSQL_HOST=127.0.0.1 \
  --env MYSQL_PORT=54855 \
  --env MYSQL_USER=db-readonly \
  -- uvx --from git+https://github.com/<owner>/<repo>.git@<tag> mysql-mcp-server
```

### Option 2 — stdio via settings file

Add to `~/.claude.json` under the `mcpServers` key (user scope — available in all projects):

```json
{
  "mcpServers": {
    "mysql": {
      "command": "uvx",
      "args": [
        "--from", "git+https://github.com/<owner>/<repo>.git@<tag>",
        "mysql-mcp-server"
      ],
      "env": {
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "54855",
        "MYSQL_USER": "db-readonly"
      }
    }
  }
}
```

### Option 3 — HTTP (server already running)

First start the server:

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
        "--from", "git+https://github.com/<owner>/<repo>.git@<tag>",
        "mysql-mcp-server"
      ],
      "env": {
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "54855",
        "MYSQL_USER": "db-readonly"
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

- Only `SELECT` queries are accepted — any write keyword is blocked (27 blocked keywords including `outfile`, `execute`, `prepare`, `set`, `flush`, `shutdown` and more)
- MySQL session enforces `READ ONLY` at the protocol level via `init_command` — writes are rejected even if the application layer is bypassed
- 500-row limit per query (configurable via `MCP_MAX_ROWS`)
- `LIMIT` is automatically injected if absent
- Rate limiting protects against abuse by restricting the total tool calls per minute across all connections. Configurable via `MCP_RATE_LIMIT`. When exceeded, tools will return a rate-limit error.
- Credentials are loaded exclusively from environment variables, never hardcoded

### Encryption

Encryption and authentication are handled by the Teleport Database Access tunnel (mTLS certificate, short-lived, per individual identity) — no SSL configuration is required in this server. Do not set `MYSQL_HOST` to a direct remote endpoint; the server will warn at startup if it detects a non-loopback host.

## Environment Variables

| Variable | Default | Required |
|---|---|---|
| `MYSQL_HOST` | — | Yes (must be `127.0.0.1` — Teleport Database Access tunnel) |
| `MYSQL_USER` | — | Yes (the Teleport role's `--db-user`, e.g. `db-readonly`) |
| `MYSQL_PORT` | `54855` | No |
| `MCP_MAX_ROWS` | `500` | No |
| `MCP_TRANSPORT` | `http` | No |
| `MCP_HOST` | `127.0.0.1` | No |
| `MCP_QUERY_TIMEOUT` | `30` | No |
| `MCP_CONNECT_TIMEOUT` | `10` | No |
| `MCP_RATE_LIMIT` | `60` | No (tool calls per minute; `0` to disable) |
| `MCP_POOL_MIN` / `MCP_POOL_MAX` | `2` / `10` | No |
| `PORT` | `8000` | No |

## MySQL User Setup (run by DBA)

The underlying MySQL user mapped to the Teleport read-only role needs `SELECT`-only privileges on the target databases:

```sql
-- Create read-only user
CREATE USER 'mcp_readonly'@'%' IDENTIFIED BY 'secure_password';

-- Grant SELECT on target databases
GRANT SELECT ON `my_database`.* TO 'mcp_readonly'@'%';

-- Allow reading information_schema (required for list_tables / describe_table)
GRANT SELECT ON information_schema.* TO 'mcp_readonly'@'%';

FLUSH PRIVILEGES;
```

## Teleport Setup Requirements

Using this server with Teleport Database Access requires two things provisioned by a Teleport administrator:

1. The MySQL cluster registered as a `db` resource in Teleport.
2. A read-only role (e.g. `db-readonly`) mapped to the MySQL read-only user above, scoped to the target databases.

## Tags and releases

Releases are cut as semantic Git tags (`v1.0.0`, `v1.1.0`, ...) on this repository:

```bash
git tag v1.1.0
git push origin v1.1.0
```
