#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Migration script to add UNIQUE constraint on claude_raw_traces(external_id, uuid).

This prevents duplicate events from being inserted into the database.
Run this after cleaning up existing duplicates.

Usage:
    python scripts/add_unique_constraint.py [--cleanup-duplicates]

Options:
    --cleanup-duplicates    Remove duplicate events before adding constraint
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.processing.database.sqlite_client import SQLiteClient

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cleanup_duplicates(client: SQLiteClient) -> int:
    """
    Remove duplicate events, keeping only the first occurrence (lowest sequence).

    Args:
        client: SQLiteClient instance

    Returns:
        Number of duplicate rows removed
    """
    logger.info("Checking for duplicate events...")

    with client.get_connection() as conn:
        # Count duplicates before cleanup
        cursor = conn.execute("""
            SELECT COUNT(*) FROM claude_raw_traces
            WHERE sequence NOT IN (
                SELECT MIN(sequence)
                FROM claude_raw_traces
                GROUP BY external_id, uuid
            )
        """)
        duplicate_count = cursor.fetchone()[0]

        if duplicate_count == 0:
            logger.info("No duplicates found!")
            return 0

        logger.info(f"Found {duplicate_count} duplicate events")

        # Remove duplicates
        logger.info("Removing duplicates (keeping first occurrence)...")
        conn.execute("""
            DELETE FROM claude_raw_traces
            WHERE sequence NOT IN (
                SELECT MIN(sequence)
                FROM claude_raw_traces
                GROUP BY external_id, uuid
            )
        """)
        conn.commit()

        logger.info(f"Removed {duplicate_count} duplicate events")

        # Vacuum to reclaim space
        logger.info("Running VACUUM to reclaim disk space...")
        conn.execute("VACUUM")

        logger.info("Cleanup complete!")
        return duplicate_count


def add_unique_constraint(client: SQLiteClient) -> bool:
    """
    Add UNIQUE index on (external_id, uuid) to prevent duplicates.

    Args:
        client: SQLiteClient instance

    Returns:
        True if constraint was added, False if it already exists
    """
    logger.info("Checking for existing UNIQUE constraint...")

    with client.get_connection() as conn:
        # Check if the unique index already exists
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index'
            AND name='idx_claude_unique_event'
        """)

        if cursor.fetchone():
            logger.info("UNIQUE constraint already exists (idx_claude_unique_event)")
            return False

        # Add the unique index
        logger.info("Adding UNIQUE constraint on (external_id, uuid)...")
        try:
            conn.execute("""
                CREATE UNIQUE INDEX idx_claude_unique_event
                ON claude_raw_traces(external_id, uuid)
            """)
            conn.commit()
            logger.info("✓ UNIQUE constraint added successfully!")
            return True
        except Exception as e:
            logger.error(f"Failed to add UNIQUE constraint: {e}")
            logger.error("This may happen if there are still duplicate events.")
            logger.error("Try running with --cleanup-duplicates flag first.")
            raise


def main():
    parser = argparse.ArgumentParser(
        description="Add UNIQUE constraint to claude_raw_traces table"
    )
    parser.add_argument(
        '--cleanup-duplicates',
        action='store_true',
        help='Remove duplicate events before adding constraint'
    )
    parser.add_argument(
        '--db-path',
        type=str,
        default=str(Path.home() / ".blueplane" / "telemetry.db"),
        help='Path to telemetry database (default: ~/.blueplane/telemetry.db)'
    )

    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        logger.error("Please run init_database.py first")
        sys.exit(1)

    logger.info(f"Using database: {db_path}")

    # Connect to database
    client = SQLiteClient(str(db_path))

    try:
        # Cleanup duplicates if requested
        if args.cleanup_duplicates:
            duplicates_removed = cleanup_duplicates(client)
            logger.info(f"Cleanup summary: {duplicates_removed} duplicates removed")

        # Add unique constraint
        constraint_added = add_unique_constraint(client)

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("Migration complete!")
        logger.info("=" * 60)

        if args.cleanup_duplicates:
            logger.info(f"✓ Removed {duplicates_removed} duplicate events")

        if constraint_added:
            logger.info("✓ Added UNIQUE constraint on (external_id, uuid)")
            logger.info("")
            logger.info("Future duplicate events will be rejected automatically.")
        else:
            logger.info("✓ UNIQUE constraint already exists")

        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
