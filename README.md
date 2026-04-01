# Vector Indexer MCP - Real-Time Vector Indexing System

**Status**: Phase 4 Complete ✓
**Version**: 0.4.0

Automatic, real-time vector indexing system for code repositories and documentation. Monitors configured directories, generates semantic embeddings, and enables vector search via MCP server.

## Architecture

The system consists of three components working together:

### Watcher Daemon (Phase 3) - `daemon/watcher.py`
- Monitors configured directories using inotify (watchdog library)
- Detects file changes: create, modify, delete, move
- Debounces rapid changes (100ms window)
- Filters by extension and exclude patterns
- Batch inserts events into `index_queue`

### Worker Daemon (Phase 2) - `daemon/worker.py`
- Polls `index_queue` for pending events
- Processes files through the indexing pipeline:
  1. **TextChunker** - Token-aware chunking (tiktoken)
  2. **EmbeddingGenerator** - 384-dim vectors (sentence-transformers)
  3. **Database Storage** - Chunks + embeddings in Supabase
- SHA256 hash-based change detection (skip unchanged files)
- Error handling with queue status tracking

### MCP Server (Phase 4) - `src/server.py`
- Exposes 7 tools to Claude via Model Context Protocol
- **Search Tools**: semantic, lexical, hybrid search
- **Management Tools**: index_status, reindex_path, get_file_chunks, search_similar_files
- Lazy-loaded embedding model (first query only)
- Response envelope format for all tools

### Pipeline Flow

```
File System → Watcher → Queue → Worker → Vector Database → MCP Server → Claude
  (inotify)  (debounce) (async)  (chunk)  (embeddings)   (search)    (query)
```

## Database Schema

The worker expects these tables (created in Phase 1):

- `file_metadata` - File information and indexing status
- `file_chunks` - Text chunks with line/token metadata
- `file_embeddings` - 384-dim vectors with pgvector
- `index_queue` - Event queue for file changes
- `index_stats` - Indexing statistics

## Installation

```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp

# Install dependencies
pip install -r requirements.txt

# Or install as package
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key

# Embedding model
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2

# Chunking
MAX_TOKENS=500
OVERLAP_TOKENS=50

# Worker
WORKER_BATCH_SIZE=10
WORKER_POLL_INTERVAL=5
```

## Running the System

### Both Services Required

For real-time indexing, run both daemons as user services:

```bash
# Start watcher (monitors file changes)
systemctl --user start vector-indexer
systemctl --user enable vector-indexer

# Start worker (processes queue)
systemctl --user start vector-indexer-worker
systemctl --user enable vector-indexer-worker

# Enable lingering for persistence after logout
loginctl enable-linger $USER

# Check status
systemctl --user status vector-indexer vector-indexer-worker

# Monitor logs
journalctl --user -u vector-indexer -u vector-indexer-worker -f
```

**Note**: Services run in user mode (not system mode) for better security and isolation. The `loginctl enable-linger` command ensures services persist after logout.

### Development Mode

Run directly without systemd:

```bash
# Terminal 1: Watcher
python -m daemon.watcher

# Terminal 2: Worker
python -m daemon.worker
```

## Usage Example

### Automatic Indexing

With both services running, file changes are automatically indexed:

```bash
# Create a file in watched directory
echo "# Test Document" > /srv/latvian_mcp/test.md
echo "This is a test." >> /srv/latvian_mcp/test.md

# Watcher detects change → adds to queue → worker processes
```

### Manual Queue Insert

You can also manually trigger indexing:

```sql
-- Add file to index queue
INSERT INTO index_queue (file_path, event, priority)
VALUES ('/path/to/file.txt', 'create', 1);

-- Worker automatically processes:
-- 1. Read file content
-- 2. Calculate SHA256 hash
-- 3. Generate chunks (respecting token limits)
-- 4. Generate embeddings (384-dim vectors)
-- 5. Store in file_chunks and file_embeddings tables
-- 6. Update index_stats
```


## Systemd Service

The vector indexer can run as a systemd service for automatic startup and process management.

### Installation

1. Copy the service file:
```bash
sudo cp mcp-sse-vector-indexer-mcp.service /etc/systemd/system/
sudo systemctl daemon-reload
```

