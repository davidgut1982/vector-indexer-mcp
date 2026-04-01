# Migration Guide: System Services → User Services

## Overview

This guide explains how to migrate vector-indexer-mcp from system services to user-persistent services.

**Why migrate?**
- **Better security**: Services run as your user without elevated privileges
- **Easier management**: No sudo required for service operations
- **Better isolation**: User services are isolated from system services
- **Persistent after logout**: With lingering enabled, services survive logout

## What Changed

### Service Files
- **Removed**: `User=` and `Group=` directives (not needed for user services)
- **Changed**: `WantedBy=multi-user.target` → `WantedBy=default.target`
- **Same**: All other directives remain identical

### Installation Location
- **Old**: `/etc/systemd/system/` (system services)
- **New**: `~/.config/systemd/user/` (user services)

### Commands
- **Old**: `sudo systemctl <command> <service>`
- **New**: `systemctl --user <command> <service>`

## Migration Steps

### 1. Stop Existing System Services

```bash
sudo systemctl stop vector-indexer
sudo systemctl stop vector-indexer-worker
sudo systemctl stop vector-indexer-mcp-http  # If installed

sudo systemctl disable vector-indexer
sudo systemctl disable vector-indexer-worker
sudo systemctl disable vector-indexer-mcp-http  # If installed
```

### 2. Remove System Service Files

```bash
sudo rm /etc/systemd/system/vector-indexer.service
sudo rm /etc/systemd/system/vector-indexer-worker.service
sudo rm /etc/systemd/system/vector-indexer-mcp-http.service  # If installed

sudo systemctl daemon-reload
```

### 3. Install User Services

```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp

# Create user systemd directory
mkdir -p ~/.config/systemd/user

# Copy service files
cp vector-indexer.service ~/.config/systemd/user/
cp vector-indexer-worker.service ~/.config/systemd/user/
cp vector-indexer-mcp-http.service ~/.config/systemd/user/  # If needed

# Reload user systemd
systemctl --user daemon-reload
```

### 4. Enable and Start User Services

```bash
# Enable services
systemctl --user enable vector-indexer
systemctl --user enable vector-indexer-worker
systemctl --user enable vector-indexer-mcp-http  # If needed

# Start services
systemctl --user start vector-indexer
systemctl --user start vector-indexer-worker
systemctl --user start vector-indexer-mcp-http  # If needed
```

### 5. Enable Lingering (CRITICAL)

This ensures services persist after logout:

```bash
loginctl enable-linger $USER
```

### 6. Verify Migration

```bash
# Check service status
systemctl --user status vector-indexer
systemctl --user status vector-indexer-worker
systemctl --user status vector-indexer-mcp-http  # If installed

# Check logs
journalctl --user -u vector-indexer -n 50
journalctl --user -u vector-indexer-worker -n 50
journalctl --user -u vector-indexer-mcp-http -n 50  # If installed

# Verify lingering is enabled
loginctl show-user $USER | grep Linger
# Should show: Linger=yes
```

## New Commands Reference

### Service Management

```bash
# Start services
systemctl --user start vector-indexer
systemctl --user start vector-indexer-worker

# Stop services
systemctl --user stop vector-indexer
systemctl --user stop vector-indexer-worker

# Restart services
systemctl --user restart vector-indexer
systemctl --user restart vector-indexer-worker

# Enable on boot
systemctl --user enable vector-indexer
systemctl --user enable vector-indexer-worker

# Disable
systemctl --user disable vector-indexer
systemctl --user disable vector-indexer-worker

# Check status
systemctl --user status vector-indexer vector-indexer-worker
```

### Logs

```bash
# View logs
journalctl --user -u vector-indexer -f
journalctl --user -u vector-indexer-worker -f

# Last 100 lines
journalctl --user -u vector-indexer -n 100

# Since timestamp
journalctl --user -u vector-indexer --since "2025-01-01 10:00:00"
```

### Lingering

```bash
# Enable lingering for current user
loginctl enable-linger $USER

# Disable lingering
loginctl disable-linger $USER

# Check lingering status
loginctl show-user $USER | grep Linger
```

## Automated Migration Script

For convenience, use the provided migration script:

```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp
./scripts/migrate_to_user_services.sh
```

This script:
1. Stops and disables system services
2. Removes system service files
3. Installs user services
4. Enables lingering
5. Starts user services
6. Verifies migration success

## Troubleshooting

### Services Not Starting

```bash
# Check for errors
systemctl --user status vector-indexer --no-pager -l

# Check logs
journalctl --user -u vector-indexer --since today

# Verify service file syntax
systemd-analyze verify ~/.config/systemd/user/vector-indexer.service
```

### Services Stop After Logout

**Problem**: You forgot to enable lingering

**Solution**:
```bash
loginctl enable-linger $USER
```

### Permission Errors

**Problem**: Service trying to access system directories

**Solution**: User services should only access user-writable directories:
- `/srv/latvian_mcp` - Should be owned by your user
- `/srv/latvian_xtts` - Should be owned by your user
- Home directory - Always accessible

Verify ownership:
```bash
ls -ld /srv/latvian_mcp
# Should show: drwxr-xr-x ... david david ... /srv/latvian_mcp
```

### Environment Variables Not Loading

**Problem**: `.env` file not readable

**Solution**:
```bash
# Verify .env exists and is readable
ls -l /srv/latvian_mcp/servers/vector-indexer-mcp/.env

# Should show: -rw-r--r-- ... david david ... .env

# If not, fix permissions
chmod 644 /srv/latvian_mcp/servers/vector-indexer-mcp/.env
```

## Reverting to System Services

If you need to revert:

```bash
# Stop user services
systemctl --user stop vector-indexer vector-indexer-worker
systemctl --user disable vector-indexer vector-indexer-worker

# Remove user services
rm ~/.config/systemd/user/vector-indexer*.service
systemctl --user daemon-reload

# Reinstall as system services
cd /srv/latvian_mcp/servers/vector-indexer-mcp
sudo cp *.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable vector-indexer vector-indexer-worker
sudo systemctl start vector-indexer vector-indexer-worker
```

**Note**: You'll need to modify service files to add back `User=david` and `Group=david` directives.

## Benefits of User Services

1. **No sudo required** - Manage services without elevated privileges
2. **Better security** - Services run with user permissions only
3. **Easier debugging** - Logs accessible without sudo
4. **Cleaner separation** - User services isolated from system services
5. **Per-user configuration** - Each user can have their own services

## References

- [systemd User Services](https://wiki.archlinux.org/title/Systemd/User)
- [loginctl manpage](https://www.freedesktop.org/software/systemd/man/loginctl.html)
- [Lingering explained](https://www.freedesktop.org/software/systemd/man/loginctl.html#enable-linger%20USER%E2%80%A6)
