# Vector Indexer MCP - Phase 3: File Watcher Daemon

**Date**: 2025-12-18
**Status**: ✅ Complete
**Version**: 0.3.0

## Overview

Phase 3 implements the File Watcher Daemon that monitors configured directories for file changes and automatically populates the index queue. This enables real-time indexing of code repositories and documentation.

## Architecture

```
┌─────────────────────┐
│  File System (OS)   │
│    (inotify)        │
└──────────┬──────────┘
           │ File events
           ▼
┌─────────────────────┐
│  Watchdog Library   │
│  (FileSystemEvent)  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ IndexEventHandler   │  ← Filter & validate events
│  (FileSystemEvent   │
│     Handler)        │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  DebounceQueue      │  ← Deduplicate rapid changes
│  (100ms window)     │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Queue Processor     │  ← Batch insert to DB
│   (Background       │
│     Thread)         │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Supabase           │
│  (index_queue)      │
└─────────────────────┘
           │
           ▼
┌─────────────────────┐
│  IndexingWorker     │  ← Process queue (Phase 2)
└─────────────────────┘
```

## Components

### 1. Configuration System (`daemon/config.py`)

**Purpose**: Load and validate watcher configuration from YAML.

**Key Features**:
- Environment variable expansion (`$VAR` and `${VAR}` syntax)
- Recursive expansion for nested structures
- Path filtering logic (include/exclude patterns)
- File size validation

**WatcherConfig Class**:
```python
@dataclass
class WatcherConfig:
    watch_paths: List[str]           # Directories to monitor
    exclude_patterns: List[str]       # Patterns to skip
    include_extensions: List[str]     # File types to index
    max_file_size_mb: int            # Size limit
    debounce_ms: int                 # Debounce delay
    batch_size: int                  # Queue batch size
```

**Methods**:
- `should_include_file(path)` - Check file extension
- `should_exclude_path(path)` - Check exclude patterns
- `max_file_size_bytes` - Property for size in bytes

---

### 2. Configuration File (`config/watcher.yaml`)

**Default Configuration**:

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
    - node_modules
    - venv
    - .venv
    - "*.pyc"
    - "*.log"
    - "*.tmp"

  include_extensions:
    - .py
    - .md
    - .txt
    - .json
    - .yaml
    - .yml
    - .sql
    - .sh

  max_file_size_mb: 10
  debounce_ms: 100
  batch_size: 50
```

**Customization**:
- Add/remove watch paths
- Adjust exclude patterns for your environment
- Tune debounce delay for performance
- Set batch size based on event volume

---

### 3. File Watcher Daemon (`daemon/watcher.py`)

**Purpose**: Monitor file system and populate index queue.

#### 3.1 FileEvent Dataclass

Represents a file system event:

```python
@dataclass
class FileEvent:
    file_path: str
    event_type: str      # 'create', 'modify', 'delete', 'move'
    dest_path: str       # For move events
    timestamp: float
