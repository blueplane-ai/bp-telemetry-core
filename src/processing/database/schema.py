# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Database schema definitions and migrations for Blueplane Telemetry Core.

Creates tables for raw traces, conversations, and related data structures.
"""

import logging
from typing import Optional

from .sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)

# Schema version for migrations
SCHEMA_VERSION = 1


def create_raw_traces_table(client: SQLiteClient) -> None:
    """
    Create raw_traces table for storing compressed event data.

    Args:
        client: SQLiteClient instance
    """
    sql = """
    CREATE TABLE IF NOT EXISTS raw_traces (
        -- Core identification
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        -- Event metadata (indexed fields)
        event_id TEXT NOT NULL,
        session_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        platform TEXT NOT NULL,
        timestamp TIMESTAMP NOT NULL,

        -- Context fields
        workspace_hash TEXT,
        model TEXT,
        tool_name TEXT,

        -- Metrics (for fast filtering)
        duration_ms INTEGER,
        tokens_used INTEGER,
        lines_added INTEGER,
        lines_removed INTEGER,

        -- Compressed payload (zlib level 6, achieves 7-10x compression)
        event_data BLOB NOT NULL,

        -- Generated columns for partitioning
        event_date DATE GENERATED ALWAYS AS (DATE(timestamp)),
        event_hour INTEGER GENERATED ALWAYS AS (CAST(strftime('%H', timestamp) AS INTEGER))
    );
    """
    client.execute(sql)
    logger.info("Created raw_traces table")


def create_conversations_table(client: SQLiteClient) -> None:
    """
    Create conversations table for structured conversation data.

    Args:
        client: SQLiteClient instance
    """
    sql = """
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        external_session_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        workspace_hash TEXT,
        started_at TIMESTAMP NOT NULL,
        ended_at TIMESTAMP,

        -- JSON fields
        context TEXT DEFAULT '{}',
        metadata TEXT DEFAULT '{}',
        tool_sequence TEXT DEFAULT '[]',
        acceptance_decisions TEXT DEFAULT '[]',

        -- Metrics
        interaction_count INTEGER DEFAULT 0,
        acceptance_rate REAL,
        total_tokens INTEGER DEFAULT 0,
        total_changes INTEGER DEFAULT 0,

        UNIQUE(external_session_id, platform)
    );
    """
    client.execute(sql)
    logger.info("Created conversations table")


def create_conversation_turns_table(client: SQLiteClient) -> None:
    """
    Create conversation_turns table for individual conversation turns.

    Args:
        client: SQLiteClient instance
    """
    sql = """
    CREATE TABLE IF NOT EXISTS conversation_turns (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id),
        turn_number INTEGER NOT NULL,
        timestamp TIMESTAMP NOT NULL,
        turn_type TEXT CHECK (turn_type IN ('user_prompt', 'assistant_response', 'tool_use')),

        content_hash TEXT,
        metadata TEXT DEFAULT '{}',
        tokens_used INTEGER,
        latency_ms INTEGER,
        tools_called TEXT,

        UNIQUE(conversation_id, turn_number)
    );
    """
    client.execute(sql)
    logger.info("Created conversation_turns table")


def create_code_changes_table(client: SQLiteClient) -> None:
    """
    Create code_changes table for tracking file modifications.

    Args:
        client: SQLiteClient instance
    """
    sql = """
    CREATE TABLE IF NOT EXISTS code_changes (
        id TEXT PRIMARY KEY,
        conversation_id TEXT NOT NULL REFERENCES conversations(id),
        turn_id TEXT REFERENCES conversation_turns(id),
        timestamp TIMESTAMP NOT NULL,

        file_extension TEXT,
        operation TEXT CHECK (operation IN ('create', 'edit', 'delete', 'read')),
        lines_added INTEGER DEFAULT 0,
        lines_removed INTEGER DEFAULT 0,

        accepted BOOLEAN,
        acceptance_delay_ms INTEGER,
        revision_count INTEGER DEFAULT 0
    );
    """
    client.execute(sql)
    logger.info("Created code_changes table")


def create_session_mappings_table(client: SQLiteClient) -> None:
    """
    Create session_mappings table for mapping external to internal session IDs.

    Args:
        client: SQLiteClient instance
    """
    sql = """
    CREATE TABLE IF NOT EXISTS session_mappings (
        external_id TEXT PRIMARY KEY,
        internal_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(external_id, platform)
    );
    """
    client.execute(sql)
    logger.info("Created session_mappings table")


def create_trace_stats_table(client: SQLiteClient) -> None:
    """
    Create trace_stats table for pre-computed daily aggregations.

    Args:
        client: SQLiteClient instance
    """
    sql = """
    CREATE TABLE IF NOT EXISTS trace_stats (
        stat_date DATE PRIMARY KEY,
        total_events INTEGER NOT NULL,
        unique_sessions INTEGER NOT NULL,
        event_types TEXT NOT NULL,
        platform_breakdown TEXT NOT NULL,
        error_count INTEGER DEFAULT 0,
        avg_duration_ms REAL,
        total_tokens INTEGER DEFAULT 0,
        computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    client.execute(sql)
    logger.info("Created trace_stats table")


def create_indexes(client: SQLiteClient) -> None:
    """
    Create indexes for common query patterns.

    Args:
        client: SQLiteClient instance
    """
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_session_time ON raw_traces(session_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_event_type_time ON raw_traces(event_type, timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_date_hour ON raw_traces(event_date, event_hour);",
        "CREATE INDEX IF NOT EXISTS idx_timestamp ON raw_traces(timestamp DESC);",
        "CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);",
        "CREATE INDEX IF NOT EXISTS idx_conv_platform_time ON conversations(platform, started_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_turn_conv ON conversation_turns(conversation_id, turn_number);",
        "CREATE INDEX IF NOT EXISTS idx_changes_conv ON code_changes(conversation_id);",
        "CREATE INDEX IF NOT EXISTS idx_changes_accepted ON code_changes(accepted, timestamp);",
    ]

    for index_sql in indexes:
        client.execute(index_sql)

    logger.info("Created database indexes")


def create_schema(client: SQLiteClient) -> None:
    """
    Create all database tables and indexes.

    Args:
        client: SQLiteClient instance
    """
    logger.info("Creating database schema...")

    # Create tables
    create_raw_traces_table(client)
    create_conversations_table(client)
    create_conversation_turns_table(client)
    create_code_changes_table(client)
    create_session_mappings_table(client)
    create_trace_stats_table(client)

    # Create indexes
    create_indexes(client)

    logger.info("Database schema created successfully")


def get_schema_version(client: SQLiteClient) -> Optional[int]:
    """
    Get current schema version from database.

    Args:
        client: SQLiteClient instance

    Returns:
        Schema version number or None if not set
    """
    try:
        # Check if schema_version table exists
        with client.get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            if not cursor.fetchone():
                return None

            cursor = conn.execute("SELECT version FROM schema_version LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.warning(f"Could not get schema version: {e}")
        return None


def migrate_schema(client: SQLiteClient, from_version: int, to_version: int) -> None:
    """
    Migrate database schema from one version to another.

    Args:
        client: SQLiteClient instance
        from_version: Current schema version
        to_version: Target schema version
    """
    logger.info(f"Migrating schema from version {from_version} to {to_version}")

    # Create schema_version table if it doesn't exist
    client.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );
        """
    )

    # For now, just recreate schema (future: add incremental migrations)
    if from_version < to_version:
        create_schema(client)
        client.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (to_version,))
        logger.info(f"Schema migrated to version {to_version}")

