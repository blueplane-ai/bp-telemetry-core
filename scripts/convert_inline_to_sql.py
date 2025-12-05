#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
One-time conversion tool for migrating inline Python migrations to SQL files.

Extracts SQL from existing migrate_to_v2, migrate_to_v3, migrate_to_v4 functions
and generates corresponding V{XXX}__{description}/ directories with:
- up.sql
- down.sql
- metadata.yaml

Note: V002 contains complex data migration logic that should remain in Python.
This tool will generate SQL for the DDL portions and document the data migration.
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def create_v002_migration(output_dir: Path):
    """
    Create V002__cursor_sessions migration.

    Note: This migration includes complex data migration from raw_traces
    that cannot be easily represented in pure SQL. The SQL files will contain
    the DDL, and the inline Python function should be retained for the data migration.
    """
    migration_dir = output_dir / "V002__cursor_sessions"
    migration_dir.mkdir(parents=True, exist_ok=True)

    # up.sql - DDL portion only
    up_sql = """-- Migration v2: Add cursor_sessions table and update conversations table
-- Created: 2025-01-04
-- Author: Blueplane Telemetry Core

-- ============================================================================
-- Part 1: Create cursor_sessions table
-- ============================================================================

CREATE TABLE IF NOT EXISTS cursor_sessions (
    session_id TEXT PRIMARY KEY,
    workspace_hash TEXT,
    workspace_path TEXT,
    workspace_name TEXT,
    machine_id TEXT,
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    last_seen TIMESTAMP,
    metadata TEXT DEFAULT '{}'
);

-- Create indexes for cursor_sessions
CREATE INDEX IF NOT EXISTS idx_cursor_sessions_workspace
ON cursor_sessions(workspace_hash, start_time DESC);

CREATE INDEX IF NOT EXISTS idx_cursor_sessions_machine
ON cursor_sessions(machine_id, start_time DESC);

CREATE INDEX IF NOT EXISTS idx_cursor_sessions_last_seen
ON cursor_sessions(last_seen DESC);

-- ============================================================================
-- Part 2: Update conversations table structure
-- ============================================================================

-- Note: The actual data migration and schema changes to conversations table
-- are handled by the inline Python migration function migrate_to_v2() due to
-- complexity of the data transformations required.
--
-- The Python function:
-- 1. Creates a new conversations_new table with updated schema
-- 2. Migrates data from conversations with transformations
-- 3. Drops old conversations table
-- 4. Renames conversations_new to conversations
-- 5. Recreates all indexes
--
-- This ensures data integrity during the complex schema change.
"""

    (migration_dir / "up.sql").write_text(up_sql)

    # down.sql
    down_sql = """-- Rollback v2: Remove cursor_sessions table changes
-- Created: 2025-01-04

-- Drop cursor_sessions indexes
DROP INDEX IF EXISTS idx_cursor_sessions_workspace;
DROP INDEX IF EXISTS idx_cursor_sessions_machine;
DROP INDEX IF EXISTS idx_cursor_sessions_last_seen;

-- Drop cursor_sessions table
DROP TABLE IF EXISTS cursor_sessions;

-- Note: Rollback of conversations table changes is not supported
-- due to data transformation complexity. Restore from backup if needed.
"""

    (migration_dir / "down.sql").write_text(down_sql)

    # metadata.yaml
    metadata = f"""version: 2
description: "Add cursor_sessions table and update conversations table"
author: "blueplane"
created: "{datetime.now(timezone.utc).isoformat()}"
dependencies:
  - V001__initial_schema
tags:
  - cursor
  - sessions
estimated_duration_ms: 500
reversible: false
notes: |
  This migration adds cursor_sessions table for Cursor IDE window sessions.

  IMPORTANT: This migration includes complex data migration logic that
  remains in the inline Python function migrate_to_v2().

  The SQL files contain only the DDL portions. The actual conversations
  table migration is handled by Python code in schema.py due to:
  - Complex data transformations
  - Multi-step table recreation
  - Index recreation

  For production use, the inline Python migration should be retained
  alongside these SQL files for backward compatibility.
"""

    (migration_dir / "metadata.yaml").write_text(metadata)

    print(f"✓ Created {migration_dir.name}")