```

#### 3.2 DebounceQueue Class

**Purpose**: Deduplicate rapid file changes.

**How it works**:
1. Events are added to queue with timestamp
2. Duplicate events for same file replace previous ones
3. Events become "ready" after debounce period (default 100ms)
4. Ready events are retrieved in batch

**Methods**:
- `add(event)` - Add event to queue
- `get_ready_events()` - Get events past debounce period
- `size()` - Current queue size

**Benefits**:
- Prevents duplicate processing during rapid file changes
- Reduces database load during batch edits
- Captures final state after editor saves

#### 3.3 IndexEventHandler Class

**Purpose**: Handle watchdog file system events.

**Event Types Handled**:
- `on_created` - New file created
- `on_modified` - File content changed
- `on_deleted` - File removed
- `on_moved` - File renamed/moved

**Filtering Logic**:
1. Skip directories (only files)
2. Check exclude patterns
3. Validate file size (skip if too large)
4. Check include extensions
5. Add to debounce queue if passed

**Statistics Tracked**:
- `events_received` - Total events from watchdog
- `events_queued` - Events added to queue
- `events_filtered` - Events skipped

#### 3.4 FileWatcherDaemon Class

**Purpose**: Main daemon orchestrator.

**Lifecycle**:

1. **Initialization**:
   - Load configuration
   - Create debounce queue
   - Setup watchdog observer
   - Initialize Supabase client

2. **Start**:
   - Setup file system watchers for each path
   - Start watchdog observer
   - Start background processor thread
   - Log stats every 60 seconds

3. **Processing** (background thread):
   - Continuously check debounce queue
   - Retrieve ready events
   - Insert events into Supabase in batches
   - Sleep briefly to avoid busy-waiting

4. **Shutdown**:
   - Stop watchdog observer
   - Wait for processor thread
   - Process remaining events
   - Clean exit

**Key Methods**:
- `start()` - Start daemon
- `stop()` - Graceful shutdown
- `_process_queue()` - Background processor
- `_insert_batch()` - Batch insert to DB

**Signal Handling**:
- SIGTERM (systemd stop) → graceful shutdown
- SIGINT (Ctrl+C) → graceful shutdown

---

## Project Structure

```
/srv/latvian_mcp/servers/vector-indexer-mcp/
├── daemon/
│   ├── __init__.py           # Package exports
│   ├── chunker.py            # TextChunker (Phase 2)
│   ├── embedder.py           # EmbeddingGenerator (Phase 2)
│   ├── worker.py             # IndexingWorker (Phase 2)
│   ├── config.py             # Configuration loader (NEW)
│   └── watcher.py            # File watcher daemon (NEW)
├── config/
│   └── watcher.yaml          # Watcher configuration (NEW)
├── .env                      # Environment variables
├── requirements.txt          # Python dependencies (updated)
├── test_pipeline.py          # Phase 2 tests
├── test_watcher.py           # Watcher tests (NEW)
├── vector-indexer.service    # Watcher systemd service (NEW)
└── vector-indexer-worker.service  # Worker systemd service (Phase 2)
```

---

## Installation

### 1. Install New Dependencies

```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp

# Activate virtual environment
source venv/bin/activate

# Install watchdog and pyyaml
pip install watchdog>=3.0.0 pyyaml>=6.0

# Or install from requirements.txt
pip install -r requirements.txt
```

### 2. Verify Configuration

```bash
# Check configuration file
cat config/watcher.yaml

# Edit if needed
nano config/watcher.yaml
```

### 3. Test Watcher Components

```bash
# Run watcher tests
python test_watcher.py
```

Expected output:
```
Vector Indexer Watcher - Test Suite
==================================================

=== Testing Configuration Loading ===
Watch paths: 4
  - /srv/latvian_mcp
  - /srv/latvian_xtts
  - /srv/latvian_learning
  - /srv/claude-mpm

✓ Configuration loading test passed

=== Testing Debounce Queue ===
✓ Debounce queue test passed

=== Testing Rapid Changes ===
✓ Rapid changes test passed

=== Testing Move Events ===
✓ Move event test passed

=== Testing Batch Processing ===
✓ Batch processing test passed

==================================================
✓ All tests passed!
==================================================
```

### 4. Run Watcher Manually (Test Mode)

```bash
# Run in foreground for testing
python -m daemon.watcher
```

You should see:
```
2025-12-18 12:00:00 - __main__ - INFO - Starting Vector Indexer File Watcher Daemon
2025-12-18 12:00:00 - __main__ - INFO - Configuration: 4 watch paths
2025-12-18 12:00:00 - __main__ - INFO - Debounce: 100ms
2025-12-18 12:00:00 - __main__ - INFO - Batch size: 50
2025-12-18 12:00:00 - __main__ - INFO - Connected to Supabase
2025-12-18 12:00:00 - __main__ - INFO - Watching: /srv/latvian_mcp
2025-12-18 12:00:00 - __main__ - INFO - Watching: /srv/latvian_xtts
2025-12-18 12:00:00 - __main__ - INFO - Watching: /srv/latvian_learning
2025-12-18 12:00:00 - __main__ - INFO - Watching: /srv/claude-mpm
2025-12-18 12:00:00 - __main__ - INFO - File system observer started
2025-12-18 12:00:00 - __main__ - INFO - Queue processor thread started
```

Test by creating a file in a watched directory:
```bash
# In another terminal
echo "test" > /srv/latvian_mcp/test_file.py
```

You should see in watcher logs:
```
2025-12-18 12:00:05 - __main__ - DEBUG - File created: /srv/latvian_mcp/test_file.py
2025-12-18 12:00:05 - __main__ - INFO - Inserted 1 events into queue
```

Stop with Ctrl+C for graceful shutdown.

### 5. Install Systemd Service

```bash
# Copy service file
sudo cp vector-indexer.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable on boot
sudo systemctl enable vector-indexer

