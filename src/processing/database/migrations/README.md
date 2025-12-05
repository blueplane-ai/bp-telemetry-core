<!--
Copyright © 2025 Sierra Labs LLC
SPDX-License-Identifier: AGPL-3.0-only
License-Filename: LICENSE
-->

# Database Migrations

This directory contains database schema migrations for Blueplane Telemetry Core.

## Migration System Overview

Blueplane uses a Flyway-inspired migration system with:

- **Versioned SQL files** in `V{XXX}__{description}/` directories
- **Rollback support** via separate `up.sql` and `down.sql` files
- **Checksum validation** to detect manual edits to applied migrations
- **Automated backups** before applying migrations
- **Lock file mechanism** to prevent concurrent migrations
- **Full metadata tracking** in the `migration_history` table

## Directory Structure

```
migrations/
├── README.md                           # This file
├── V001__initial_schema/
│   ├── up.sql                         # Upgrade script
│   ├── down.sql                       # Rollback script (optional)
│   └── metadata.yaml                  # Migration metadata (optional)
├── V002__cursor_sessions/
│   ├── up.sql
│   ├── down.sql
│   └── metadata.yaml
└── V003__workspaces_and_git/
    ├── up.sql
    ├── down.sql
    └── metadata.yaml
```

## Naming Convention

Migration directories must follow the pattern: `V{XXX}__{description}/`

- **V**: Required prefix
- **{XXX}**: Zero-padded 3-digit version number (e.g., `001`, `002`, `150`)
- **__**: Double underscore separator (required)
- **{description}**: Descriptive name using underscores (e.g., `add_user_settings`, `rename_conversations`)

Examples:
- ✅ `V001__initial_schema/`
- ✅ `V042__add_user_preferences/`
- ✅ `V150__optimize_indexes/`
- ❌ `V1__test/` (not zero-padded)
- ❌ `v001__test/` (lowercase 'v')
- ❌ `V001_test/` (single underscore)

## Migration Files

### up.sql (Required)

The upgrade script that applies the migration. Can contain any valid SQLite SQL, including:

- `CREATE TABLE` / `ALTER TABLE` statements
- `CREATE INDEX` statements
- `INSERT` / `UPDATE` statements for data migrations
- Multiple statements separated by semicolons

Example:
```sql
-- V005__add_user_settings/up.sql

CREATE TABLE user_settings (
    user_id TEXT PRIMARY KEY,
    theme TEXT DEFAULT 'light',
    notifications_enabled INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_settings_theme ON user_settings(theme);

-- Seed default settings
INSERT INTO user_settings (user_id, theme) VALUES ('default', 'dark');
```

### down.sql (Optional but Recommended)

The rollback script that reverses the migration. Should undo everything `up.sql` does.

Example:
```sql
-- V005__add_user_settings/down.sql

DROP INDEX IF EXISTS idx_user_settings_theme;
DROP TABLE IF EXISTS user_settings;
```

### metadata.yaml (Optional)

Additional metadata about the migration. Useful for documentation and tracking.

Example:
```yaml
version: 5
description: "Add user_settings table for preferences"
author: "dev@example.com"
created: "2025-01-04T14:30:00Z"
dependencies:
  - V001__initial_schema
tags:
  - user_preferences
  - settings
estimated_duration_ms: 100
reversible: true
notes: |
  This migration adds a central user_settings table to store
  per-user preferences like theme and notification settings.
```

## CLI Usage

Use the `migrate.py` CLI tool to manage migrations:

### Apply All Pending Migrations

```bash
python scripts/migrate.py up
```

### Dry-Run (Preview Without Applying)

```bash
python scripts/migrate.py up --dry-run
```

### Migrate to Specific Version

```bash
python scripts/migrate.py to --version 5
```

### Show Migration Status

```bash
python scripts/migrate.py status
```

### Validate Migrations

Checks for version gaps, duplicates, and checksum mismatches:

```bash
python scripts/migrate.py validate
```

### Rollback Last Migration

```bash
python scripts/migrate.py down
```

### Create New Migration

Generates a migration template:

```bash
python scripts/migrate.py create add_user_settings --author "dev@example.com"
```

This creates:
```
migrations/V{next}_add_user_settings/
├── up.sql          # Empty template with comments
├── down.sql        # Empty template with comments
└── metadata.yaml   # Pre-filled metadata
```

## Migration History Table

The system tracks all migrations in the `migration_history` table:

```sql
CREATE TABLE migration_history (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    checksum TEXT NOT NULL,              -- SHA256 of up.sql
    applied_at TIMESTAMP NOT NULL,
    execution_time_ms INTEGER,
    status TEXT NOT NULL,                -- 'completed', 'failed', 'rolled_back'
    rollback_at TIMESTAMP,
    applied_by TEXT,                     -- 'migrate.py', 'server.py', etc.
    metadata TEXT,                       -- JSON metadata
    error_message TEXT,
    hostname TEXT
);
```