def create_v003_migration(output_dir: Path):
    """Create V003__workspaces_and_git migration."""
    migration_dir = output_dir / "V003__workspaces_and_git"
    migration_dir.mkdir(parents=True, exist_ok=True)

    # up.sql
    up_sql = """-- Migration v3: Add workspaces and git_commits tables
-- Created: 2025-01-04
-- Author: Blueplane Telemetry Core

-- ============================================================================
-- Part 1: Create workspaces table
-- ============================================================================

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_hash TEXT PRIMARY KEY,
    workspace_path TEXT NOT NULL,
    workspace_name TEXT,
    first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT DEFAULT '{}'
);

-- Create workspaces indexes
CREATE INDEX IF NOT EXISTS idx_workspaces_path
ON workspaces(workspace_path);

CREATE INDEX IF NOT EXISTS idx_workspaces_last_seen
ON workspaces(last_seen_at DESC);

-- ============================================================================
-- Part 2: Create git_commits table
-- ============================================================================

CREATE TABLE IF NOT EXISTS git_commits (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_hash TEXT NOT NULL,
    repo_id TEXT NOT NULL,
    workspace_hash TEXT NOT NULL,
    author_name TEXT,
    author_email TEXT,
    commit_timestamp TIMESTAMP NOT NULL,
    commit_message TEXT,
    files_changed INTEGER DEFAULT 0,
    insertions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    branch_name TEXT,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_id TEXT,
    UNIQUE(repo_id, commit_hash)
);

-- Create git_commits indexes
CREATE INDEX IF NOT EXISTS idx_git_commits_workspace
ON git_commits(workspace_hash, commit_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_git_commits_repo
ON git_commits(repo_id, commit_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_git_commits_timestamp
ON git_commits(commit_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_git_commits_author
ON git_commits(author_email, commit_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_git_commits_branch
ON git_commits(branch_name, commit_timestamp DESC);

-- ============================================================================
-- Part 3: Backfill workspaces from cursor_sessions
-- ============================================================================

INSERT OR IGNORE INTO workspaces (workspace_hash, workspace_path, workspace_name)
SELECT DISTINCT workspace_hash,
       COALESCE(workspace_path, ''),
       workspace_name
FROM cursor_sessions
WHERE workspace_hash IS NOT NULL;

-- ============================================================================
-- Part 4: Backfill workspaces from conversations
-- ============================================================================

INSERT OR IGNORE INTO workspaces (workspace_hash, workspace_path, workspace_name)
SELECT DISTINCT workspace_hash,
       COALESCE(json_extract(context, '$.workspace_path'), ''),
       workspace_name
FROM conversations
WHERE workspace_hash IS NOT NULL;
"""

    (migration_dir / "up.sql").write_text(up_sql)

    # down.sql
    down_sql = """-- Rollback v3: Remove workspaces and git_commits tables
-- Created: 2025-01-04

-- Drop git_commits indexes
DROP INDEX IF EXISTS idx_git_commits_workspace;
DROP INDEX IF EXISTS idx_git_commits_repo;
DROP INDEX IF EXISTS idx_git_commits_timestamp;
DROP INDEX IF EXISTS idx_git_commits_author;
DROP INDEX IF EXISTS idx_git_commits_branch;

-- Drop git_commits table
DROP TABLE IF EXISTS git_commits;

-- Drop workspaces indexes
DROP INDEX IF EXISTS idx_workspaces_path;
DROP INDEX IF EXISTS idx_workspaces_last_seen;

-- Drop workspaces table
DROP TABLE IF EXISTS workspaces;
"""

    (migration_dir / "down.sql").write_text(down_sql)

    # metadata.yaml
    metadata = f"""version: 3
description: "Add workspaces and git_commits tables"
author: "blueplane"
created: "{datetime.now(timezone.utc).isoformat()}"
dependencies:
  - V002__cursor_sessions
tags:
  - workspaces
  - git
  - commits
estimated_duration_ms: 200
reversible: true
notes: |
  This migration creates the workspaces table as a central registry for
  workspace identification, linking cursor_sessions, conversations, and
  git_commits together.

  The git_commits table stores commit metadata with workspace and repo
  linking for analysis.

  Backfills workspaces from existing cursor_sessions and conversations data.
"""

    (migration_dir / "metadata.yaml").write_text(metadata)

    print(f"✓ Created {migration_dir.name}")