# Start service
sudo systemctl start vector-indexer

# Check status
sudo systemctl status vector-indexer
```

Expected status:
```
● vector-indexer.service - Vector Search File Indexer Daemon
     Loaded: loaded (/etc/systemd/system/vector-indexer.service; enabled)
     Active: active (running) since Wed 2025-12-18 12:00:00 UTC
```

### 6. Monitor Logs

```bash
# Follow logs
sudo journalctl -u vector-indexer -f

# Last 100 lines
sudo journalctl -u vector-indexer -n 100

# With timestamps
sudo journalctl -u vector-indexer -o short-precise -f
```

---

## Usage

### Running Both Services

The complete system requires both services running:

1. **vector-indexer** (watcher) - Monitors files, populates queue
2. **vector-indexer-worker** (processor) - Processes queue, indexes files

```bash
# Start both services
sudo systemctl start vector-indexer
sudo systemctl start vector-indexer-worker

# Check both are running
sudo systemctl status vector-indexer vector-indexer-worker

# Enable both on boot
sudo systemctl enable vector-indexer vector-indexer-worker
```

### Monitoring Queue

Check the queue status in Supabase:

```sql
-- Queue summary
SELECT status, COUNT(*) as count
FROM index_queue
GROUP BY status;

-- Recent events
SELECT file_path, event, status, created_at
FROM index_queue
ORDER BY created_at DESC
LIMIT 10;

-- Failed events
SELECT file_path, error_message, processed_at
FROM index_queue
WHERE status = 'failed'
ORDER BY processed_at DESC;
```

### Testing Real-Time Indexing

1. **Create a test file**:
   ```bash
   echo "# Test Document" > /srv/latvian_mcp/test_doc.md
   echo "This is a test." >> /srv/latvian_mcp/test_doc.md
   ```

2. **Check watcher logs**:
   ```bash
   sudo journalctl -u vector-indexer -n 20
   ```
   Should show: `File created: /srv/latvian_mcp/test_doc.md`

3. **Check queue**:
   ```sql
   SELECT * FROM index_queue WHERE file_path = '/srv/latvian_mcp/test_doc.md';
   ```

4. **Wait for worker** to process (check worker logs):
   ```bash
   sudo journalctl -u vector-indexer-worker -n 20
   ```

5. **Verify indexing**:
   ```sql
   SELECT * FROM file_metadata WHERE file_path = '/srv/latvian_mcp/test_doc.md';
   ```

---

## Configuration Tuning

### Debounce Delay

**Default**: 100ms

**Adjust for**:
- **High-frequency changes** (e.g., IDE auto-save): Increase to 500ms
- **Low latency requirements**: Decrease to 50ms
- **Batch editing**: Increase to 1000ms

```yaml
debounce_ms: 500  # Wait 500ms before processing
```

### Batch Size

**Default**: 50 events

**Adjust for**:
- **High event volume**: Increase to 100
- **Low latency**: Decrease to 10
- **Database constraints**: Match worker batch size

```yaml
batch_size: 100
```

### Watch Paths

Add or remove paths as needed:

```yaml
watch_paths:
  - /srv/latvian_mcp
  - /srv/latvian_xtts
  - /home/david/projects  # Add custom path
```

### Exclude Patterns

Add patterns to skip:

```yaml
exclude_patterns:
  - __pycache__
  - .git
  - "*.test.py"      # Skip test files
  - "temp_*"         # Skip temp files
  - node_modules
