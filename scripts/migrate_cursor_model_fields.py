#!/usr/bin/env python3
"""
Migration script to add model fields to cursor_raw_traces table.

This migration adds:
- model_name TEXT - Primary model used (e.g., "claude-4.5-opus-high-thinking")
- model_cost_cents INTEGER - Cost in cents for this model
- model_response_count INTEGER - Number of AI responses using this model  
- models_used TEXT - JSON array of all models if multiple used

The model information is extracted from the usageData field in composerData,
where the model name is stored as the KEY of the dictionary.

Usage:
    python scripts/migrate_cursor_model_fields.py
    python scripts/migrate_cursor_model_fields.py --db-path /path/to/telemetry.db
"""

import argparse
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_default_db_path() -> Path:
    """Get default telemetry database path."""
    return Path.home() / ".blueplane" / "telemetry.db"


def check_columns_exist(conn: sqlite3.Connection) -> dict:
    """Check which model columns already exist."""
    cursor = conn.execute("PRAGMA table_info(cursor_raw_traces)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    
    model_columns = ['model_name', 'model_cost_cents', 'model_response_count', 'models_used']
    return {col: col in existing_columns for col in model_columns}


def migrate_cursor_model_fields(db_path: Path) -> bool:
    """
    Add model fields to cursor_raw_traces table.
    
    Args:
        db_path: Path to telemetry database
        
    Returns:
        True if migration successful, False otherwise
    """
    if not db_path.exists():
        logger.error(f"Database not found at {db_path}")
        return False
    
    try:
        conn = sqlite3.connect(str(db_path))
        
        # Check if cursor_raw_traces table exists
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='cursor_raw_traces'
        """)
        if not cursor.fetchone():
            logger.info("cursor_raw_traces table does not exist yet - no migration needed")
            return True
        
        # Check which columns need to be added
        column_status = check_columns_exist(conn)
        
        columns_to_add = [col for col, exists in column_status.items() if not exists]
        
        if not columns_to_add:
            logger.info("All model columns already exist - no migration needed")
            return True
        
        logger.info(f"Adding columns: {columns_to_add}")
        
        # Add missing columns
        column_definitions = {
            'model_name': 'TEXT',
            'model_cost_cents': 'INTEGER', 
            'model_response_count': 'INTEGER',
            'models_used': 'TEXT',
        }
        
        for col in columns_to_add:
            col_type = column_definitions[col]
            try:
                conn.execute(f"ALTER TABLE cursor_raw_traces ADD COLUMN {col} {col_type}")
                logger.info(f"Added column: {col} {col_type}")
            except sqlite3.OperationalError as e:
                if "duplicate column" in str(e).lower():
                    logger.info(f"Column {col} already exists")
                else:
                    raise
        
        # Add index for model_name if it doesn't exist
        try:
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_cursor_model 
                ON cursor_raw_traces(model_name) 
                WHERE model_name IS NOT NULL
            """)
            logger.info("Created index idx_cursor_model")
        except sqlite3.OperationalError as e:
            if "already exists" in str(e).lower():
                logger.info("Index idx_cursor_model already exists")
            else:
                raise
        
        conn.commit()
        conn.close()
        
        logger.info("Migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Add model fields to cursor_raw_traces table"
    )
    parser.add_argument(
        "--db-path",
        help="Path to telemetry database (default: ~/.blueplane/telemetry.db)",
        type=Path,
        default=None
    )
    
    args = parser.parse_args()
    
    db_path = args.db_path or get_default_db_path()
    
    logger.info(f"Migrating database: {db_path}")
    
    success = migrate_cursor_model_fields(db_path)
    
    if success:
        print("\n✅ Migration completed successfully!")
    else:
        print("\n❌ Migration failed!")
        exit(1)


if __name__ == "__main__":
    main()

