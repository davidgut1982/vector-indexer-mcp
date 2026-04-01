# Vector Indexer Scripts

Phase 5 operational scripts for bulk indexing and optimization.

## Prerequisites

**IMPORTANT**: The database migration MUST be executed before using these scripts.

```bash
# Check if migration was run
python scripts/verify_index.py
```

If tables don't exist, you'll see:
```
ERROR: Database tables do not exist!
Please run the migration first.
```

**To run migration:**
1. Open Supabase Studio (https://supabase.com/dashboard)
2. Go to SQL Editor
3. Execute: `/srv/latvian_mcp/migrations/020_vector_search_indexer.sql`

## Scripts Overview

### 1. bulk_index.py - Initial Indexing

Index all existing files from configured watch directories.

**Usage:**

```bash
# Preview what will be indexed
python scripts/bulk_index.py --dry-run

# Actually index files (recommended first time)
python scripts/bulk_index.py --execute

# Index specific path
python scripts/bulk_index.py --execute --path /srv/latvian_mcp/servers

# Re-index everything (including unchanged files)
python scripts/bulk_index.py --execute --no-skip-unchanged
```

**Features:**
- Respects include/exclude patterns from `config/watcher.yaml`
- Computes file hashes to detect changes
- Classifies files as: new, modified, unchanged
- Progress reporting with ETA
- Batch processing for efficiency
- Graceful error handling per file

**Performance:**
- ~2-5 seconds per file (depends on file size and chunking)
- Embedding model loads once (shared across files)
- Estimated time for full corpus: 30-60 minutes

**Output:**
```
Scanning directories...
Found 1,243 files matching criteria

Classification:
  New files: 1,200
  Modified files: 43
  Unchanged files: 0

Initializing chunker and embedder...
Indexing files...

[1/1243] server.py (ETA: 45.2m)
  Path: /srv/latvian_mcp/servers/vector-indexer-mcp/src/server.py
  ✓ indexed 12 chunks

...

BULK INDEX COMPLETE
Success: 1,240 files
Errors: 3 files
Total time: 42.3 minutes
Average: 2.0 seconds per file
```

---

### 2. verify_index.py - Integrity Validation

Validate index integrity and detect issues.

**Usage:**

```bash
# Basic verification
python scripts/verify_index.py

# Verify specific path
python scripts/verify_index.py --path /srv/latvian_mcp

# Show detailed mismatch lists
python scripts/verify_index.py --detailed

# Fix orphaned records
python scripts/verify_index.py --fix-orphans
```

**Checks:**
1. **Index Health** - File/chunk/embedding counts
2. **Filesystem Sync** - Files in index vs filesystem
3. **Chunks & Embeddings** - All chunks have embeddings
4. **Orphaned Records** - Chunks/embeddings without parents

**Output:**
```
VECTOR INDEX VERIFICATION

Index Health Statistics
  Files indexed: 1,240
  File chunks: 15,678
  File embeddings: 15,678
  Total size: 342.56 MB
  ✓ Chunk count matches embedding count

Filesystem Synchronization
  Files in index: 1,240
  Files in filesystem: 1,242
  Matching: 1,240
  ⚠ Files in filesystem but not indexed: 2

Chunks & Embeddings Integrity
  Total chunks: 15,678
  Chunks with embeddings: 15,678
  ✓ All chunks have embeddings

Orphaned Records Check
  Orphaned chunks: 0
  Orphaned embeddings: 0
  ✓ No orphaned records

✓ INDEX VERIFICATION PASSED
All checks passed - index is healthy
```

---

### 3. optimize_index.py - Performance Tuning

Optimize index performance with VACUUM, statistics updates, and index tuning.

**Usage:**

```bash
# Preview optimizations
python scripts/optimize_index.py --dry-run

# Show optimization instructions
python scripts/optimize_index.py --execute

# Include HNSW index rebuild (use with caution)
python scripts/optimize_index.py --execute --rebuild-index
```

**Optimizations:**
1. **VACUUM ANALYZE** - Reclaim space and update statistics
2. **Update Statistics** - Improve query planning
3. **Rebuild HNSW Index** - Optimize vector index (optional)
4. **Index Bloat Check** - Detect bloat from modifications

**Note:** Most optimizations require direct PostgreSQL access via Supabase SQL Editor.

**Output:**
```
VECTOR INDEX OPTIMIZATION

Table Statistics
  file_metadata: 1,240 rows
  file_chunks: 15,678 rows
  file_embeddings: 15,678 rows

Index Health
  Embeddings indexed: 15,678
  HNSW index: exists

Optimization Plan

1. VACUUM ANALYZE (reclaim space and update statistics)
   SQL:
   ```sql
   VACUUM ANALYZE file_metadata;
   VACUUM ANALYZE file_chunks;
   VACUUM ANALYZE file_embeddings;
   ```

2. Update Statistics (improve query planning)
   SQL:
   ```sql
   ANALYZE file_metadata;
   ANALYZE file_chunks;
   ANALYZE file_embeddings;
   ```

Additional Recommendations
  Small dataset (15,678 embeddings)
  Consider:
    - Using smaller HNSW parameters (m=8, ef_construction=32)
    - Current settings likely optimal

Query Optimization Tips
  - Use appropriate similarity thresholds (0.5-0.7 for semantic search)
  - Limit results to reasonable numbers (10-50)
  - Use file_type and path filters to reduce search space
  - Monitor query times with index_status tool
```

---

## Typical Workflow

### Initial Setup (After Migration)

```bash
# 1. Preview what will be indexed
python scripts/bulk_index.py --dry-run

# 2. Perform initial indexing
python scripts/bulk_index.py --execute

# 3. Verify integrity
python scripts/verify_index.py

# 4. Optimize (optional for initial index)
python scripts/optimize_index.py --execute
```

### Regular Maintenance

```bash
# Re-index changed files (daemon does this automatically)
# Manual re-index if needed:
python scripts/bulk_index.py --execute  # Only indexes new/modified

# Weekly verification
python scripts/verify_index.py

# Monthly optimization (if heavy churn)
python scripts/optimize_index.py --execute
```

### Troubleshooting

**Issue: "Database tables do not exist"**
```bash
# Solution: Run migration in Supabase Studio
# File: /srv/latvian_mcp/migrations/020_vector_search_indexer.sql
```

**Issue: "Files in filesystem but not indexed"**
```bash
# Solution: Run bulk indexing
python scripts/bulk_index.py --execute
```

**Issue: "Chunks without embeddings"**
```bash
# Solution: Re-index affected files
python scripts/bulk_index.py --execute --no-skip-unchanged
```

**Issue: "Orphaned records"**
```bash
# Solution: Clean up orphans
python scripts/verify_index.py --fix-orphans
```

---

## Configuration

Scripts read from:
- **Config**: `/srv/latvian_mcp/servers/vector-indexer-mcp/config/watcher.yaml`
- **Environment**: `.env` file (SUPABASE_URL, SUPABASE_KEY)

**Key settings** (watcher.yaml):
```yaml
watcher:
  watch_paths:
    - /srv/latvian_mcp
    - /srv/latvian_xtts
    - /srv/latvian_learning
    - /srv/claude-mpm

  include_extensions:
    - .py
    - .md
    - .txt
    # ... etc

  exclude_patterns:
    - __pycache__
    - .git
    - node_modules
    # ... etc

  max_file_size_mb: 10
```

---

## Dependencies

All dependencies are in the main `pyproject.toml`:

```toml
[tool.poetry.dependencies]
python = "^3.10"
sentence-transformers = "^3.3.1"
tiktoken = "^0.8.0"
supabase = "^2.11.1"
watchdog = "^6.0.0"
pyyaml = "^6.0.2"
```

---

## Performance Notes

### Bulk Indexing
- **Speed**: ~2-5 seconds per file
- **Bottleneck**: Embedding generation (GPU helps)
- **Memory**: ~1-2 GB (embedding model in memory)
- **Disk I/O**: Moderate (reading files sequentially)

### Database Operations
- **Inserts**: Batched per file (chunks + embeddings)
- **Upserts**: Uses ON CONFLICT for file_metadata
- **Network**: Supabase REST API calls

### HNSW Index
- **Small datasets** (<10k embeddings): m=8, ef_construction=32
- **Medium datasets** (10k-100k): m=16, ef_construction=64 (default)
- **Large datasets** (>100k): m=24-32, ef_construction=128

---

## Error Handling

Scripts handle errors gracefully:
- **File read errors**: Skip and continue (log error)
- **Encoding errors**: Skip non-UTF-8 files
- **Database errors**: Report and continue
- **Network errors**: Retry logic built into Supabase client

All errors are reported in summary at end of script.

---

## Monitoring

Check indexing progress:
```bash
# Use MCP tool
mcp__vector-indexer-mcp__index_status

# Or verify script
python scripts/verify_index.py
```

---

## Next Steps After Phase 5

1. **Start File Watcher Daemon** (Phase 6)
   ```bash
   # Will automatically index new/modified files
   python daemon/watcher.py
   ```

2. **Configure as Systemd Service** (Phase 7)
   ```bash
   # Auto-start on boot
   systemctl enable vector-indexer-daemon
   systemctl start vector-indexer-daemon
   ```

3. **Test Search Tools**
   ```bash
   # Via MCP
   mcp__vector-indexer-mcp__search_semantic(query="authentication patterns")
   ```

---

**Phase 5 Complete** ✓

Scripts ready for bulk indexing and optimization after migration is applied.
