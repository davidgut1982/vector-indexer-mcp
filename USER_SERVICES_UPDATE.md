# User Services Update Summary

**Date**: 2025-12-18
**Status**: Complete ✓
**Migration Path**: System services → User-persistent services

## Overview

All vector-indexer-mcp systemd services have been updated to run in user mode instead of system mode. This provides better security, easier management, and cleaner separation from system services.

## Files Updated

### Service Files (3 files)

1. **vector-indexer-mcp-http.service**
   - Location: `/srv/latvian_mcp/servers/vector-indexer-mcp/`
   - Changes:
     - Removed `User=david` and `Group=david` directives
     - Changed `WantedBy=multi-user.target` → `WantedBy=default.target`

2. **vector-indexer-worker.service**
   - Location: `/srv/latvian_mcp/servers/vector-indexer-mcp/`
   - Changes:
     - Removed `User=david` and `Group=david` directives
     - Changed `WantedBy=multi-user.target` → `WantedBy=default.target`

3. **vector-indexer.service**
   - Location: `/srv/latvian_mcp/servers/vector-indexer-mcp/`
   - Changes:
     - Removed `User=david` and `Group=david` directives
     - Changed `WantedBy=multi-user.target` → `WantedBy=default.target`

### Installation Script

4. **install_http_wrapper.sh**
   - Location: `/srv/latvian_mcp/servers/vector-indexer-mcp/`
   - Changes:
     - Creates `~/.config/systemd/user/` directory
     - Copies service files to user location (not `/etc/systemd/system/`)
     - Uses `systemctl --user` commands (not `sudo systemctl`)
     - Enables lingering for persistence: `loginctl enable-linger $USER`
     - Updated all command examples in output

### Documentation

5. **README.md**
   - Updated "Running the System" section
   - Changed all systemd commands to use `--user` flag
   - Added note about user mode and lingering
   - Updated log viewing commands

6. **MIGRATION_USER_SERVICES.md** (NEW)
   - Complete migration guide from system to user services
   - Step-by-step instructions
   - Command reference
   - Troubleshooting section
   - Rollback instructions

7. **scripts/migrate_to_user_services.sh** (NEW)
   - Automated migration script
   - Stops/disables system services
   - Removes system service files
   - Installs user services
   - Enables lingering
   - Verifies migration success

## Key Differences: System vs User Services

| Aspect | System Services | User Services |
|--------|----------------|---------------|
| **Install location** | `/etc/systemd/system/` | `~/.config/systemd/user/` |
| **Commands** | `sudo systemctl` | `systemctl --user` |
| **User directive** | Required (`User=david`) | Not used |
| **WantedBy** | `multi-user.target` | `default.target` |
| **Permissions** | Requires sudo | No sudo needed |
| **Persistence** | Auto-starts on boot | Requires lingering |
| **Logs** | `sudo journalctl` | `journalctl --user` |

## Installation Instructions

### New Installations

```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp

# Install user services
mkdir -p ~/.config/systemd/user
cp *.service ~/.config/systemd/user/
systemctl --user daemon-reload

# Enable and start
systemctl --user enable vector-indexer vector-indexer-worker
systemctl --user start vector-indexer vector-indexer-worker

# Enable lingering for persistence
loginctl enable-linger $USER
```

### Migrating Existing Installations

**Option 1: Automated (Recommended)**
```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp
./scripts/migrate_to_user_services.sh
```

**Option 2: Manual**
```bash
# See MIGRATION_USER_SERVICES.md for detailed steps
```

## Command Reference (New)

### Service Management
```bash
systemctl --user start vector-indexer
systemctl --user stop vector-indexer
systemctl --user restart vector-indexer
systemctl --user status vector-indexer
systemctl --user enable vector-indexer
systemctl --user disable vector-indexer
```

### Logs
```bash
journalctl --user -u vector-indexer -f
journalctl --user -u vector-indexer-worker -f
journalctl --user -u vector-indexer -n 100
```

### Lingering
```bash
loginctl enable-linger $USER
loginctl show-user $USER | grep Linger
```

## Benefits

1. **No sudo required** - Users can manage their own services
2. **Better security** - Services run with user permissions only
3. **Cleaner separation** - User services isolated from system
4. **Easier debugging** - Logs accessible without sudo
5. **Per-user instances** - Multiple users can run their own instances

## Important Notes

### Lingering is Critical

User services stop when the user logs out UNLESS lingering is enabled:

```bash
loginctl enable-linger $USER
```

This is **required** for services to persist after logout.

### Directory Permissions

User services can only access directories the user owns:
- `/srv/latvian_mcp` - Must be writable by user
- `/srv/latvian_xtts` - Must be writable by user
- Home directory - Always accessible

Verify:
```bash
ls -ld /srv/latvian_mcp
# Should show: drwxr-xr-x ... david david ...
```

### HTTP Wrapper Installation

The `install_http_wrapper.sh` script has been updated for user services:
```bash
cd /srv/latvian_mcp/servers/vector-indexer-mcp
./install_http_wrapper.sh
```

This automatically:
1. Installs dependencies
2. Creates user systemd directory
3. Copies service file to `~/.config/systemd/user/`
4. Enables and starts user service
5. Enables lingering

## Testing Verification

After migration, verify:

```bash
# Services are running
systemctl --user status vector-indexer vector-indexer-worker

# Lingering is enabled
loginctl show-user $USER | grep Linger
# Should show: Linger=yes

# Services survive logout
# 1. Start services
# 2. Logout and SSH back in
# 3. Check: systemctl --user status vector-indexer
# Should still be running
```

## Troubleshooting

### Services not starting
```bash
# Check logs
journalctl --user -u vector-indexer -n 50

# Verify service file
systemd-analyze verify ~/.config/systemd/user/vector-indexer.service
```

### Services stop after logout
```bash
# Enable lingering
loginctl enable-linger $USER

# Verify
loginctl show-user $USER | grep Linger
```

### Permission errors
```bash
# Check directory ownership
ls -ld /srv/latvian_mcp

# Fix if needed
sudo chown -R $USER:$USER /srv/latvian_mcp
```

## Files Added/Modified

**Modified:**
- `vector-indexer-mcp-http.service` (User/Group removed, WantedBy changed)
- `vector-indexer-worker.service` (User/Group removed, WantedBy changed)
- `vector-indexer.service` (User/Group removed, WantedBy changed)
- `install_http_wrapper.sh` (User service installation)
- `README.md` (Command updates)

**Added:**
- `MIGRATION_USER_SERVICES.md` (Migration guide)
- `scripts/migrate_to_user_services.sh` (Automated migration)
- `USER_SERVICES_UPDATE.md` (This file)

## References

- [systemd User Services Documentation](https://wiki.archlinux.org/title/Systemd/User)
- [loginctl Manual](https://www.freedesktop.org/software/systemd/man/loginctl.html)
- [Lingering Explained](https://www.freedesktop.org/software/systemd/man/loginctl.html#enable-linger%20USER%E2%80%A6)

## Support

For issues or questions about the migration:
1. Check `MIGRATION_USER_SERVICES.md` troubleshooting section
2. Review logs: `journalctl --user -u vector-indexer -n 100`
3. Verify lingering: `loginctl show-user $USER | grep Linger`

## Rollback

To revert to system services, see the "Reverting to System Services" section in `MIGRATION_USER_SERVICES.md`.
