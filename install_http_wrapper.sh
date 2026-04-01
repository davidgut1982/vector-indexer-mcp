#!/bin/bash
# Installation script for vector-indexer-mcp HTTP/SSE wrapper (User Service Mode)

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "=== Installing vector-indexer-mcp HTTP/SSE wrapper (User Service) ==="

# 1. Install dependencies
echo "Step 1/6: Installing Python dependencies..."
./venv/bin/pip install -q uvicorn starlette sse-starlette

# 2. Make sse_server.py executable
echo "Step 2/6: Making sse_server.py executable..."
chmod +x sse_server.py

# 3. Create user systemd directory
echo "Step 3/6: Creating user systemd directory..."
mkdir -p ~/.config/systemd/user

# 4. Copy systemd service file
echo "Step 4/6: Installing systemd user service..."
cp vector-indexer-mcp-http.service ~/.config/systemd/user/

# 5. Reload systemd
echo "Step 5/6: Reloading systemd user daemon..."
systemctl --user daemon-reload

# 6. Enable and start service
echo "Step 6/6: Enabling and starting service..."
systemctl --user enable vector-indexer-mcp-http.service
systemctl --user start vector-indexer-mcp-http.service

# Enable lingering for user persistence after logout
echo ""
echo "Enabling lingering for user persistence..."
loginctl enable-linger $USER

echo ""
echo "=== Installation complete! ==="
echo ""
echo "Service status:"
systemctl --user status vector-indexer-mcp-http.service --no-pager
echo ""
echo "Health check:"
sleep 2
curl -s http://localhost:5558/health | python3 -m json.tool
echo ""
echo "Commands:"
echo "  systemctl --user status vector-indexer-mcp-http   # Check status"
echo "  systemctl --user restart vector-indexer-mcp-http  # Restart service"
echo "  journalctl --user -u vector-indexer-mcp-http -f   # View logs"
echo "  curl http://localhost:5558/info | jq              # Server info"
echo ""
echo "Note: Service runs in user mode and will persist after logout (lingering enabled)"
echo ""
