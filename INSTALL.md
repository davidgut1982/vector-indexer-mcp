# Installation Guide - Vector Indexer Worker

## Prerequisites

- Python 3.10 or higher
- PostgreSQL with pgvector extension
- Supabase project with Phase 1 schema deployed

## Step 1: Install Dependencies

```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Or install as package
pip install -e .
```

## Step 2: Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit with your values
nano .env
```

Required configuration:
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_service_role_key_here
```

## Step 3: Test the Pipeline

```bash
# Run test suite
python test_pipeline.py
```

Expected output:
```
=== Testing TextChunker ===
Generated X chunks
✓ TextChunker tests passed

=== Testing EmbeddingGenerator ===
Model: paraphrase-multilingual-MiniLM-L12-v2
Embedding dimension: 384
✓ EmbeddingGenerator tests passed

=== Testing Integration ===
Document chunked into X pieces
✓ Integration tests passed

✓ All tests passed!
```

## Step 4: Run Worker (Development)

```bash
# Direct execution
python -m daemon.worker

# With custom poll interval
WORKER_POLL_INTERVAL=10 python -m daemon.worker
```

## Step 5: Production Deployment

### Install as systemd service:

```bash
# Copy service file
sudo cp vector-indexer-worker.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable vector-indexer-worker

# Start service
sudo systemctl start vector-indexer-worker

# Check status
sudo systemctl status vector-indexer-worker
```

### Monitor logs:

```bash
# Follow logs
sudo journalctl -u vector-indexer-worker -f

# View recent logs
sudo journalctl -u vector-indexer-worker -n 100
```

## Step 6: Verify Operation

Add test file to queue:

```sql
INSERT INTO index_queue (file_path, event, priority)
VALUES ('/tmp/test.txt', 'create', 1);
```

Check processing:

```sql
-- Queue status
SELECT * FROM index_queue WHERE file_path = '/tmp/test.txt';

-- File metadata
SELECT * FROM file_metadata WHERE file_path = '/tmp/test.txt';

-- Chunks
SELECT fc.chunk_index, fc.token_count, fc.start_line, fc.end_line
FROM file_chunks fc
JOIN file_metadata fm ON fc.file_id = fm.id
WHERE fm.file_path = '/tmp/test.txt';

-- Stats
SELECT * FROM index_stats;
```

## Troubleshooting

### Worker not processing queue:

1. Check service status: `sudo systemctl status vector-indexer-worker`
2. Check logs: `sudo journalctl -u vector-indexer-worker -n 50`
3. Verify database connection: Check SUPABASE_URL and SUPABASE_KEY
4. Check queue: `SELECT * FROM index_queue WHERE status = 'pending';`

### Out of memory:

- Reduce WORKER_BATCH_SIZE in .env (default: 10)
- Reduce MAX_TOKENS (default: 500)
- Check MemoryMax in service file (default: 4G)

### Embedding model download fails:

```bash
# Pre-download model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"
```

### Queue items stuck in 'processing':

```sql
-- Reset stuck items (if worker crashed)
UPDATE index_queue
SET status = 'pending'
WHERE status = 'processing'
  AND processed_at < NOW() - INTERVAL '1 hour';
```

## Performance Tuning

### For high-volume indexing:

```env
# .env settings
WORKER_BATCH_SIZE=20        # Process more items per batch
WORKER_POLL_INTERVAL=2      # Check queue more frequently
MAX_TOKENS=400              # Smaller chunks = faster processing
```

### For resource-constrained systems:

```env
WORKER_BATCH_SIZE=5         # Process fewer items
MAX_TOKENS=300              # Smaller chunks
```

### GPU acceleration (if available):

The embedding model will automatically use CUDA if available:

```bash
# Install PyTorch with CUDA
pip install torch --index-url https://download.pytorch.org/whl/cu118
```

## Next Steps

Once the worker is running successfully:

1. **Phase 3**: Implement filesystem watcher to auto-populate queue
2. **Integration**: Connect to corpus ingestion pipeline
3. **Monitoring**: Set up alerts for failed queue items
4. **Optimization**: Profile and optimize for your workload

## Support

Check README.md for architecture details and usage examples.
