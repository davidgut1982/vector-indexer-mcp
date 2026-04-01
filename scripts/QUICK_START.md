# Quick Start Guide - Vector Indexer Scripts

**Phase 5: Initial Index & Optimization**

## Prerequisites Checklist

- [ ] Migration 020 applied in Supabase Studio
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Environment variables set (`.env` file with SUPABASE_URL and SUPABASE_KEY)
- [ ] Configuration reviewed (`config/watcher.yaml`)

---

## 5-Minute Quick Start

### Step 1: Verify Migration

```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp
source venv/bin/activate
python scripts/verify_index.py
```

**Expected output if migration NOT applied**:
```
ERROR: Database tables do not exist!
Please run the migration first.
```

**Expected output if migration IS applied**:
```
✓ Database tables exist
...
✓ INDEX VERIFICATION PASSED
```

---

### Step 2: Preview Indexing (Dry Run)

```bash
python scripts/bulk_index.py --dry-run
```

**Expected output**:
```
Scanning directories...
Found 1,243 files matching criteria

DRY RUN - Preview of files to index:
  1. /srv/latvian_mcp/servers/vector-indexer-mcp/src/server.py
  2. /srv/latvian_mcp/servers/vector-indexer-mcp/README.md
  ...
  20. /srv/latvian_mcp/shared/response.py
  ... and 1,223 more files

To actually index these files, run with --execute
```

---

### Step 3: Bulk Index Files

```bash
# Full indexing (may take 30-60 minutes for large corpus)
python scripts/bulk_index.py --execute
```

**OR start with a small subset**:
```bash
# Test with just the scripts directory first
python scripts/bulk_index.py --execute --path /srv/latvian_mcp/servers/vector-indexer-mcp/scripts
```

**Expected output**:
```
Scanning directories...
Found 3 files matching criteria

Checking existing index...
  Currently indexed: 0 files

Classification:
  New files: 3
  Modified files: 0
  Unchanged files: 0

Will index 3 files

Initializing chunker and embedder...
Indexing files...

[1/3] bulk_index.py (ETA: calculating...)
  Path: /srv/latvian_mcp/servers/vector-indexer-mcp/scripts/bulk_index.py
  ✓ indexed 12 chunks

[2/3] verify_index.py (ETA: 0.1m)
  Path: /srv/latvian_mcp/servers/vector-indexer-mcp/scripts/verify_index.py
  ✓ indexed 8 chunks

[3/3] optimize_index.py (ETA: 0.0m)
  Path: /srv/latvian_mcp/servers/vector-indexer-mcp/scripts/optimize_index.py
  ✓ indexed 6 chunks

============================================================
BULK INDEX COMPLETE
============================================================

Success: 3 files
Errors: 0 files
Total time: 0.5 minutes
Average: 10.0 seconds per file

Next steps:
  1. Run verification: python scripts/verify_index.py
  2. Optimize index: python scripts/optimize_index.py
```

---

### Step 4: Verify Index

```bash
python scripts/verify_index.py
```

**Expected output**:
```
============================================================
VECTOR INDEX VERIFICATION
============================================================

Checking database...
✓ Database tables exist

Index Health Statistics
  Files indexed: 3
  File chunks: 26
  File embeddings: 26
  Total size: 0.12 MB
  ✓ Chunk count matches embedding count

Filesystem Synchronization
  Files in index: 3
  Files in filesystem: 3
  Matching: 3

Chunks & Embedings Integrity
  Total chunks: 26
  Chunks with embeddings: 26
  ✓ All chunks have embeddings

Orphaned Records Check
  Orphaned chunks: 0
  Orphaned embeddings: 0
  ✓ No orphaned records

============================================================
✓ INDEX VERIFICATION PASSED
All checks passed - index is healthy
============================================================
```

---

### Step 5: Optimize (Optional)

```bash
python scripts/optimize_index.py --execute
```

**Expected output**:
```
============================================================
VECTOR INDEX OPTIMIZATION
============================================================

Table Statistics
  file_metadata: 3 rows
  file_chunks: 26 rows
  file_embeddings: 26 rows

Index Health
  Embeddings indexed: 26
  HNSW index: exists

Optimization Plan

Note: Some optimizations require direct PostgreSQL access.
The following SQL commands should be run in Supabase SQL Editor:

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
  Small dataset (26 embeddings)
  Consider:
    - Using smaller HNSW parameters (m=8, ef_construction=32)
    - Current settings likely optimal

Query Optimization Tips
  - Use appropriate similarity thresholds (0.5-0.7 for semantic search)
  - Limit results to reasonable numbers (10-50)
  - Use file_type and path filters to reduce search space
  - Monitor query times with index_status tool

============================================================
OPTIMIZATION INSTRUCTIONS PROVIDED

Next steps:
  1. Run SQL commands in Supabase SQL Editor
  2. Monitor query performance
  3. Verify with: python scripts/verify_index.py
```

