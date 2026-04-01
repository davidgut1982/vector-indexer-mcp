# Vector Indexer MCP - PostgreSQL Migration

## Summary

vector-indexer-mcp has been updated to use **local PostgreSQL** (localhost:5433) instead of Supabase.

## Changes Made

### 1. Database Abstraction Layer
- Updated to use `/srv/latvian_mcp/shared/db_client.py`
- Supports both backends via `DB_BACKEND` environment variable
- All database operations use schema-qualified table names: `vectors.*`

### 2. Files Modified

**Server:**
- `src/server.py` - Replaced Supabase client with `get_db_client()`
- All RPC calls now use `vectors.search_hybrid`, `vectors.get_index_health`, etc.
- All table queries use `vectors.file_metadata`, `vectors.file_chunks`, etc.

**Worker:**
- `daemon/worker.py` - Updated to use `get_db_client()` 
- Removed `supabase_url` and `supabase_key` parameters from constructor

**Watcher:**
- `daemon/watcher.py` - Updated to use `get_db_client()`
- Replaced `_init_supabase()` with `_init_database()`

**Configuration:**
- `requirements.txt` - Added `psycopg2-binary>=2.9.0`
- `.env` - Added `DB_BACKEND=local` and PostgreSQL connection details
- `.env.example` - Updated with all new environment variables

### 3. Environment Variables

**New (for local PostgreSQL):**
```bash
DB_BACKEND=local
DB_HOST=localhost
DB_PORT=5433
DB_NAME=mpm_system
DB_USER=latvian_user
DB_PASSWORD=latvian_dev_password_2026
```

**Retained (for Supabase fallback):**
```bash
SUPABASE_URL=https://zbhddlduxcwhgibhbeuu.supabase.co
SUPABASE_KEY=<service_role_key>
```

### 4. Database Schema

All vector-indexer tables are in the `vectors` schema:
- `vectors.file_metadata`
- `vectors.file_chunks`
- `vectors.file_embeddings`
- `vectors.index_queue`
- `vectors.index_stats`

Functions:
- `vectors.search_hybrid(query_text, query_embedding, result_limit, alpha)`
- `vectors.search_vector(query_embedding, result_limit)`
- `vectors.search_fts(query_text, result_limit)`
- `vectors.get_index_health()`

## Testing

✅ **Verified:**
1. Server starts with `LocalPostgresClient`
2. Database connection successful
3. RPC calls to `vectors.get_index_health()` work
4. Table queries to `vectors.file_metadata` work
5. Queue operations to `vectors.index_queue` work

**Test command:**
```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp
source venv/bin/activate
DB_BACKEND=local python src/server.py
```

## Deployment

### Prerequisites
1. ✅ PostgreSQL running at localhost:5433
2. ✅ Database `mpm_system` exists
3. ✅ Schema `vectors` with all tables/functions created
4. ✅ `psycopg2-binary` installed in venv

### Steps

1. **Install dependencies:**
   ```bash
   cd /srv/latvian_mcp/servers/vector-indexer-mcp
   source venv/bin/activate
   pip install psycopg2-binary
   ```

2. **Verify .env file:**
   ```bash
   cat .env | grep DB_BACKEND
   # Should show: DB_BACKEND=local
   ```

3. **Restart services:**
   ```bash
   systemctl --user restart vector-indexer-worker
   systemctl --user restart vector-indexer
   ```

4. **Verify services:**
   ```bash
   systemctl --user status vector-indexer-worker
   journalctl --user -u vector-indexer-worker -n 50
   ```

## Rollback Plan

To switch back to Supabase:

1. Edit `.env`:
   ```bash
   DB_BACKEND=supabase
   ```

2. Restart services:
   ```bash
   systemctl --user restart vector-indexer-worker
   systemctl --user restart vector-indexer
   ```

## Benefits

1. **Lower latency** - Local database eliminates network round-trips
2. **No external dependencies** - No Supabase service dependency
3. **Better integration** - Same database as knowledge-mcp and todo-tracker-mcp
4. **Cost savings** - No Supabase usage fees
5. **Easier development** - Direct database access for debugging

## Notes

- The db_client abstraction supports both backends transparently
- No changes to tool interfaces or API contracts
- Existing Supabase code paths remain for potential rollback
- RPC function calls now use named parameter syntax: `param => value`