```

---

## Performance

### Resource Usage

| Metric | Expected Value |
|--------|----------------|
| CPU (idle) | ~1-2% |
| CPU (active) | ~5-10% |
| Memory | ~100-200 MB |
| Disk I/O | Minimal (reads only) |
| Network | Minimal (DB inserts) |

### Throughput

| Metric | Performance |
|--------|-------------|
| Events/second | ~1000 |
| Batch inserts/second | ~20 |
| Latency (debounced) | 100-200ms |

### Scaling

**Per-directory limits** (inotify):
- Default: 8192 watches per user
- Check: `cat /proc/sys/fs/inotify/max_user_watches`
- Increase: `sudo sysctl fs.inotify.max_user_watches=524288`

---

## Troubleshooting

### Watcher Not Starting

**Check service status**:
```bash
sudo systemctl status vector-indexer
```

**Check logs**:
```bash
sudo journalctl -u vector-indexer -n 50
```

**Common issues**:
- Missing .env file → Copy from .env.example
- Invalid Supabase credentials → Check SUPABASE_URL and SUPABASE_KEY
- Watch path doesn't exist → Check paths in watcher.yaml

### No Events Being Queued

**Check if paths exist**:
```bash
ls -la /srv/latvian_mcp
```

**Check exclude patterns**:
- File might match exclude pattern
- Run `python test_watcher.py` to verify filtering logic

**Check file extensions**:
- Only files with included extensions are indexed
- Add extension to `include_extensions` if needed

### High CPU Usage

**Possible causes**:
1. Too many watch paths
2. Debounce too low
3. High-frequency file changes

**Solutions**:
- Increase debounce delay
- Add more exclude patterns
- Reduce watch paths

### Memory Growth

**Check if**:
- Debounce queue growing unbounded
- Events not being processed

**Solutions**:
- Check worker is running: `systemctl status vector-indexer-worker`
- Increase batch size to drain queue faster
- Add more exclude patterns

---

## Security

### Service Hardening

The systemd service includes security hardening:

- `NoNewPrivileges=true` - Prevent privilege escalation
- `PrivateTmp=true` - Private /tmp directory
- `ProtectSystem=strict` - Read-only filesystem
- `ProtectHome=read-only` - Read-only home directory
- `ReadWritePaths=/srv/*` - Only write to /srv
- `MemoryMax=512M` - Memory limit
- `CPUQuota=25%` - CPU limit

### File Access

The watcher runs as user `david` with:
- Read access to watch paths
- Write access to none (monitoring only)
- Database write via Supabase client

### Secrets Management

- Supabase credentials in `.env` file (git-ignored)
- Service reads `.env` via `EnvironmentFile=`
- No secrets in systemd service file

---

## Integration with Phase 2

The watcher and worker operate as a pipeline:

```
[File Change] → [Watcher] → [Queue] → [Worker] → [Indexed]
                  Phase 3     DB       Phase 2
```

**Workflow**:

1. **File created** in watched directory
2. **Watcher** detects via inotify
3. **Debounce queue** deduplicates rapid changes
4. **Batch inserted** into `index_queue` table
5. **Worker** polls queue (every 5 seconds)
6. **Worker processes** file (chunk → embed → store)
7. **Queue status** updated to `completed`

**Both services must be running** for real-time indexing.

---

## Next Steps

### Phase 4 Ideas (Future)

1. **Search API**: Query indexed embeddings
2. **MCP Server**: Expose search tools to Claude
3. **Similarity Search**: Find similar code/docs
4. **Duplicate Detection**: Find redundant files
5. **Dependency Graph**: Link files by imports
6. **Change Impact**: Predict affected files

---

## Maintenance

### Restart Services

```bash
# Restart both services
sudo systemctl restart vector-indexer vector-indexer-worker
```

### Update Configuration

```bash
# Edit config
nano /srv/latvian_mcp/servers/vector-indexer-mcp/config/watcher.yaml

# Restart to apply
sudo systemctl restart vector-indexer
```

### Update Code

```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp

# Pull latest code
git pull

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Restart services
sudo systemctl restart vector-indexer vector-indexer-worker
```

### Clear Queue

```sql
-- Clear pending events
DELETE FROM index_queue WHERE status = 'pending';

-- Clear failed events
DELETE FROM index_queue WHERE status = 'failed';

-- Clear all events
TRUNCATE index_queue;
```

### Reindex Everything

```sql
-- Clear existing index
TRUNCATE file_metadata CASCADE;

-- Populate queue with all files (manual)
INSERT INTO index_queue (file_path, event, priority)
VALUES
  ('/path/to/file1.py', 'create', 1),
  ('/path/to/file2.md', 'create', 1);
```

Or trigger reindex by touching files:
```bash
find /srv/latvian_mcp -name "*.py" -exec touch {} \;
```

---

## License

MIT

---

**Implementation Complete**: 2025-12-18
**Author**: Claude Sonnet 4.5 via Latvian Lab
**Phase**: 3/4 (Watcher Daemon)
