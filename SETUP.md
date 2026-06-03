# Vector Indexer MCP — Deployment Setup Guide

This document describes the **actual running deployment** — the `*_local.py` modules,
migrations, and systemd units that ship in this repo. The original `src/server.py` /
`daemon/*.py` modules (Supabase backend) remain in tree but are not used by the
production deployment.

---

## Prerequisites

- Python 3.10+
- PostgreSQL 14+ with **pgvector** extension
- systemd (user session) for service management

---

## 1. PostgreSQL / pgvector

### Install pgvector (if not already installed)

```bash
# Debian/Ubuntu
sudo apt install postgresql-14-pgvector   # or postgresql-15-pgvector

# Build from source (any distro)
git clone https://github.com/pgvector/pgvector.git
cd pgvector && make && sudo make install
```

### Create role and database

```sql
-- as postgres superuser
CREATE ROLE vectoruser WITH LOGIN PASSWORD 'your-strong-password';
CREATE DATABASE vectorindex OWNER vectoruser;

-- connect to vectorindex and enable the extension
\c vectorindex
CREATE EXTENSION IF NOT EXISTS vector;
GRANT ALL ON SCHEMA public TO vectoruser;
```

### Apply the migration

```bash
psql -U vectoruser -d vectorindex -f migrations/020_vector_search_indexer.sql
```

This creates:
- `file_metadata`, `file_chunks`, `file_embeddings`, `index_queue`, `index_stats` tables
- GIN index for full-text search
- HNSW index for vector cosine similarity
- `search_hybrid()` and `get_index_health()` stored functions

---

## 2. Python environment

```bash
cd /path/to/vector-indexer-mcp

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

Key runtime dependencies (all in `requirements.txt`):
- `asyncpg` — PostgreSQL driver used by all `*_local.py` modules
- `sentence-transformers` + `torch` — embedding generation
- `watchdog` — file system monitoring
- `mcp` — MCP server protocol
- `uvicorn`, `starlette`, `sse-starlette` — HTTP/SSE transport (`sse_server_local.py`)

> **Note on pyproject.toml**: The `[project.scripts]` entries (`vector-indexer-worker`,
> `vector-indexer-mcp`) point at the old Supabase modules (`daemon.worker:main`,
> `src.server:main`). Do **not** use them for the local deployment — use the systemd
> units or the module invocations below instead.

---

## 3. Configuration

```bash
cp config.yaml.example config.yaml
# Edit config.yaml and set:
#   database.password  → your PostgreSQL password (same as step 1)
#   watcher.paths      → list of absolute directory paths to monitor
```

**Important**: `config.yaml` is gitignored and must never be committed — it contains
your database password. The modules load it from a **hardcoded path**:

```
/home/david/vector-indexer-mcp/config.yaml   # in src/server_local.py
/home/david/vector-indexer-mcp/config.yaml   # in daemon/worker_local.py
/home/david/vector-indexer-mcp/config.yaml   # in daemon/watcher_local.py
```

This path is hardcoded in the source (known limitation — see Recommended Follow-ups).
For a different checkout location, update `CONFIG_PATH` in each `*_local.py` file or
create a symlink.

### watcher.paths gotcha

The `watcher.paths` list accepts **any** absolute path, including paths outside the
project root. The daemon watches each listed directory recursively. Paths that do not
exist at startup are skipped with a warning (they can be added later by restarting the
service).

---

## 4. Systemd user services

The `systemd/` directory contains the three unit files. Copy them to your user systemd
directory and adjust the `WorkingDirectory` and `ExecStart` paths to match your
checkout location before enabling.

```bash
# Adjust paths inside each .service file first, then:
cp systemd/vector-indexer-worker.service    ~/.config/systemd/user/
cp systemd/vector-indexer-watcher.service   ~/.config/systemd/user/
cp systemd/vector-indexer-mcp-http.service  ~/.config/systemd/user/

systemctl --user daemon-reload

# Start worker first (embedder / queue processor)
systemctl --user enable --now vector-indexer-worker

# Start file watcher (enqueues changed files)
systemctl --user enable --now vector-indexer-watcher

# Start HTTP/SSE server (optional — for non-stdio MCP clients)
systemctl --user enable --now vector-indexer-mcp-http
```

Check status / logs:

```bash
systemctl --user status vector-indexer-worker
journalctl --user -u vector-indexer-worker -f
```

### Service startup order

`vector-indexer-worker` → `vector-indexer-mcp-http` (declared in `After=`).
`vector-indexer-watcher` is independent of the other two.

---

## 5. Claude MCP stdio entry

For direct stdio usage (the typical Claude Code / claude-mpm setup), add this to your
`mcpServers` configuration:

```json
{
  "vector-indexer-mcp": {
    "command": "/path/to/vector-indexer-mcp/venv/bin/python",
    "args": ["-m", "src.server_local"],
    "cwd": "/path/to/vector-indexer-mcp"
  }
}
```

The server reads `config.yaml` at import time (hardcoded path — see note above), so
the `cwd` must match the checkout location, **or** the `CONFIG_PATH` constant in
`src/server_local.py` must be updated.

---

## 6. Initial bulk index

After the services are running, queue all files in a watched directory for indexing:

```bash
# Via MCP tool (from a Claude session):
# search_hybrid → reindex_path(path="/your/project", recursive=true, force=true)

# Or directly via psql:
INSERT INTO index_queue(file_path, event_type, status)
SELECT file_path, 'modify', 'pending'
FROM file_metadata;
```

Or use `scripts/bulk_index.py` if it exists.

---

## 7. Verify the index

```bash
source venv/bin/activate
python scripts/verify_index.py
```

Or via MCP `index_status` tool — returns `total_files`, `total_chunks`,
`total_embeddings`, and `queue.pending`.

---

## Recommended Follow-ups (not done in this reconciliation)

1. **De-hardcode `CONFIG_PATH`** — read from `VECTOR_INDEXER_CONFIG` env var with a
   fallback, so the service works from any checkout location without editing source.
2. **Fix `pyproject.toml` scripts** — `vector-indexer-worker` and `vector-indexer-mcp`
   point at the old Supabase modules; update them to point at `daemon.worker_local:main`
   and `src.server_local:main` (or remove them and rely on the systemd units).
3. **Prune dead dependencies** — `supabase`, `postgrest-py`, and `tiktoken` are listed
   in `requirements.txt` / `pyproject.toml` but not used by the `*_local.py` runtime.
   Removing them reduces install size and eliminates a large dependency surface.
4. **Add `asyncpg` to `pyproject.toml` dependencies** — currently only in
   `requirements.txt`; the two should stay in sync.
