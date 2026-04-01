# Phase 4 MCP Server - Installation Guide

## Prerequisites

- Phase 1 database migration applied (creates tables and functions)
- Python 3.13+ with venv
- Supabase credentials configured

## Quick Installation

### 1. Install MCP Package

```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp
source venv/bin/activate
pip install mcp
```

### 2. Verify Environment

Check `.env` file contains:

```env
SUPABASE_URL=https://zbhddlduxcwhgibhbeuu.supabase.co
SUPABASE_KEY=your_service_role_key
EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
```

### 3. Test the Server

```bash
python test_mcp_server.py
```

**Expected output**:
```
============================================================
Vector Indexer MCP Server - Test Suite
============================================================

Testing list_tools()...
✓ Found 7 tools:
  - search_semantic
  - search_lexical
  - search_hybrid
  - index_status
  - reindex_path
  - get_file_chunks
  - search_similar_files

✅ ALL TESTS PASSED
============================================================
```

### 4. Apply Database Migration (If Not Done)

```bash
# Check if migration is needed
psql $SUPABASE_URL -c "SELECT COUNT(*) FROM file_metadata;" 2>&1 | grep -q "does not exist" && echo "Migration needed"

# Apply migration
psql $SUPABASE_URL -f /srv/latvian_mcp/migrations/020_vector_search_indexer.sql
```

## Register with Claude

### Option 1: Manual Registration

Edit `~/.config/claude/mcp_servers.json`:

```json
{
  "vector-indexer": {
    "command": "/srv/latvian_mcp/servers/vector-indexer-mcp/venv/bin/python",
    "args": ["-m", "src"],
    "env": {
      "SUPABASE_URL": "https://zbhddlduxcwhgibhbeuu.supabase.co",
      "SUPABASE_SERVICE_KEY": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InpiaGRkbGR1eGN3aGdpYmhiZXV1Iiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTE5Njk2OCwiZXhwIjoyMDgwNzcyOTY4fQ.rXVZXQaEvBbxh8npS2YQauW13oxD1gfttH0ZZjzFQ6o"
    }
  }
}
```

**Note**: Use the actual service role key from your environment.

### Option 2: Merge with Existing Config

If you already have MCP servers configured:

```bash
# Backup existing config
cp ~/.config/claude/mcp_servers.json ~/.config/claude/mcp_servers.json.backup

# Add vector-indexer entry to existing JSON
```

## Verification

### 1. Check Server Starts

```bash
source venv/bin/activate
python -m src
```

Should display MCP server initialization messages (no errors).

**Press Ctrl+C to stop**.

### 2. Test Search Tool (Manual)

Create test input file:

```bash
cat > /tmp/test_search.json <<'EOF'
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "index_status",
    "arguments": {}
  }
}
EOF
```

Test the server:

```bash
cat /tmp/test_search.json | python -m src
```

**Expected**: JSON response with index health statistics.

## Troubleshooting

### Issue: Import Error on Startup

**Error**: `ModuleNotFoundError: No module named 'mcp'`

**Solution**:
```bash
source venv/bin/activate
pip install mcp
```

### Issue: Database Function Not Found

**Error**: `Could not find the function public.get_index_health`

**Solution**: Apply Phase 1 migration:
```bash
psql $SUPABASE_URL -f /srv/latvian_mcp/migrations/020_vector_search_indexer.sql
```

### Issue: Supabase Connection Error

**Error**: `ValueError: SUPABASE_URL environment variable is required`

**Solution**: Check `.env` file exists and contains credentials:
```bash
cat .env | grep SUPABASE_URL
```

### Issue: Model Download Timeout

**Error**: First query times out downloading model

**Solution**: Pre-download model:
```bash
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

## System Integration

### Start All Components

For full real-time indexing + search:

```bash
# 1. Start watcher (Phase 3)
sudo systemctl start vector-indexer

# 2. Start worker (Phase 2)
sudo systemctl start vector-indexer-worker

# 3. MCP server runs when Claude calls it (automatic)
```

### Check System Health

```bash
# Check watcher status
sudo systemctl status vector-indexer

# Check worker status
sudo systemctl status vector-indexer-worker

# Check index health (via MCP tool)
# Use Claude: "Use vector-indexer index_status"
```

## Uninstallation

```bash
# Remove from MCP config
# Edit ~/.config/claude/mcp_servers.json and remove "vector-indexer" entry

# Optional: Remove virtual environment
rm -rf /srv/latvian_mcp/servers/vector-indexer-mcp/venv

# Optional: Drop database tables
psql $SUPABASE_URL -c "DROP TABLE IF EXISTS file_embeddings, file_chunks, file_metadata, index_queue, index_stats CASCADE;"
```

## Next Steps

After installation:

1. **Index some files**: Use `reindex_path` tool to index a directory
2. **Test search**: Try `search_semantic` with a query
3. **Monitor status**: Check `index_status` regularly
4. **Explore similar files**: Use `search_similar_files` to discover patterns

## Support

- **Documentation**: See `PHASE4_MCP_SERVER.md` for detailed usage
- **Issues**: Check logs in test output
- **Database**: Query Supabase directly if needed

---

**Version**: 0.4.0
**Last Updated**: 2025-12-18
