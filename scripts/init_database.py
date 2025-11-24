#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Database initialization script for Blueplane Telemetry Core.

Creates SQLite database with schema and optimal settings.
"""

import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from blueplane.processing.database.sqlite_client import SQLiteClient
from blueplane.processing.database.schema import create_schema, get_schema_version, SCHEMA_VERSION

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Initialize database."""
    # Default database path
    db_path = Path.home() / ".blueplane" / "telemetry.db"
    
    logger.info(f"Initializing database: {db_path}")
    
    # Create client
    client = SQLiteClient(str(db_path))
    
    # Initialize database (creates directory, sets PRAGMAs)
    try:
        client.initialize_database()
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return 1
    
    # Check schema version
    current_version = get_schema_version(client)
    
    if current_version is None:
        # First time setup - create schema
        logger.info("Creating database schema...")
        create_schema(client)
        
        # Set schema version
        client.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"
        )
        client.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,)
        )
        logger.info(f"Database schema created (version {SCHEMA_VERSION})")
    elif current_version < SCHEMA_VERSION:
        # Migration needed
        logger.info(f"Migrating schema from version {current_version} to {SCHEMA_VERSION}")
        from blueplane.processing.database.schema import migrate_schema
        migrate_schema(client, current_version, SCHEMA_VERSION)
    else:
        logger.info(f"Database schema is up to date (version {current_version})")
    
    # Verify database
    if client.exists():
        logger.info("✅ Database initialized successfully")
        return 0
    else:
        logger.error("❌ Database file was not created")
        return 1


if __name__ == "__main__":
    sys.exit(main())

