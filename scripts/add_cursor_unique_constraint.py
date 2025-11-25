#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Migration script to add UNIQUE constraint on cursor_raw_traces(event_id).

This prevents duplicate Cursor events from being inserted into the database.
Run this after cleaning up existing duplicates.

Usage:
    python scripts/add_cursor_unique_constraint.py [--cleanup-duplicates]

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
    logger.info("Checking for duplicate Cursor events...")

    with client.get_connection() as conn:
        # Count duplicates before cleanup
        cursor = conn.execute("""
            SELECT COUNT(*) FROM cursor_raw_traces
            WHERE sequence NOT IN (
                SELECT MIN(sequence)
                FROM cursor_raw_traces
                GROUP BY event_id
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
            DELETE FROM cursor_raw_traces
            WHERE sequence NOT IN (
                SELECT MIN(sequence)
                FROM cursor_raw_traces
                GROUP BY event_id
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
    Add UNIQUE index on event_id to prevent duplicates.

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
            AND name='idx_cursor_unique_event'
        """)

        if cursor.fetchone():
            logger.info("UNIQUE constraint already exists (idx_cursor_unique_event)")
            return False

        # Add the unique index
        logger.info("Adding UNIQUE constraint on event_id...")
        try:
            conn.execute("""
                CREATE UNIQUE INDEX idx_cursor_unique_event
                ON cursor_raw_traces(event_id)
            """)
            conn.commit()
            logger.info("✓ UNIQUE constraint added successfully!")
            return True
        except Exception as e:
            logger.error(f"Failed to add UNIQUE constraint: {e}")
            logger.error("This may happen if there are still duplicate events.")
            logger.error("Try running with --cleanup-duplicates flag first.")
            raise


def get_statistics(client: SQLiteClient) -> dict:
    """
    Get statistics about Cursor raw traces.

    Args:
        client: SQLiteClient instance

    Returns:
        Dictionary with statistics
    """
    with client.get_connection() as conn:
        cursor = conn.execute("""
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT event_id) as unique_events,
                ROUND(CAST(COUNT(*) AS FLOAT) / NULLIF(COUNT(DISTINCT event_id), 0), 2) as avg_duplication
            FROM cursor_raw_traces
        """)
        row = cursor.fetchone()
        return {
            'total_rows': row[0],
            'unique_events': row[1],
            'avg_duplication': row[2] or 1.0
        }


def main():
    parser = argparse.ArgumentParser(
        description="Add UNIQUE constraint to cursor_raw_traces table"
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
        # Get initial statistics
        logger.info("")
        logger.info("=" * 60)
        logger.info("Initial Statistics")
        logger.info("=" * 60)
        stats = get_statistics(client)
        logger.info(f"Total rows: {stats['total_rows']}")
        logger.info(f"Unique events: {stats['unique_events']}")
        logger.info(f"Duplication rate: {stats['avg_duplication']}x")
        logger.info("")

        # Cleanup duplicates if requested
        duplicates_removed = 0
        if args.cleanup_duplicates:
            duplicates_removed = cleanup_duplicates(client)

            # Get post-cleanup statistics
            logger.info("")
            logger.info("=" * 60)
            logger.info("Post-Cleanup Statistics")
            logger.info("=" * 60)
            stats = get_statistics(client)
            logger.info(f"Total rows: {stats['total_rows']}")
            logger.info(f"Unique events: {stats['unique_events']}")
            logger.info(f"Duplication rate: {stats['avg_duplication']}x")
            logger.info("")

        # Add unique constraint
        constraint_added = add_unique_constraint(client)

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("Migration Complete!")
        logger.info("=" * 60)

        if args.cleanup_duplicates:
            logger.info(f"✓ Removed {duplicates_removed} duplicate events")

        if constraint_added:
            logger.info("✓ Added UNIQUE constraint on event_id")
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
