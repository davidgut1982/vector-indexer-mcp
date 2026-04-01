# Phase 5 Completion Checklist

**Vector Indexer MCP - Initial Index & Optimization**

Use this checklist to verify Phase 5 is complete and ready for initial indexing.

---

## ✅ Phase 5 Scripts Complete

- [x] **bulk_index.py** - Bulk file indexing script created and updated
- [x] **verify_index.py** - Index integrity validation script created and updated
- [x] **optimize_index.py** - Performance optimization script created and updated
- [x] **README.md** - Comprehensive documentation with examples
- [x] **PHASE5_SUMMARY.md** - Technical summary and implementation details
- [x] **QUICK_START.md** - Quick reference guide for users

---

## 🔧 Schema Alignment Complete

- [x] All scripts reference correct table names from migration 020:
  - `file_metadata` ✅
  - `file_chunks` (not `text_chunks`) ✅
  - `file_embeddings` (not `embeddings`) ✅
  - `index_queue` ✅
  - `index_stats` ✅

- [x] All scripts reference correct field names:
  - `chunk_text` (not `content`) ✅
  - `chunk_start_line` (not `start_line`) ✅
  - `chunk_end_line` (not `end_line`) ✅

- [x] All scripts reference correct index names:
  - `idx_file_embeddings_vector` (not `embeddings_embedding_idx`) ✅

---

## 📝 Scripts Validated

- [x] Python syntax validation passed for all scripts
- [x] Import paths correct (daemon/chunker.py, daemon/embedder.py)
- [x] Environment variable handling implemented
- [x] Error handling for missing database tables
- [x] Colored terminal output for readability
- [x] Help text and argument parsing complete

---

## 📚 Documentation Complete

- [x] **scripts/README.md** - Full documentation with:
  - Usage examples for all scripts
  - Configuration details
  - Troubleshooting guide
  - Performance notes
  - Typical workflows

- [x] **PHASE5_SUMMARY.md** - Technical details:
  - Script purposes and features
  - Database schema alignment
  - Integration with components
  - Performance metrics
  - Next steps

- [x] **scripts/QUICK_START.md** - Quick reference:
  - 5-minute quick start
  - Common commands
  - Troubleshooting quick fixes
  - Performance benchmarks

---

## 🎯 Ready for User

### Prerequisites User Must Complete

Before running scripts, user needs to:

- [ ] **Apply migration 020** in Supabase Studio
  - File: `/srv/latvian_mcp/migrations/020_vector_search_indexer.sql`
  - Location: Supabase Studio > SQL Editor
  - Verify: Run `python scripts/verify_index.py`

- [ ] **Install dependencies** in virtual environment
  ```bash
  cd /srv/latvian_mcp/servers/vector-indexer-mcp
  source venv/bin/activate
  pip install -r requirements.txt
  ```

- [ ] **Configure environment variables**
  - Copy `.env.example` to `.env`
  - Set `SUPABASE_URL` and `SUPABASE_KEY`
  - Verify: Run `python scripts/verify_index.py`

- [ ] **Review configuration**
  - Check `config/watcher.yaml`
  - Verify watch_paths are correct
  - Adjust include/exclude patterns if needed

---

## 🚀 Initial Indexing Workflow

Once prerequisites are complete, user should:

1. [ ] **Preview indexing**
   ```bash
   python scripts/bulk_index.py --dry-run
   ```

2. [ ] **Bulk index corpus**
   ```bash
   python scripts/bulk_index.py --execute
   ```
   - Expected time: 30-60 minutes for ~1,200 files
   - Monitor progress and ETA
   - Note any errors

3. [ ] **Verify index integrity**
   ```bash
   python scripts/verify_index.py
   ```
   - Should see: "✓ INDEX VERIFICATION PASSED"
   - Fix any issues found

4. [ ] **Optimize index** (optional)
   ```bash
   python scripts/optimize_index.py --execute
   ```
   - Run SQL commands in Supabase Studio
   - Commands provided in output

---

## 🔍 Success Criteria

After initial indexing, verify:

- [ ] **All files indexed**
  - Run: `python scripts/verify_index.py`
  - Check: "Files in index" matches "Files in filesystem"