def create_v004_migration(output_dir: Path):
    """Create V004__rename_conversations migration."""
    migration_dir = output_dir / "V004__rename_conversations"
    migration_dir.mkdir(parents=True, exist_ok=True)

    # up.sql
    up_sql = """-- Migration v4: Rename conversations table to claude_conversations
-- Created: 2025-01-04
-- Author: Blueplane Telemetry Core

-- ============================================================================
-- Rename conversations table for clarity
-- ============================================================================

-- Disable foreign keys for migration
PRAGMA foreign_keys = OFF;

-- Rename table (only if exists)
-- Note: This is handled conditionally in the Python code,
--       but for pure SQL we attempt the rename

-- Check will be done by application code before executing this

ALTER TABLE conversations RENAME TO claude_conversations;

-- Re-enable foreign keys
PRAGMA foreign_keys = ON;

-- Note: Index renaming is handled by SQLite automatically in some versions,
--       but may need manual intervention. The Python migration handles this
--       by detecting and renaming indexes with pattern matching.
"""

    (migration_dir / "up.sql").write_text(up_sql)

    # down.sql
    down_sql = """-- Rollback v4: Rename claude_conversations back to conversations
-- Created: 2025-01-04

-- Disable foreign keys for migration
PRAGMA foreign_keys = OFF;

-- Rename table back
ALTER TABLE claude_conversations RENAME TO conversations;

-- Re-enable foreign keys
PRAGMA foreign_keys = ON;
"""

    (migration_dir / "down.sql").write_text(down_sql)

    # metadata.yaml
    metadata = f"""version: 4
description: "Rename conversations table to claude_conversations"
author: "blueplane"
created: "{datetime.now(timezone.utc).isoformat()}"
dependencies:
  - V003__workspaces_and_git
tags:
  - conversations
  - claude
  - rename
estimated_duration_ms: 100
reversible: true
notes: |
  This migration renames the conversations table to claude_conversations
  for clarity, as the table is specific to Claude Code interactions.

  The Python implementation includes additional logic to:
  - Check if the table exists before renaming
  - Handle index renaming with pattern matching
  - Gracefully handle the case where the table was already renamed

  For production use, the inline Python migration provides more robust
  handling of edge cases.
"""

    (migration_dir / "metadata.yaml").write_text(metadata)

    print(f"✓ Created {migration_dir.name}")


def main():
    parser = argparse.ArgumentParser(
        description='Convert inline Python migrations to SQL files'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=PROJECT_ROOT / "src" / "processing" / "database" / "migrations",
        help='Output directory for migration files (default: src/processing/database/migrations)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing migration directories'
    )

    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Converting Inline Migrations to SQL")
    print("=" * 70)
    print()
    print(f"Output directory: {output_dir}")
    print()

    # Check for existing migrations
    existing = []
    for version in ['V002__cursor_sessions', 'V003__workspaces_and_git', 'V004__rename_conversations']:
        migration_dir = output_dir / version
        if migration_dir.exists():
            existing.append(version)

    if existing and not args.force:
        print("✗ The following migrations already exist:")
        for dirname in existing:
            print(f"  - {dirname}")
        print()
        print("Use --force to overwrite existing migrations")
        return 1

    # Create migrations
    print("Creating SQL migrations...")
    print()

    create_v002_migration(output_dir)
    create_v003_migration(output_dir)
    create_v004_migration(output_dir)

    print()
    print("=" * 70)
    print("✓ Conversion complete!")
    print("=" * 70)
    print()
    print("IMPORTANT NOTES:")
    print()
    print("1. V002 migration includes complex data migration logic that")
    print("   should remain in the inline Python function migrate_to_v2().")
    print("   The SQL files contain only the DDL portions.")
    print()
    print("2. For backward compatibility, the inline Python migrations")
    print("   should be retained in schema.py alongside the new SQL files.")
    print()
    print("3. The migration runner will handle both SQL and inline migrations,")
    print("   merging them into a single migration timeline.")
    print()
    print("Next steps:")
    print("  1. Review the generated SQL files")
    print("  2. Run: python scripts/migrate.py validate")
    print("  3. Test on a development database")
    print("  4. Commit the migration files to git")

    return 0


if __name__ == '__main__':
    sys.exit(main())