---

## Common Commands

### Re-index Changed Files Only

```bash
python scripts/bulk_index.py --execute
```

This will:
- Skip unchanged files (by comparing hash)
- Index new files
- Re-index modified files

---

### Force Re-index Everything

```bash
python scripts/bulk_index.py --execute --no-skip-unchanged
```

This will re-index ALL files regardless of whether they changed.

---

### Index Specific Directory

```bash
python scripts/bulk_index.py --execute --path /srv/latvian_mcp/servers
```

---

### Check Index Health

```bash
python scripts/verify_index.py
```

---

### Fix Orphaned Records

```bash
python scripts/verify_index.py --fix-orphans
```

---

### Show Detailed Verification

```bash
python scripts/verify_index.py --detailed
```

This will show lists of:
- Files in index but not filesystem
- Files in filesystem but not indexed
- Missing chunk IDs

---

## Troubleshooting Quick Fixes

### "Database tables do not exist"

**Fix**: Run migration in Supabase Studio
```
File: /srv/latvian_mcp/migrations/020_vector_search_indexer.sql
```

---

### "ModuleNotFoundError: sentence_transformers"

**Fix**: Install dependencies
```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp
source venv/bin/activate
pip install -r requirements.txt
```

---

### "Connection refused" or Supabase errors

**Fix**: Check environment variables
```bash
# Verify .env file exists and has:
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-service-role-key

# Test connection
python -c "from supabase import create_client; import os; from dotenv import load_dotenv; load_dotenv(); print('OK' if create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY')) else 'FAIL')"
```

---

### Slow indexing performance

**Causes**:
1. No GPU available (CPU-only embedding is ~10x slower)
2. Large files (exceeding max_file_size_mb)
3. Network latency to Supabase

**Fixes**:
- Use GPU if available (set `device='cuda'` in embedder.py)
- Reduce `max_file_size_mb` in watcher.yaml
- Run during off-peak hours
- Consider regional Supabase deployment

---

### Files not being indexed

**Check**:
1. File extension in `include_extensions` (watcher.yaml)
2. File not matching `exclude_patterns` (watcher.yaml)
3. File size under `max_file_size_mb` (watcher.yaml)
4. File is UTF-8 text (binary files skipped)

**Debug**:
```bash
# Run with --dry-run to see what would be indexed
python scripts/bulk_index.py --dry-run --path /path/to/specific/dir
```

---

## Full Corpus Indexing Workflow

For production initial indexing of entire codebase:

```bash
# 1. Verify prerequisites
python scripts/verify_index.py

# 2. Preview (check file count)
python scripts/bulk_index.py --dry-run

# 3. Index in stages (optional - for testing)
python scripts/bulk_index.py --execute --path /srv/latvian_mcp/servers/vector-indexer-mcp
python scripts/verify_index.py

# 4. Index remaining directories
python scripts/bulk_index.py --execute --path /srv/latvian_mcp/servers
python scripts/verify_index.py

# 5. Index full corpus
python scripts/bulk_index.py --execute

# 6. Final verification
python scripts/verify_index.py

# 7. Optimize
python scripts/optimize_index.py --execute
# Then run SQL commands in Supabase Studio
```

**Expected total time**: 30-60 minutes for ~1,200 files

---

## Next Steps After Indexing

### 1. Start File Watcher Daemon

```bash
python daemon/watcher.py
```

This will automatically index new/modified files going forward.

---

### 2. Configure as Systemd Service

```bash
sudo cp vector-indexer.service /etc/systemd/system/
sudo systemctl enable vector-indexer
sudo systemctl start vector-indexer
sudo systemctl status vector-indexer
```

---

### 3. Test Search via MCP

```bash
# Example semantic search
mcp__vector-indexer-mcp__search_semantic(query="authentication patterns")

# Example lexical search
mcp__vector-indexer-mcp__search_lexical(query="def handle_request")

# Check index status
mcp__vector-indexer-mcp__index_status()
```

---

## Performance Benchmarks

**Typical performance** (CPU-only, no GPU):
- Small files (<5 KB): ~2 seconds
- Medium files (5-50 KB): ~3-5 seconds
- Large files (50-500 KB): ~8-15 seconds

**With GPU** (CUDA-enabled):
- Small files: ~0.5 seconds
- Medium files: ~1-2 seconds
- Large files: ~3-5 seconds

**Bottleneck**: Embedding generation (90% of time per file)

---

## Support

For issues or questions:
1. Check `scripts/README.md` for detailed documentation
2. Check `PHASE5_SUMMARY.md` for technical details
3. Review migration file: `/srv/latvian_mcp/migrations/020_vector_search_indexer.sql`

---

**Quick Start Complete** ✅

You're now ready to index your corpus and start using vector search!