Query migration history:
```sql
SELECT version, description, status, applied_at, execution_time_ms
FROM migration_history
ORDER BY version DESC;
```

## Workflow

### 1. Create a New Migration

```bash
# Generate template
python scripts/migrate.py create add_notifications --author "dev@example.com"
```

### 2. Edit Migration Files

Edit the generated `up.sql` and `down.sql` files:

```sql
-- migrations/V006__add_notifications/up.sql

CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    message TEXT NOT NULL,
    read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_notifications_user ON notifications(user_id, created_at DESC);
```

```sql
-- migrations/V006__add_notifications/down.sql

DROP INDEX IF EXISTS idx_notifications_user;
DROP TABLE IF EXISTS notifications;
```

### 3. Validate Migration

```bash
python scripts/migrate.py validate
```

### 4. Test with Dry-Run

```bash
python scripts/migrate.py up --dry-run
```

### 5. Apply Migration

```bash
python scripts/migrate.py up
```

### 6. Commit to Git

```bash
git add src/processing/database/migrations/V006__add_notifications
git commit -m "feat: Add notifications table (migration V006)"
```

## Best Practices

### DO:

1. **Test migrations on a backup** before applying to production
2. **Always provide down.sql** for rollback capability
3. **Keep migrations small and focused** on a single change
4. **Use transactions implicitly** (SQLite executescript uses transactions)
5. **Add comments** to explain complex migrations
6. **Include indexes** in the same migration as the table
7. **Validate** before committing with `migrate.py validate`
8. **Test rollback** to ensure down.sql works correctly

### DON'T:

1. **Never edit applied migrations** - checksums will fail validation
2. **Don't skip version numbers** - keep them sequential
3. **Don't reuse version numbers** - always increment
4. **Don't make migrations depend on application code** - use pure SQL
5. **Don't combine DDL and large data migrations** - split into separate migrations
6. **Don't use database-specific features** unless necessary
7. **Don't forget to update SCHEMA_VERSION** in schema.py

## Backward Compatibility

The migration system is backward compatible with inline Python migrations (v2-v4).

Existing migrations are automatically registered as inline migrations during server startup:

```python
# Inline migration example (for backward compatibility only)
runner.register_inline_migration(
    version=2,
    description="cursor_sessions",
    up_func=migrate_to_v2,
    down_func=None,
)
```

**New migrations should always use SQL files**, not inline Python functions.

## Safety Features

### Automated Backups

Before applying migrations, the system creates a backup:

```
~/.blueplane/backups/telemetry_pre_v{version}_{timestamp}.db
```

Backups use SQLite's `VACUUM INTO` for consistency. By default, the last 10 backups are retained.

### Lock File

Prevents concurrent migrations:

```
~/.blueplane/migration.lock
```

Contains PID and timestamp. Automatically detects and removes stale locks.

### Checksum Validation

Computes SHA256 hash of `up.sql` content. Detects if an applied migration file was edited:

```
Migration v3 checksum mismatch:
  Expected: a3f9c8d2...
  Got:      b7e1f5a8...
```

### Dry-Run Mode

Preview migrations without applying them:

```bash
python scripts/migrate.py up --dry-run
```

Shows:
- Which migrations would be applied
- SQL content preview
- No database changes

## Troubleshooting

### Migration Fails

1. **Check error message** in logs
2. **Restore from backup** in `~/.blueplane/backups/`
3. **Fix migration SQL** in the migration directory
4. **Re-run** migration

### Checksum Mismatch

If you need to fix an applied migration:

```bash
# Option 1: Rollback and re-apply
python scripts/migrate.py down
# Fix migration file
python scripts/migrate.py up

# Option 2: Restore from backup
cp ~/.blueplane/backups/telemetry_pre_v{version}_{timestamp}.db ~/.blueplane/telemetry.db
# Fix migration file
python scripts/migrate.py up
```

### Lock File Issues

If migration is stuck:

```bash
# Remove lock file manually
rm ~/.blueplane/migration.lock

# Check if process is still running
ps aux | grep migrate
```

### Check Migration Status

```bash
# Show applied migrations
python scripts/migrate.py status

# Query database directly
sqlite3 ~/.blueplane/telemetry.db \
  "SELECT version, description, status, applied_at FROM migration_history ORDER BY version;"
```

## Production Deployment

1. **Backup database** before deployment
2. **Run validation** to ensure migrations are consistent
3. **Test on staging** environment first
4. **Use dry-run** to preview changes
5. **Apply migrations** during maintenance window
6. **Monitor logs** for errors
7. **Keep backups** for quick rollback

## References

- Migration runner implementation: [src/processing/database/migration_runner.py](../migration_runner.py)
- CLI tool: [scripts/migrate.py](../../../../scripts/migrate.py)
- Schema definitions: [src/processing/database/schema.py](../schema.py)
