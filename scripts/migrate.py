#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
CLI tool for managing database migrations.

Provides commands to:
- Apply migrations (up)
- Rollback migrations (down)
- Migrate to specific version (to)
- Show migration status (status)
- Validate migrations (validate)
- Create new migration templates (create)
"""

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.processing.database.sqlite_client import SQLiteClient
from src.processing.database.migration_runner import (
    MigrationRunner,
    MigrationValidationError,
    MigrationLockError,
)
from src.processing.database.schema import (
    get_schema_version,
    SCHEMA_VERSION,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_default_db_path() -> Path:
    """Get default database path."""
    return Path.home() / ".blueplane" / "telemetry.db"


def get_migrations_dir() -> Path:
    """Get migrations directory path."""
    return PROJECT_ROOT / "src" / "processing" / "database" / "migrations"


def init_runner(db_path: Optional[Path] = None) -> MigrationRunner:
    """
    Initialize MigrationRunner with backward compatibility for old schema_version system.

    Args:
        db_path: Optional database path (default: ~/.blueplane/telemetry.db)

    Returns:
        MigrationRunner instance
    """
    if db_path is None:
        db_path = get_default_db_path()

    # Ensure database directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    client = SQLiteClient(db_path)
    runner = MigrationRunner(client, migrations_dir=get_migrations_dir())

    # Initialize migration_history table
    runner.initialize_migration_history()

    # Check for old schema_version table and backfill if needed
    current_version = runner.get_current_version()
    if current_version == 0:
        old_version = get_schema_version(client)
        if old_version and old_version > 0:
            logger.info(f"Detected old schema_version system (v{old_version}), backfilling migration_history...")

            # Backfill migration_history for v1 through old_version
            description_map = {
                1: "initial_schema",
                2: "cursor_sessions",
                3: "workspaces_and_git",
                4: "rename_conversations",
            }

            for v in range(1, old_version + 1):
                runner._record_migration_status(
                    version=v,
                    description=description_map.get(v, f"legacy_v{v}"),
                    checksum="legacy_backfill",
                    execution_time_ms=0,
                    status='completed',
                    applied_by='migrate.py_backfill',
                    metadata={'backfilled': True, 'original_system': 'schema_version'},
                )

            logger.info(f"Backfilled migration_history with v1-v{old_version}")

    return runner


def cmd_up(args):
    """Apply all pending migrations."""
    runner = init_runner(args.db_path)

    current_version = runner.get_current_version()
    pending = runner.get_pending_migrations()

    if not pending:
        print(f"✓ Database is up to date (v{current_version})")
        return 0

    target_version = pending[-1].version

    print(f"Migrating from v{current_version} to v{target_version}")
    print(f"Pending migrations: {len(pending)}")
    print()

    for migration in pending:
        print(f"  - v{migration.version}: {migration.description}")

    print()

    if args.dry_run:
        print("[DRY RUN] No changes will be made")
        return 0

    success = runner.migrate_to(target_version, dry_run=False)

    if success:
        print()
        print(f"✓ Successfully migrated to v{target_version}")
        return 0
    else:
        print()
        print(f"✗ Migration failed")
        return 1


def cmd_down(args):
    """Rollback last migration."""
    runner = init_runner(args.db_path)

    current_version = runner.get_current_version()

    if current_version == 0:
        print("No migrations to rollback")
        return 0

    applied = runner.get_applied_migrations()
    last_migration = applied[-1]

    print(f"Rolling back v{last_migration.version}: {last_migration.description}")

    if args.dry_run:
        print("[DRY RUN] No changes will be made")
        return 0

    success = runner.rollback_migration(last_migration.version)

    if success:
        new_version = runner.get_current_version()
        print(f"✓ Rolled back to v{new_version}")
        return 0
    else:
        print("✗ Rollback failed")
        return 1


def cmd_to(args):
    """Migrate to specific version."""
    runner = init_runner(args.db_path)

    current_version = runner.get_current_version()
    target_version = args.version

    if current_version == target_version:
        print(f"✓ Already at v{target_version}")
        return 0

    if current_version > target_version:
        print(f"✗ Downgrade not supported (current: v{current_version}, target: v{target_version})")
        print("Use 'migrate.py down' to rollback one migration at a time")
        return 1

    print(f"Migrating from v{current_version} to v{target_version}")

    if args.dry_run:
        pending = runner.get_pending_migrations(target_version)
        print(f"[DRY RUN] Would apply {len(pending)} migration(s):")
        for migration in pending:
            print(f"  - v{migration.version}: {migration.description}")
        return 0

    success = runner.migrate_to(target_version, dry_run=False)

    if success:
        print(f"✓ Successfully migrated to v{target_version}")
        return 0
    else:
        print("✗ Migration failed")
        return 1


def cmd_status(args):
    """Show migration status."""
    runner = init_runner(args.db_path)

    current_version = runner.get_current_version()
    applied = runner.get_applied_migrations()
    pending = runner.get_pending_migrations()

    print("=" * 70)
    print("Migration Status")
    print("=" * 70)
    print()
    print(f"Current version: v{current_version}")
    print(f"Applied migrations: {len(applied)}")
    print(f"Pending migrations: {len(pending)}")
    print()

    if applied:
        print("Applied Migrations:")
        print("-" * 70)
        for migration in applied:
            status_icon = {
                'completed': '✓',
                'failed': '✗',
                'rolled_back': '⟲',
            }.get(migration.status, '?')

            print(f"{status_icon} v{migration.version:03d} - {migration.description}")
            print(f"    Status: {migration.status}")
            print(f"    Applied: {migration.applied_at.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    Duration: {migration.execution_time_ms}ms")

            if migration.error_message:
                print(f"    Error: {migration.error_message}")

            print()

    if pending:
        print("Pending Migrations:")
        print("-" * 70)
        for migration in pending:
            print(f"  v{migration.version:03d} - {migration.description}")
        print()

    print("=" * 70)

    return 0


def cmd_validate(args):
    """Validate migration consistency."""
    runner = init_runner(args.db_path)

    print("Validating migrations...")
    print()

    is_valid, errors = runner.validate_migrations()

    if is_valid:
        print("✓ All migrations are valid")
        return 0
    else:
        print("✗ Migration validation failed:")
        print()
        for error in errors:
            print(f"  - {error}")
        print()
        return 1


def cmd_create(args):
    """Create new migration template."""
    migrations_dir = get_migrations_dir()

    # Find next version number
    existing = sorted(
        [d for d in migrations_dir.iterdir() if d.is_dir() and d.name.startswith('V')],
        key=lambda d: int(d.name.split('__')[0][1:])
    )

    next_version = 1
    if existing:
        last_version = int(existing[-1].name.split('__')[0][1:])
        next_version = last_version + 1

    # Create directory name
    description = args.description.replace(' ', '_').replace('-', '_')
    dirname = f"V{next_version:03d}__{description}"
    migration_dir = migrations_dir / dirname

    if migration_dir.exists():
        print(f"✗ Migration directory already exists: {migration_dir}")
        return 1

    # Create migration directory
    migration_dir.mkdir(parents=True, exist_ok=True)

    # Create up.sql
    up_sql_content = f"""-- Migration: v{next_version} - {description.replace('_', ' ')}