2. Enable and start the service:
```bash
sudo systemctl enable mcp-sse-vector-indexer-mcp
sudo systemctl start mcp-sse-vector-indexer-mcp
```

3. Check status:
```bash
sudo systemctl status mcp-sse-vector-indexer-mcp
```

### Features

- **Port conflict prevention**: Checks if port 5568 is already in use before starting
- **Automatic restart**: Restarts on failure after 10 seconds
- **Safe shutdown**: 30-second timeout for graceful termination
- **Logging**: View logs with `journalctl -u mcp-sse-vector-indexer-mcp -f`

### Management

```bash
# Stop service
sudo systemctl stop mcp-sse-vector-indexer-mcp

# Restart service
sudo systemctl restart mcp-sse-vector-indexer-mcp

# Disable auto-start
sudo systemctl disable mcp-sse-vector-indexer-mcp
```


## Event Types

| Event | Description | Action |
|-------|-------------|--------|
| `create` | New file added | Generate chunks + embeddings |
| `modify` | File content changed | Re-generate if hash differs |
| `delete` | File removed | Delete chunks + embeddings |
| `move` | File path changed | Update file_path in metadata |

## Performance

- **Chunking**: ~10,000 lines/second
- **Embedding**: ~50 chunks/second (batch mode)
- **Token counting**: Uses tiktoken (same as GPT models)
- **Memory**: ~2GB for embedding model

## Monitoring

Check worker status:

```sql
-- Queue status
SELECT status, COUNT(*)
FROM index_queue
GROUP BY status;

-- Index stats
SELECT * FROM index_stats;

-- Recent errors
SELECT file_path, error_message, processed_at
FROM index_queue
WHERE status = 'failed'
ORDER BY processed_at DESC
LIMIT 10;
```

## Error Handling

The worker uses queue status for error tracking:

- `pending` - Waiting to be processed
- `processing` - Currently being processed
- `completed` - Successfully processed
- `failed` - Processing failed (see error_message)

Failed items remain in queue for manual inspection/retry.

## Development

Run tests:
```bash
pytest tests/
```

Code formatting:
```bash
black daemon/
ruff daemon/
```

Type checking:
```bash
mypy daemon/
```

## Configuration (Watcher)

Edit `config/watcher.yaml` to customize:

```yaml
watcher:
  watch_paths:
    - /srv/latvian_mcp
    - /srv/latvian_xtts
    - /srv/latvian_learning
    - /srv/claude-mpm

  exclude_patterns:
    - __pycache__
    - .git
    - venv
    - "*.log"

  include_extensions:
    - .py
    - .md
    - .txt
    - .json
    - .yaml

  max_file_size_mb: 10
  debounce_ms: 100
  batch_size: 50
```

## Testing

```bash
# Test watcher components
python test_watcher_core.py

# Test worker pipeline
python test_pipeline.py

# Test MCP server
python test_mcp_server.py
```

## MCP Server Usage (Phase 4)

### Available Tools

1. **search_semantic** - Vector similarity search for concepts
2. **search_lexical** - Full-text search for exact keywords
3. **search_hybrid** - Combined semantic + lexical (best of both)
4. **index_status** - Get index health statistics
5. **reindex_path** - Force reindex a file or directory
6. **get_file_chunks** - View how a file was chunked
7. **search_similar_files** - Find files similar to a reference file

### Quick Start

```bash
# Run MCP server standalone
cd /srv/latvian_mcp/servers/vector-indexer-mcp
source venv/bin/activate
python -m src
```

### Register with Claude

Add to `~/.config/claude/mcp_servers.json`:

```json
{
  "vector-indexer": {
    "command": "/srv/latvian_mcp/servers/vector-indexer-mcp/venv/bin/python",
    "args": ["-m", "src"],
    "env": {
      "SUPABASE_URL": "https://zbhddlduxcwhgibhbeuu.supabase.co",
      "SUPABASE_SERVICE_KEY": "your_service_key_here"
    }
  }
}
```

## Documentation

- **PHASE4_MCP_SERVER.md** - Phase 4 MCP server (NEW)
- **PHASE3_SUMMARY.md** - Phase 3 file watcher
- **PHASE3_WATCHER.md** - Detailed watcher documentation
- **IMPLEMENTATION_SUMMARY.md** - Phase 2 indexing worker
- **INSTALL.md** - Installation guide

## License

MIT