- [ ] **No orphaned records**
  - Run: `python scripts/verify_index.py`
  - Check: "Orphaned chunks: 0" and "Orphaned embeddings: 0"

- [ ] **Chunk/embedding parity**
  - Run: `python scripts/verify_index.py`
  - Check: "✓ Chunk count matches embedding count"

- [ ] **Search tools work**
  - Test: `mcp__vector-indexer-mcp__search_semantic(query="test")`
  - Should return results

- [ ] **Index status available**
  - Test: `mcp__vector-indexer-mcp__index_status()`
  - Should return health metrics

---

## 📊 Expected Results

After successful Phase 5 completion:

**Database Tables**:
- `file_metadata`: ~1,000-2,000 rows (depends on corpus)
- `file_chunks`: ~10,000-30,000 rows
- `file_embeddings`: ~10,000-30,000 rows (matches chunks)
- `index_queue`: 0 pending (initially)
- `index_stats`: Optional (future use)

**Index Health**:
- ✅ All tables created
- ✅ HNSW index exists on file_embeddings.embedding
- ✅ GIN index exists on file_chunks.fts_vector
- ✅ All foreign key constraints valid
- ✅ No orphaned records

**Performance**:
- Semantic search: <500ms for 20 results
- Lexical search: <100ms for 20 results
- Hybrid search: <600ms for 20 results
- Index status: <50ms

---

## 🐛 Common Issues and Fixes

### Issue: "Database tables do not exist"

**Status**: ❌ Migration not applied

**Fix**: Apply migration 020 in Supabase Studio first

---

### Issue: "ModuleNotFoundError"

**Status**: ❌ Dependencies not installed

**Fix**: Run `pip install -r requirements.txt` in venv

---

### Issue: Slow indexing (>10 seconds per file)

**Status**: ⚠️ CPU-only embedding (no GPU)

**Fix**: Expected behavior without GPU. Consider:
- Running during off-peak hours
- Using GPU if available
- Reducing corpus size

---

### Issue: "Files in filesystem but not indexed"

**Status**: ⚠️ New files added or indexing incomplete

**Fix**: Run `python scripts/bulk_index.py --execute` again

---

## 🎯 Phase 5 Deliverables Summary

| Deliverable | Status | Location |
|------------|--------|----------|
| bulk_index.py | ✅ Complete | `/srv/latvian_mcp/servers/vector-indexer-mcp/scripts/` |
| verify_index.py | ✅ Complete | `/srv/latvian_mcp/servers/vector-indexer-mcp/scripts/` |
| optimize_index.py | ✅ Complete | `/srv/latvian_mcp/servers/vector-indexer-mcp/scripts/` |
| README.md | ✅ Complete | `/srv/latvian_mcp/servers/vector-indexer-mcp/scripts/` |
| PHASE5_SUMMARY.md | ✅ Complete | `/srv/latvian_mcp/servers/vector-indexer-mcp/` |
| QUICK_START.md | ✅ Complete | `/srv/latvian_mcp/servers/vector-indexer-mcp/scripts/` |
| PHASE5_CHECKLIST.md | ✅ Complete | `/srv/latvian_mcp/servers/vector-indexer-mcp/` |

**Total lines of code**: ~1,200 lines (scripts)
**Total documentation**: ~1,500 lines (markdown)

---

## 🔜 Next Steps (After Phase 5)

### Phase 6: File Watcher Daemon

- [ ] Start file watcher daemon (`python daemon/watcher.py`)
- [ ] Verify automatic indexing on file changes
- [ ] Test queue processing

### Phase 7: Production Deployment

- [ ] Configure systemd service
- [ ] Enable auto-start on boot
- [ ] Set up monitoring and logging

### Phase 8: Integration Testing

- [ ] Test all MCP search tools
- [ ] Verify performance under load
- [ ] Run end-to-end workflows

---

## ✅ Phase 5 Sign-Off

**Development Complete**: ✅ Yes
**Schema Aligned**: ✅ Yes
**Documentation Complete**: ✅ Yes
**Scripts Validated**: ✅ Yes
**Ready for User**: ✅ Yes (pending migration)

**Completion Date**: 2025-12-18

---

**Phase 5: COMPLETE** 🎉

All bulk indexing and optimization scripts are ready for use. User can now apply the migration and begin initial corpus indexing.
