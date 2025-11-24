#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Migration script for session/conversation schema (v1 -> v2).

Migrates existing database to new schema:
- Creates cursor_sessions table
- Migrates Cursor sessions from conversations to cursor_sessions
- Updates conversations table schema (nullable session_id, external_id)
- Creates new indexes

Usage:
    python scripts/migrate_sessions_schema.py [--db-path PATH]
"""

import argparse
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from blueplane.processing.database.sqlite_client import SQLiteClient
from blueplane.processing.database.schema import (
    get_schema_version,
    migrate_schema,
    SCHEMA_VERSION
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backup_database(db_path: Path) -> Path:
    """
    Create a backup of the database before migration.
    
    Args:
        db_path: Path to database file
        
    Returns:
        Path to backup file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"
    
    logger.info(f"Creating backup: {backup_path}")
    shutil.copy2(db_path, backup_path)
    logger.info(f"✅ Backup created: {backup_path}")
    
    return backup_path


def validate_migration(client: SQLiteClient) -> bool:
    """
    Validate migration results.
    
    Args:
        client: SQLiteClient instance
        
    Returns:
        True if validation passes
    """
    logger.info("Validating migration...")
    
    try:
        with client.get_connection() as conn:
            # Check cursor_sessions table exists
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='cursor_sessions'
            """)
            if not cursor.fetchone():
                logger.error("❌ cursor_sessions table not found")
                return False
            
            # Check conversations table has new schema
            cursor = conn.execute("PRAGMA table_info(conversations)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'external_id' not in columns:
                logger.error("❌ conversations table missing external_id column")
                return False
            
            if 'external_session_id' in columns:
                logger.warning("⚠️  conversations table still has external_session_id column (may be expected)")
            
            # Check for invalid session_id values
            cursor = conn.execute("""
                SELECT COUNT(*) FROM conversations 
                WHERE (platform = 'cursor' AND session_id IS NULL) OR
                      (platform = 'claude_code' AND session_id IS NOT NULL)
            """)
            invalid_count = cursor.fetchone()[0]
            if invalid_count > 0:
                logger.error(f"❌ Found {invalid_count} conversations with invalid session_id values")
                return False
            
            # Check for orphaned Cursor conversations
            cursor = conn.execute("""
                SELECT COUNT(*) FROM conversations c
                LEFT JOIN cursor_sessions s ON c.session_id = s.id
                WHERE c.platform = 'cursor' AND s.id IS NULL
            """)
            orphaned_count = cursor.fetchone()[0]
            if orphaned_count > 0:
                logger.error(f"❌ Found {orphaned_count} orphaned Cursor conversations")
                return False
            
            logger.info("✅ Migration validation passed")
            return True
            
    except Exception as e:
        logger.error(f"❌ Validation failed: {e}", exc_info=True)
        return False


def main() -> int:
    """Run migration."""
    parser = argparse.ArgumentParser(
        description="Migrate database schema to version 2 (session/conversation schema)"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(Path.home() / ".blueplane" / "telemetry.db"),
        help="Path to database file (default: ~/.blueplane/telemetry.db)"
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip database backup (not recommended)"
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip post-migration validation"
    )
    
    args = parser.parse_args()
    
    db_path = Path(args.db_path)
    
    if not db_path.exists():
        logger.error(f"❌ Database file not found: {db_path}")
        logger.info("Run 'python scripts/init_database.py' to create a new database")
        return 1
    
    logger.info(f"Migrating database: {db_path}")
    
    # Create backup
    if not args.no_backup:
        try:
            backup_path = backup_database(db_path)
        except Exception as e:
            logger.error(f"❌ Failed to create backup: {e}")
            return 1
    else:
        logger.warning("⚠️  Skipping backup (--no-backup flag)")
        backup_path = None
    
    # Create client
    client = SQLiteClient(str(db_path))
    
    # Check current version
    current_version = get_schema_version(client)
    logger.info(f"Current schema version: {current_version}")
    logger.info(f"Target schema version: {SCHEMA_VERSION}")
    
    if current_version is None:
        logger.warning("⚠️  No schema version found, assuming version 1")
        current_version = 1
    
    if current_version >= SCHEMA_VERSION:
        logger.info(f"✅ Database already at version {current_version}, no migration needed")
        return 0
    
    # Run migration
    try:
        logger.info("Starting migration...")
        migrate_schema(client, current_version, SCHEMA_VERSION)
        logger.info("✅ Migration completed successfully")
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}", exc_info=True)
        if backup_path:
            logger.info(f"💡 To restore backup, run: cp {backup_path} {db_path}")
        return 1
    
    # Validate migration
    if not args.skip_validation:
        if not validate_migration(client):
            logger.error("❌ Migration validation failed")
            if backup_path:
                logger.info(f"💡 To restore backup, run: cp {backup_path} {db_path}")
            return 1
    
    logger.info("✅ Migration completed and validated successfully")
    if backup_path:
        logger.info(f"💡 Backup saved at: {backup_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

