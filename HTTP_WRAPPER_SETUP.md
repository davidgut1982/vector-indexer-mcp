# Vector Indexer MCP HTTP/SSE Wrapper

## Overview

HTTP/SSE wrapper for the vector-indexer-mcp server to integrate with ContextForge gateway.

**Port**: 5558
**Endpoints**: `/sse`, `/messages/`, `/health`, `/info`
**Gateway URL**: `http://172.17.0.1:5558/sse` (already configured in gateway.env)

## Files Created

### 1. `/srv/latvian_mcp/servers/vector-indexer-mcp/sse_server.py`
HTTP/SSE wrapper that:
- Exposes the stdio MCP server over HTTP/SSE
- Runs on port 5558
- Provides health check and info endpoints
- Handles MCP protocol translation
- CORS-enabled for ContextForge gateway access

### 2. `/srv/latvian_mcp/servers/vector-indexer-mcp/vector-indexer-mcp-http.service`
Systemd service file that:
- Runs the HTTP wrapper on port 5558
- Auto-restarts on failure
- Uses the venv at `/srv/latvian_mcp/servers/vector-indexer-mcp/venv/`
- Loads environment from `.env` file
- Runs as user `david`

### 3. `/srv/latvian_mcp/servers/vector-indexer-mcp/requirements.txt` (updated)
Added HTTP/SSE dependencies:
- `uvicorn>=0.27.0`
- `starlette>=0.36.0`
- `sse-starlette>=1.8.0`

### 4. `/srv/latvian_mcp/servers/vector-indexer-mcp/install_http_wrapper.sh`
Automated installation script that:
- Installs Python dependencies
- Makes sse_server.py executable
- Installs systemd service
- Enables and starts the service
- Verifies installation

## Quick Start

### Option 1: Automated Installation (Recommended)

```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp
./install_http_wrapper.sh
```

### Option 2: Manual Installation

```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp

# Install dependencies
./venv/bin/pip install uvicorn starlette sse-starlette

# Install systemd service
sudo cp vector-indexer-mcp-http.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vector-indexer-mcp-http.service
sudo systemctl start vector-indexer-mcp-http.service

# Verify
sudo systemctl status vector-indexer-mcp-http.service
curl http://localhost:5558/health
```

## Service Management

```bash
# Check status
sudo systemctl status vector-indexer-mcp-http

# Restart service
sudo systemctl restart vector-indexer-mcp-http

# View logs
sudo journalctl -u vector-indexer-mcp-http -f

# Stop service
sudo systemctl stop vector-indexer-mcp-http

# Disable service
sudo systemctl disable vector-indexer-mcp-http
```

## Testing

### Health Check
```bash
curl http://localhost:5558/health
# Expected: {"status":"healthy","server":"vector-indexer-mcp","transport":"sse"}
```

### Server Info
```bash
curl http://localhost:5558/info | jq
# Expected: Server info with available tools list
```

### SSE Connection (from ContextForge)
The gateway connects via: `http://172.17.0.1:5558/sse`

## Architecture

```
┌─────────────────────────┐
│  ContextForge Gateway   │
│    (port 4444)          │
└───────────┬─────────────┘
            │
            │ HTTP/SSE
            │ 172.17.0.1:5558/sse
            │
            ▼
┌─────────────────────────┐
│  vector-indexer-mcp     │
│  HTTP/SSE Wrapper       │
│  (sse_server.py)        │
│  Port 5558              │
└───────────┬─────────────┘
            │
            │ stdio pipes
            │
            ▼
┌─────────────────────────┐
│  vector-indexer-mcp     │
│  MCP Server             │
│  (server.py)            │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│  Supabase Postgres      │
│  (vector_index table)   │
└─────────────────────────┘
```

## Available Tools (via HTTP/SSE)

- `search_semantic` - Vector similarity search
- `search_lexical` - Full-text search (FTS)
- `search_hybrid` - Combined semantic + lexical search
- `index_status` - Get index health statistics
- `reindex_path` - Force reindex a file/directory
- `get_file_chunks` - View chunks for a specific file
- `search_similar_files` - Find files similar to a given file

## Environment Variables

The service reads from `/srv/latvian_mcp/servers/vector-indexer-mcp/.env`:

```bash
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
MCP_SSE_PORT=5558  # Optional, defaults to 5558
MCP_SSE_HOST=0.0.0.0  # Optional, defaults to 0.0.0.0
```

## Gateway Configuration

Already configured in `/srv/latvian_mcp/gateway.env`:

```bash
VECTOR_INDEXER_MCP_URL=http://172.17.0.1:5558/sse
```

## Troubleshooting

### Service won't start
```bash
# Check service status
sudo systemctl status vector-indexer-mcp-http

# Check logs
sudo journalctl -u vector-indexer-mcp-http -n 50

# Verify .env file exists
cat /srv/latvian_mcp/servers/vector-indexer-mcp/.env

# Test manually
cd /srv/latvian_mcp/servers/vector-indexer-mcp
./venv/bin/python3 sse_server.py
```

### Port already in use
```bash
# Check what's using port 5558
sudo lsof -i :5558

# Kill process or change port in service file
```

### Gateway can't connect
```bash
# Verify service is running
curl http://localhost:5558/health

# Check from gateway container
docker exec -it <gateway-container> curl http://172.17.0.1:5558/health

# Check firewall rules
sudo iptables -L -n | grep 5558
```

## Next Steps

1. Run `./install_http_wrapper.sh` to install and start the service
2. Verify health check: `curl http://localhost:5558/health`
3. Restart ContextForge gateway to pick up the new backend
4. Test vector search from gateway: `curl http://localhost:4444/...`

## Related Documentation

- `/srv/latvian_mcp/servers/vector-indexer-mcp/README.md` - Main server documentation
- `/srv/latvian_mcp/servers/vector-indexer-mcp/PHASE4_MCP_SERVER.md` - MCP server implementation
- `/srv/latvian_mcp/servers/vector-indexer-mcp/PHASE5_SUMMARY.md` - Latest updates