-- Created: {datetime.now(timezone.utc).isoformat()}
-- Author: {args.author or 'unknown'}

-- Add your upgrade SQL here

"""

    (migration_dir / "up.sql").write_text(up_sql_content)

    # Create down.sql
    down_sql_content = f"""-- Rollback: v{next_version} - {description.replace('_', ' ')}
-- Created: {datetime.now(timezone.utc).isoformat()}
-- Author: {args.author or 'unknown'}

-- Add your rollback SQL here
-- This should undo everything in up.sql

"""

    (migration_dir / "down.sql").write_text(down_sql_content)

    # Create metadata.yaml
    metadata_content = f"""version: {next_version}
description: "{description.replace('_', ' ')}"
author: "{args.author or 'unknown'}"
created: "{datetime.now(timezone.utc).isoformat()}"
dependencies: []
tags: []
estimated_duration_ms: 100
reversible: true
notes: |
  Add notes about this migration here.
"""

    (migration_dir / "metadata.yaml").write_text(metadata_content)

    print(f"✓ Created migration: {dirname}")
    print()
    print(f"Files created:")
    print(f"  - {migration_dir / 'up.sql'}")
    print(f"  - {migration_dir / 'down.sql'}")
    print(f"  - {migration_dir / 'metadata.yaml'}")
    print()
    print("Next steps:")
    print(f"  1. Edit {migration_dir / 'up.sql'} with your upgrade SQL")
    print(f"  2. Edit {migration_dir / 'down.sql'} with your rollback SQL")
    print(f"  3. Run: python scripts/migrate.py validate")
    print(f"  4. Run: python scripts/migrate.py up --dry-run")
    print(f"  5. Run: python scripts/migrate.py up")

    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Database migration CLI tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Apply all pending migrations
  python scripts/migrate.py up

  # Dry-run (preview without applying)
  python scripts/migrate.py up --dry-run

  # Rollback last migration
  python scripts/migrate.py down

  # Migrate to specific version
  python scripts/migrate.py to --version 5

  # Show migration status
  python scripts/migrate.py status

  # Validate migrations
  python scripts/migrate.py validate

  # Create new migration
  python scripts/migrate.py create add_user_settings --author "dev@example.com"
"""
    )

    parser.add_argument(
        '--db-path',
        type=Path,
        help='Database path (default: ~/.blueplane/telemetry.db)'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # up command
    up_parser = subparsers.add_parser('up', help='Apply all pending migrations')
    up_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview migrations without applying'
    )
    up_parser.set_defaults(func=cmd_up)

    # down command
    down_parser = subparsers.add_parser('down', help='Rollback last migration')
    down_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview rollback without applying'
    )
    down_parser.set_defaults(func=cmd_down)

    # to command
    to_parser = subparsers.add_parser('to', help='Migrate to specific version')
    to_parser.add_argument(
        '--version',
        type=int,
        required=True,
        help='Target version number'
    )
    to_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview migrations without applying'
    )
    to_parser.set_defaults(func=cmd_to)

    # status command
    status_parser = subparsers.add_parser('status', help='Show migration status')
    status_parser.set_defaults(func=cmd_status)

    # validate command
    validate_parser = subparsers.add_parser('validate', help='Validate migrations')
    validate_parser.set_defaults(func=cmd_validate)

    # create command
    create_parser = subparsers.add_parser('create', help='Create new migration template')
    create_parser.add_argument(
        'description',
        help='Migration description (e.g., add_user_settings)'
    )
    create_parser.add_argument(
        '--author',
        help='Author email'
    )
    create_parser.set_defaults(func=cmd_create)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        return args.func(args)
    except MigrationValidationError as e:
        logger.error(f"Validation error: {e}")
        return 1
    except MigrationLockError as e:
        logger.error(f"Lock error: {e}")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
