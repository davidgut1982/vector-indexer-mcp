#!/bin/bash
# Automated migration script: System services → User services
# For vector-indexer-mcp

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "Vector Indexer MCP - User Service Migration"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    print_error "Do not run this script as root"
    echo "This script migrates to user services, which should run as your regular user."
    exit 1
fi

# Step 1: Check for existing system services
echo "Step 1/7: Checking for existing system services..."

SYSTEM_SERVICES_EXIST=false
if systemctl list-unit-files | grep -q "vector-indexer.service"; then
    SYSTEM_SERVICES_EXIST=true
    print_warning "Found existing system services"
else
    print_status "No existing system services found (fresh install)"
fi

# Step 2: Stop and disable system services if they exist
if [ "$SYSTEM_SERVICES_EXIST" = true ]; then
    echo ""
    echo "Step 2/7: Stopping existing system services..."

    for service in vector-indexer vector-indexer-worker vector-indexer-mcp-http; do
        if systemctl is-active --quiet "$service" 2>/dev/null; then
            echo "  Stopping $service..."
            sudo systemctl stop "$service" || true
        fi

        if systemctl is-enabled --quiet "$service" 2>/dev/null; then
            echo "  Disabling $service..."
            sudo systemctl disable "$service" || true
        fi
    done

    print_status "System services stopped and disabled"
else
    echo ""
    echo "Step 2/7: No system services to stop"
    print_status "Skipped"
fi

# Step 3: Remove system service files
if [ "$SYSTEM_SERVICES_EXIST" = true ]; then
    echo ""
    echo "Step 3/7: Removing system service files..."

    for service in vector-indexer.service vector-indexer-worker.service vector-indexer-mcp-http.service; do
        if [ -f "/etc/systemd/system/$service" ]; then
            echo "  Removing /etc/systemd/system/$service..."
            sudo rm "/etc/systemd/system/$service"
        fi
    done

    sudo systemctl daemon-reload
    print_status "System service files removed"
else
    echo ""
    echo "Step 3/7: No system service files to remove"
    print_status "Skipped"
fi

# Step 4: Create user systemd directory
echo ""
echo "Step 4/7: Creating user systemd directory..."
mkdir -p ~/.config/systemd/user
print_status "User systemd directory ready: ~/.config/systemd/user"

# Step 5: Install user service files
echo ""
echo "Step 5/7: Installing user service files..."

cd "$PROJECT_DIR"

for service in vector-indexer.service vector-indexer-worker.service vector-indexer-mcp-http.service; do
    if [ -f "$service" ]; then
        echo "  Copying $service..."
        cp "$service" ~/.config/systemd/user/
    else
        print_warning "Service file not found: $service"
    fi
done

systemctl --user daemon-reload
print_status "User service files installed"

# Step 6: Enable and start user services
echo ""
echo "Step 6/7: Enabling and starting user services..."

# Check which services to enable based on what files exist
SERVICES_TO_ENABLE=()
[ -f ~/.config/systemd/user/vector-indexer.service ] && SERVICES_TO_ENABLE+=("vector-indexer")
[ -f ~/.config/systemd/user/vector-indexer-worker.service ] && SERVICES_TO_ENABLE+=("vector-indexer-worker")
[ -f ~/.config/systemd/user/vector-indexer-mcp-http.service ] && SERVICES_TO_ENABLE+=("vector-indexer-mcp-http")

for service in "${SERVICES_TO_ENABLE[@]}"; do
    echo "  Enabling $service..."
    systemctl --user enable "$service"

    echo "  Starting $service..."
    systemctl --user start "$service"
done

print_status "User services enabled and started"

# Step 7: Enable lingering
echo ""
echo "Step 7/7: Enabling lingering for user persistence..."
loginctl enable-linger "$USER"

# Verify lingering
if loginctl show-user "$USER" | grep -q "Linger=yes"; then
    print_status "Lingering enabled - services will persist after logout"
else
    print_error "Failed to enable lingering"
fi

# Final verification
echo ""
echo "========================================"
echo "Migration Complete - Verification"
echo "========================================"
echo ""

echo "Service Status:"
for service in "${SERVICES_TO_ENABLE[@]}"; do
    echo ""
    echo "--- $service ---"
    if systemctl --user is-active --quiet "$service"; then
        print_status "$service is active"
    else
        print_error "$service is not active"
        echo "Check logs: journalctl --user -u $service -n 50"
    fi
done

echo ""
echo "Lingering Status:"
if loginctl show-user "$USER" | grep -q "Linger=yes"; then
    print_status "Lingering: enabled"
else
    print_warning "Lingering: not enabled"
fi

echo ""
echo "========================================"
echo "Next Steps"
echo "========================================"
echo ""
echo "1. Check service status:"
echo "   systemctl --user status ${SERVICES_TO_ENABLE[*]}"
echo ""
echo "2. View logs:"
echo "   journalctl --user -u vector-indexer -f"
echo "   journalctl --user -u vector-indexer-worker -f"
echo ""
echo "3. Restart services if needed:"
echo "   systemctl --user restart ${SERVICES_TO_ENABLE[*]}"
echo ""
echo "4. To revert migration, see: MIGRATION_USER_SERVICES.md"
echo ""
print_status "Migration script complete!"
