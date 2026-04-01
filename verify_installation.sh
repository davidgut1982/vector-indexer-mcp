#!/bin/bash
# Vector Indexer MCP - Installation Verification Script
# Tests that all Phase 3 components are properly installed

set -e

echo "========================================"
echo "Vector Indexer MCP - Installation Check"
echo "========================================"
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check Python version
echo "=== Python Version ==="
if python3 --version | grep -q "Python 3"; then
    check_pass "Python 3 installed: $(python3 --version)"
else
    check_fail "Python 3 not found"
    exit 1
fi
echo ""

# Check virtual environment
echo "=== Virtual Environment ==="
if [ -d "venv" ]; then
    check_pass "Virtual environment exists"
    if [ -f "venv/bin/python" ]; then
        check_pass "Python interpreter in venv"
    else
        check_fail "Python interpreter not found in venv"
    fi
else
    check_warn "Virtual environment not found (will create during installation)"
fi
echo ""

# Check configuration files
echo "=== Configuration Files ==="
if [ -f "config/watcher.yaml" ]; then
    check_pass "Watcher config exists: config/watcher.yaml"
else
    check_fail "Watcher config missing: config/watcher.yaml"
fi

if [ -f ".env" ]; then
    check_pass "Environment file exists: .env"
    # Check for required variables
    if grep -q "SUPABASE_URL" .env; then
        check_pass "SUPABASE_URL configured"
    else
        check_warn "SUPABASE_URL not set in .env"
    fi
    if grep -q "SUPABASE_KEY" .env; then
        check_pass "SUPABASE_KEY configured"
    else
        check_warn "SUPABASE_KEY not set in .env"
    fi
else
    check_warn "Environment file missing: .env (copy from .env.example)"
fi
echo ""

# Check daemon files
echo "=== Daemon Components ==="
components=(
    "daemon/config.py"
    "daemon/watcher.py"
    "daemon/chunker.py"
    "daemon/embedder.py"
    "daemon/worker.py"
)

for component in "${components[@]}"; do
    if [ -f "$component" ]; then
        check_pass "$component"
    else
        check_fail "$component missing"
    fi
done
echo ""

# Check systemd services
echo "=== Systemd Services ==="
if [ -f "vector-indexer.service" ]; then
    check_pass "Watcher service file: vector-indexer.service"
else
    check_fail "Watcher service file missing"
fi

if [ -f "vector-indexer-worker.service" ]; then
    check_pass "Worker service file: vector-indexer-worker.service"
else
    check_fail "Worker service file missing"
fi

# Check if services are installed
if systemctl list-unit-files | grep -q "vector-indexer.service"; then
    check_pass "Watcher service installed in systemd"
    if systemctl is-enabled vector-indexer.service >/dev/null 2>&1; then
        check_pass "Watcher service enabled"
    else
        check_warn "Watcher service not enabled"
    fi
    if systemctl is-active vector-indexer.service >/dev/null 2>&1; then
        check_pass "Watcher service running"
    else
        check_warn "Watcher service not running"
    fi
else
    check_warn "Watcher service not installed in systemd"
fi

if systemctl list-unit-files | grep -q "vector-indexer-worker.service"; then
    check_pass "Worker service installed in systemd"
    if systemctl is-enabled vector-indexer-worker.service >/dev/null 2>&1; then
        check_pass "Worker service enabled"
    else
        check_warn "Worker service not enabled"
    fi
    if systemctl is-active vector-indexer-worker.service >/dev/null 2>&1; then
        check_pass "Worker service running"
    else
        check_warn "Worker service not running"
    fi
else
    check_warn "Worker service not installed in systemd"
fi
echo ""

# Check test files
echo "=== Test Files ==="
if [ -f "test_watcher_core.py" ]; then
    check_pass "Watcher tests: test_watcher_core.py"
else
    check_fail "Watcher tests missing"
fi

if [ -f "test_pipeline.py" ]; then
    check_pass "Pipeline tests: test_pipeline.py"
else
    check_fail "Pipeline tests missing"
fi
echo ""

# Check documentation
echo "=== Documentation ==="
docs=(
    "README.md"
    "PHASE3_SUMMARY.md"
    "PHASE3_WATCHER.md"
    "IMPLEMENTATION_SUMMARY.md"
    "INSTALL.md"
)

for doc in "${docs[@]}"; do
    if [ -f "$doc" ]; then
        check_pass "$doc"
    else
        check_warn "$doc missing"
    fi
done
echo ""

# Check watch directories
echo "=== Watch Directories ==="
watch_dirs=(
    "/srv/latvian_mcp"
    "/srv/latvian_xtts"
    "/srv/latvian_learning"
    "/srv/claude-mpm"
)

for dir in "${watch_dirs[@]}"; do
    if [ -d "$dir" ]; then
        check_pass "Directory exists: $dir"
    else
        check_warn "Directory not found: $dir"
    fi
done
echo ""

# Summary
echo "========================================"
echo "Installation Check Complete"
echo "========================================"
echo ""
echo "Next steps:"
echo "1. If venv missing: python3 -m venv venv"
echo "2. Activate venv: source venv/bin/activate"
echo "3. Install deps: pip install -r requirements.txt"
echo "4. Copy .env: cp .env.example .env (and configure)"
echo "5. Run tests: python test_watcher_core.py"
echo "6. Install services:"
echo "   sudo cp vector-indexer*.service /etc/systemd/system/"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl enable vector-indexer vector-indexer-worker"
echo "   sudo systemctl start vector-indexer vector-indexer-worker"
echo ""
