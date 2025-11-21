# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Database schema definitions and migrations for Blueplane Telemetry Core.

Creates tables for raw traces, conversations, and related data structures.
"""

import hashlib
import logging
from typing import Optional

from .sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)

# Schema version for migrations
SCHEMA_VERSION = 2


def create_cursor_sessions_table(client: SQLiteClient) -> None:
    """
    Create cursor_sessions table for Cursor IDE window sessions.

    Only Cursor has sessions (IDE window instances). Claude Code has no session concept.

    Args:
        client: SQLiteClient instance
    """
    sql = """
    CREATE TABLE IF NOT EXISTS cursor_sessions (
        id TEXT PRIMARY KEY,
        external_session_id TEXT NOT NULL UNIQUE,
        workspace_hash TEXT NOT NULL,
        workspace_name TEXT,
        workspace_path TEXT,
        started_at TIMESTAMP NOT NULL,
        ended_at TIMESTAMP,
        metadata TEXT DEFAULT '{}'
    );
    """
    client.execute(sql)
    
    # Create indexes
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_cursor_sessions_workspace ON cursor_sessions(workspace_hash);",
        "CREATE INDEX IF NOT EXISTS idx_cursor_sessions_time ON cursor_sessions(started_at DESC);",
        "CREATE INDEX IF NOT EXISTS idx_cursor_sessions_external ON cursor_sessions(external_session_id);",
    ]
    
    for index_sql in indexes:
        client.execute(index_sql)
    
    logger.info("Created cursor_sessions table")


def create_conversations_table(client: SQLiteClient) -> None:
    """
    Create conversations table for structured conversation data.

    Schema supports both platforms:
    - Claude Code: session_id is NULL (no session concept)
    - Cursor: session_id references cursor_sessions.id

    Args:
        client: SQLiteClient instance
    """
    sql = """
    CREATE TABLE IF NOT EXISTS conversations (
        id TEXT PRIMARY KEY,
        session_id TEXT,
        external_id TEXT NOT NULL,
        platform TEXT NOT NULL,
        workspace_hash TEXT,
        workspace_name TEXT,
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

        -- Foreign key constraint (only enforced when session_id IS NOT NULL)
        FOREIGN KEY (session_id) REFERENCES cursor_sessions(id),
        
        -- Data integrity constraint
        CHECK (
            (platform = 'cursor' AND session_id IS NOT NULL) OR
            (platform = 'claude_code' AND session_id IS NULL)
        ),
        
        UNIQUE(external_id, platform)
    );
    """
    client.execute(sql)
    
    # Add workspace_name column to existing tables (migration)
    try:
        client.execute("ALTER TABLE conversations ADD COLUMN workspace_name TEXT")
        logger.info("Added workspace_name column to conversations table")
    except Exception as e:
        # Column already exists or table doesn't exist yet - that's fine
        if "duplicate column name" not in str(e).lower():
            logger.debug(f"Could not add workspace_name column (may already exist): {e}")
    
    logger.info("Created conversations table")


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


def create_claude_raw_traces_table(client: SQLiteClient) -> None:
    """
    Create claude_raw_traces table for Claude Code JSONL events.

    This table stores all events from Claude Code JSONL files with:
    - Indexed fields for common queries
    - Full event data compressed with zlib
    - Platform-specific fields (uuid, parentUuid, requestId, agentId)
    - Support for both main session and agent (Task tool) files

    Args:
        client: SQLiteClient instance
    """
    sql = """
    CREATE TABLE IF NOT EXISTS claude_raw_traces (
        -- Primary key and metadata
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        -- Event identification (indexed)
        event_id TEXT NOT NULL,
        external_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        platform TEXT NOT NULL DEFAULT 'claude_code',
        timestamp TIMESTAMP NOT NULL,

        -- Claude-specific identifiers
        uuid TEXT,
        parent_uuid TEXT,
        request_id TEXT,
        agent_id TEXT,

        -- Context fields
        workspace_hash TEXT,
        project_name TEXT,
        is_sidechain BOOLEAN DEFAULT 0,
        user_type TEXT,
        cwd TEXT,
        version TEXT,
        git_branch TEXT,

        -- Message fields (user/assistant events)
        message_role TEXT,
        message_model TEXT,
        message_id TEXT,
        message_type TEXT,
        stop_reason TEXT,
        stop_sequence TEXT,

        -- Token usage fields
        input_tokens INTEGER,
        cache_creation_input_tokens INTEGER,
        cache_read_input_tokens INTEGER,
        output_tokens INTEGER,
        service_tier TEXT,
        cache_5m_tokens INTEGER,
        cache_1h_tokens INTEGER,

        -- Queue operation fields
        operation TEXT,

        -- System event fields
        subtype TEXT,
        level TEXT,
        is_meta BOOLEAN DEFAULT 0,

        -- Summary fields
        summary TEXT,
        leaf_uuid TEXT,

        -- Derived metrics
        duration_ms INTEGER,
        tokens_used INTEGER,
        tool_calls_count INTEGER,

        -- Compressed full event (zlib level 6)
        event_data BLOB NOT NULL,

        -- Generated columns for partitioning
        event_date DATE GENERATED ALWAYS AS (DATE(timestamp)),
        event_hour INTEGER GENERATED ALWAYS AS (CAST(strftime('%H', timestamp) AS INTEGER))
    );
    """
    client.execute(sql)
    
    # Migrate existing table: rename session_id to external_id if needed
    with client.get_connection() as conn:
        cursor = conn.execute("PRAGMA table_info(claude_raw_traces)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'session_id' in columns and 'external_id' not in columns:
            logger.info("Migrating claude_raw_traces: session_id -> external_id")
            try:
                # SQLite 3.25.0+ supports RENAME COLUMN
                conn.execute("ALTER TABLE claude_raw_traces RENAME COLUMN session_id TO external_id")
                
                # Drop old indexes that reference session_id
                conn.execute("DROP INDEX IF EXISTS idx_claude_session_time")
                conn.execute("DROP INDEX IF EXISTS idx_claude_sidechain")
                
                # Recreate indexes with external_id
                conn.execute("CREATE INDEX IF NOT EXISTS idx_claude_session_time ON claude_raw_traces(external_id, timestamp);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_claude_sidechain ON claude_raw_traces(is_sidechain, external_id);")
                
                conn.commit()
                logger.info("Migration complete: claude_raw_traces.session_id -> external_id")
            except Exception as e:
                # If RENAME COLUMN is not supported, log warning
                logger.warning(
                    f"Could not migrate claude_raw_traces.session_id to external_id: {e}. "
                    f"SQLite 3.25.0+ required for RENAME COLUMN. "
                    f"Please recreate the table or upgrade SQLite."
                )
                conn.rollback()
    
    logger.info("Created claude_raw_traces table")


def create_claude_jsonl_offsets_table(client: SQLiteClient) -> None:
    """
    Create claude_jsonl_offsets table for persisted JSONL file offsets.

    Args:
        client: SQLiteClient instance
    """
    sql = """
    CREATE TABLE IF NOT EXISTS claude_jsonl_offsets (
        file_path TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        agent_id TEXT,
        line_offset INTEGER NOT NULL,
        last_size INTEGER NOT NULL,
        last_mtime REAL NOT NULL,
        last_read_time REAL NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    client.execute(sql)
    client.execute("CREATE INDEX IF NOT EXISTS idx_claude_offset_session ON claude_jsonl_offsets(session_id);")
    client.execute("CREATE INDEX IF NOT EXISTS idx_claude_offset_agent ON claude_jsonl_offsets(agent_id);")
    logger.info("Created claude_jsonl_offsets table")


def create_cursor_raw_traces_table(client: SQLiteClient) -> None:
    """
    Create cursor_raw_traces table for Cursor telemetry events.

    This table captures ALL Cursor database events including:
    - AI generations and prompts
    - Composer data with nested bubbles
    - Background composer data
    - Agent mode exit info
    - Interactive sessions
    - History entries

    Args:
        client: SQLiteClient instance
    """
    sql = """
    CREATE TABLE IF NOT EXISTS cursor_raw_traces (
        -- Primary key and ingestion metadata
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

        -- Event identification (indexed for queries)
        event_id TEXT NOT NULL,
        external_session_id TEXT,
        event_type TEXT NOT NULL,
        timestamp TIMESTAMP NOT NULL,

        -- Source location metadata
        storage_level TEXT NOT NULL,
        workspace_hash TEXT NOT NULL,
        database_table TEXT NOT NULL,
        item_key TEXT NOT NULL,

        -- AI Service fields
        generation_uuid TEXT,
        generation_type TEXT,
        command_type TEXT,

        -- Composer/Bubble fields
        composer_id TEXT,
        bubble_id TEXT,
        server_bubble_id TEXT,
        message_type INTEGER,
        is_agentic BOOLEAN,

        -- Content fields
        text_description TEXT,
        raw_text TEXT,
        rich_text TEXT,

        -- Timing fields (milliseconds)
        unix_ms INTEGER,
        created_at INTEGER,
        last_updated_at INTEGER,
        completed_at INTEGER,
        client_start_time INTEGER,
        client_end_time INTEGER,

        -- Metrics fields
        lines_added INTEGER,
        lines_removed INTEGER,
        token_count_up_until_here INTEGER,

        -- Capability/Tool fields
        capabilities_ran TEXT,
        capability_statuses TEXT,

        -- Context fields
        project_name TEXT,
        relevant_files TEXT,
        selections TEXT,

        -- Status fields
        is_archived BOOLEAN,
        has_unread_messages BOOLEAN,

        -- Full event payload (compressed)
        event_data BLOB NOT NULL,

        -- Partitioning columns (generated)
        event_date DATE GENERATED ALWAYS AS (DATE(timestamp)),
        event_hour INTEGER GENERATED ALWAYS AS (CAST(strftime('%H', timestamp) AS INTEGER))
    );
    """
    client.execute(sql)
    logger.info("Created cursor_raw_traces table")


def create_cursor_indexes(client: SQLiteClient) -> None:
    """
    Create indexes for Cursor raw traces.

    Args:
        client: SQLiteClient instance
    """
    indexes = [
        # Primary query patterns
        "CREATE INDEX IF NOT EXISTS idx_cursor_session_time ON cursor_raw_traces(external_session_id, timestamp) WHERE external_session_id IS NOT NULL;",
        "CREATE INDEX IF NOT EXISTS idx_cursor_event_type_time ON cursor_raw_traces(event_type, timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_cursor_workspace ON cursor_raw_traces(workspace_hash, timestamp);",

        # Generation and composer lookups
        "CREATE INDEX IF NOT EXISTS idx_cursor_generation ON cursor_raw_traces(generation_uuid) WHERE generation_uuid IS NOT NULL;",
        "CREATE INDEX IF NOT EXISTS idx_cursor_composer ON cursor_raw_traces(composer_id, timestamp) WHERE composer_id IS NOT NULL;",
        "CREATE INDEX IF NOT EXISTS idx_cursor_bubble ON cursor_raw_traces(bubble_id) WHERE bubble_id IS NOT NULL;",

        # Storage key lookups
        "CREATE INDEX IF NOT EXISTS idx_cursor_storage_key ON cursor_raw_traces(storage_level, database_table, item_key);",

        # Time-based partitioning
        "CREATE INDEX IF NOT EXISTS idx_cursor_date_hour ON cursor_raw_traces(event_date, event_hour);",
        "CREATE INDEX IF NOT EXISTS idx_cursor_unix_ms ON cursor_raw_traces(unix_ms DESC) WHERE unix_ms IS NOT NULL;",
    ]

    for index_sql in indexes:
        client.execute(index_sql)

    logger.info("Created Cursor indexes")


def create_claude_indexes(client: SQLiteClient) -> None:
    """
    Create indexes for Claude Code raw traces.

    Args:
        client: SQLiteClient instance
    """
    indexes = [
        # Primary query patterns
        "CREATE INDEX IF NOT EXISTS idx_claude_session_time ON claude_raw_traces(external_id, timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_claude_event_type_time ON claude_raw_traces(event_type, timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_claude_project_name ON claude_raw_traces(project_name);",

        # UUID lookups for threading
        "CREATE INDEX IF NOT EXISTS idx_claude_uuid ON claude_raw_traces(uuid);",
        "CREATE INDEX IF NOT EXISTS idx_claude_parent_uuid ON claude_raw_traces(parent_uuid);",

        # API request tracking
        "CREATE INDEX IF NOT EXISTS idx_claude_request_id ON claude_raw_traces(request_id);",

        # Model analysis
        "CREATE INDEX IF NOT EXISTS idx_claude_message_model ON claude_raw_traces(message_model);",

        # Time-based partitioning
        "CREATE INDEX IF NOT EXISTS idx_claude_date_hour ON claude_raw_traces(event_date, event_hour);",
        "CREATE INDEX IF NOT EXISTS idx_claude_timestamp ON claude_raw_traces(timestamp DESC);",

        # Agent tracking
        "CREATE INDEX IF NOT EXISTS idx_claude_agent_id ON claude_raw_traces(agent_id);",
        "CREATE INDEX IF NOT EXISTS idx_claude_sidechain ON claude_raw_traces(is_sidechain, external_id);",
    ]

    for index_sql in indexes:
        client.execute(index_sql)

    logger.info("Created Claude Code indexes")


def create_indexes(client: SQLiteClient) -> None:
    """
    Create indexes for common query patterns.

    Args:
        client: SQLiteClient instance
    """
    # Check if conversations table has new schema (external_id) or old schema (external_session_id)
    has_new_schema = True
    try:
        with client.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(conversations)")
            columns = [row[1] for row in cursor.fetchall()]
            conversations_columns = columns.copy()
            conversations_columns = columns.copy()
            if 'external_session_id' in columns and 'external_id' not in columns:
                has_new_schema = False
    except Exception:
        # Table doesn't exist yet, will be created with new schema
        pass
    
    indexes = []

    # Only create conversation indexes if table has new schema
    if has_new_schema:
        indexes.extend([
            # Partial index for Cursor conversations (session_id is NULL for Claude)
            "CREATE INDEX IF NOT EXISTS idx_conversations_session_cursor ON conversations(session_id) WHERE platform = 'cursor';",
            "CREATE INDEX IF NOT EXISTS idx_conversations_external ON conversations(external_id, platform);",
            "CREATE INDEX IF NOT EXISTS idx_conv_platform_time ON conversations(platform, started_at DESC);",
            # Index for Claude Code session recovery (active sessions query)
            "CREATE INDEX IF NOT EXISTS idx_conv_platform_active ON conversations(platform, ended_at) WHERE ended_at IS NULL;",
            "CREATE INDEX IF NOT EXISTS idx_conv_platform_started ON conversations(platform, started_at);",
            "CREATE INDEX IF NOT EXISTS idx_conversations_workspace ON conversations(workspace_hash) WHERE workspace_hash IS NOT NULL;",
        ])
    else:
        # Old schema indexes (for backward compatibility during migration)
        indexes.extend([
            "CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);",
            "CREATE INDEX IF NOT EXISTS idx_conv_platform_time ON conversations(platform, started_at DESC);",
        ])
    

    for index_sql in indexes:
        try:
            client.execute(index_sql)
        except Exception as e:
            # Log but don't fail - index creation is best effort
            logger.debug(f"Could not create index: {e}")

    logger.info("Created database indexes")


def create_schema(client: SQLiteClient) -> None:
    """
    Create all database tables and indexes.

    Args:
        client: SQLiteClient instance
    """
    logger.info("Creating database schema...")

    # Create tables (cursor_sessions must be created before conversations due to FK)
    create_claude_raw_traces_table(client)
    create_claude_jsonl_offsets_table(client)
    create_cursor_raw_traces_table(client)
    create_cursor_sessions_table(client)
    create_conversations_table(client)
    create_trace_stats_table(client)

    # Create indexes
    create_indexes(client)
    create_claude_indexes(client)
    create_cursor_indexes(client)

    logger.info("Database schema created successfully")


def detect_schema_version(client: SQLiteClient) -> Optional[int]:
    """
    Detect current schema version.
    
    Returns:
        Schema version number, or None if not versioned
    """
    try:
        version = get_schema_version(client)
        if version is not None:
            return version
        
        # Check if database has old schema (unversioned)
        with client.get_connection() as conn:
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='conversations'
            """)
            if not cursor.fetchone():
                # No conversations table - new database
                return None
            
            # Check for old schema columns
            cursor = conn.execute("PRAGMA table_info(conversations)")
            columns = {row[1] for row in cursor.fetchall()}
            
            if 'external_session_id' in columns and 'external_id' not in columns:
                # Old schema detected - assume version 1
                return 1
        
        return None
    except Exception as e:
        logger.debug(f"Error detecting schema version: {e}")
        return None


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

    # Incremental migrations
    if from_version < to_version:
        if from_version < 2:
            migrate_to_v2(client)
            from_version = 2
        
        # Future migrations can be added here
        # if from_version < 3:
        #     migrate_to_v3(client)
        #     from_version = 3
        
        client.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (to_version,))
        logger.info(f"Schema migrated to version {to_version}")


def migrate_to_v2(client: SQLiteClient) -> None:
    """
    Migrate schema to version 2: Add cursor_sessions table and update conversations table.
    
    Migration steps:
    1. Create cursor_sessions table
    2. Migrate existing Cursor sessions from conversations to cursor_sessions
    3. Create new conversations table with updated schema
    4. Migrate conversation data with updated references
    5. Create new indexes
    
    Args:
        client: SQLiteClient instance
    """
    logger.info("Starting migration to schema version 2...")
    
    import json
    import uuid
    from datetime import datetime, timezone
    
    try:
        with client.get_connection() as conn:
            # Enable foreign keys
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Step 1: Create cursor_sessions table
            logger.info("Step 1: Creating cursor_sessions table...")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cursor_sessions (
                    id TEXT PRIMARY KEY,
                    external_session_id TEXT NOT NULL UNIQUE,
                    workspace_hash TEXT NOT NULL,
                    workspace_name TEXT,
                    workspace_path TEXT,
                    started_at TIMESTAMP NOT NULL,
                    ended_at TIMESTAMP,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            
            # Create cursor_sessions indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cursor_sessions_workspace ON cursor_sessions(workspace_hash);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cursor_sessions_time ON cursor_sessions(started_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cursor_sessions_external ON cursor_sessions(external_session_id);")
            
            # Step 2: Check if conversations table exists and has old schema
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='conversations'
            """)
            table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                # Table doesn't exist, just create new schema
                logger.info("Conversations table doesn't exist, creating new schema...")
                conn.execute("""
                    CREATE TABLE conversations (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        external_id TEXT NOT NULL,
                        platform TEXT NOT NULL,
                        workspace_hash TEXT,
                        workspace_name TEXT,
                        started_at TIMESTAMP NOT NULL,
                        ended_at TIMESTAMP,
                        context TEXT DEFAULT '{}',
                        metadata TEXT DEFAULT '{}',
                        tool_sequence TEXT DEFAULT '[]',
                        acceptance_decisions TEXT DEFAULT '[]',
                        interaction_count INTEGER DEFAULT 0,
                        acceptance_rate REAL,
                        total_tokens INTEGER DEFAULT 0,
                        total_changes INTEGER DEFAULT 0,
                        FOREIGN KEY (session_id) REFERENCES cursor_sessions(id),
                        CHECK (
                            (platform = 'cursor' AND session_id IS NOT NULL) OR
                            (platform = 'claude_code' AND session_id IS NULL)
                        ),
                        UNIQUE(external_id, platform)
                    )
                """)
                conn.commit()
                logger.info("Migration to v2 complete (new database)")
                return
            
            # Check if migration already done (check for external_id column)
            cursor = conn.execute("PRAGMA table_info(conversations)")
            columns = [row[1] for row in cursor.fetchall()]
            conversations_columns = columns.copy()
            has_external_id = 'external_id' in columns
            has_external_session_id = 'external_session_id' in columns
            
            if has_external_id and not has_external_session_id:
                logger.info("Schema already migrated to v2, skipping migration")
                return
            
            if not has_external_session_id:
                logger.warning("Conversations table exists but doesn't have expected columns, creating new schema")
                conn.execute("DROP TABLE IF EXISTS conversations")
                conn.execute("""
                    CREATE TABLE conversations (
                        id TEXT PRIMARY KEY,
                        session_id TEXT,
                        external_id TEXT NOT NULL,
                        platform TEXT NOT NULL,
                        workspace_hash TEXT,
                        workspace_name TEXT,
                        started_at TIMESTAMP NOT NULL,
                        ended_at TIMESTAMP,
                        context TEXT DEFAULT '{}',
                        metadata TEXT DEFAULT '{}',
                        tool_sequence TEXT DEFAULT '[]',
                        acceptance_decisions TEXT DEFAULT '[]',
                        interaction_count INTEGER DEFAULT 0,
                        acceptance_rate REAL,
                        total_tokens INTEGER DEFAULT 0,
                        total_changes INTEGER DEFAULT 0,
                        FOREIGN KEY (session_id) REFERENCES cursor_sessions(id),
                        CHECK (
                            (platform = 'cursor' AND session_id IS NOT NULL) OR
                            (platform = 'claude_code' AND session_id IS NULL)
                        ),
                        UNIQUE(external_id, platform)
                    )
                """)
                conn.commit()
                logger.info("Migration to v2 complete (recreated table)")
                return
            
            # Step 3: Migrate Cursor sessions from conversations to cursor_sessions
            logger.info("Step 2: Migrating Cursor sessions...")
            
            # First, verify we have Cursor conversations
            cursor = conn.execute("""
                SELECT COUNT(*) FROM conversations WHERE platform = 'cursor'
            """)
            cursor_count = cursor.fetchone()[0]
            logger.info(f"Found {cursor_count} Cursor conversations to process")
            
            if cursor_count == 0:
                logger.info("No Cursor conversations found, skipping session migration")
                session_mapping = {}
            else:
                # Use window function to pick earliest session per external_session_id
                # This handles duplicates by selecting the first occurrence
                has_workspace_hash_col = 'workspace_hash' in conversations_columns
                has_workspace_name_col = 'workspace_name' in conversations_columns
                has_ended_at_col = 'ended_at' in conversations_columns
                has_context_col = 'context' in conversations_columns

                workspace_hash_expr = (
                    "workspace_hash AS workspace_hash" if has_workspace_hash_col else "NULL AS workspace_hash"
                )
                workspace_name_expr = (
                    "workspace_name AS workspace_name" if has_workspace_name_col else "NULL AS workspace_name"
                )
                ended_at_expr = "ended_at AS ended_at" if has_ended_at_col else "NULL AS ended_at"
                workspace_path_expr = (
                    "json_extract(context, '$.workspace_path') AS workspace_path"
                    if has_context_col else "NULL AS workspace_path"
                )
                workspace_hash_order = "workspace_hash" if has_workspace_hash_col else "external_session_id"

                ranked_query = f"""
                    WITH ranked_sessions AS (
                        SELECT 
                            external_session_id,
                            {workspace_hash_expr},
                            {workspace_name_expr},
                            started_at,
                            {ended_at_expr},
                            {workspace_path_expr},
                            ROW_NUMBER() OVER (
                                PARTITION BY external_session_id 
                                ORDER BY started_at ASC, {workspace_hash_order} ASC
                            ) as rn
                        FROM conversations
                        WHERE platform = 'cursor'
                          AND external_session_id IS NOT NULL
                          AND external_session_id != ''
                    )
                    SELECT 
                        external_session_id,
                        workspace_hash,
                        workspace_name,
                        started_at,
                        ended_at,
                        workspace_path
                    FROM ranked_sessions
                    WHERE rn = 1
                """
                cursor = conn.execute(ranked_query)
                
                session_mapping = {}  # external_session_id -> {"internal_id": uuid, "workspace_hash": str}
                cursor_sessions_data = []
                
                for row in cursor.fetchall():
                    external_session_id = row[0]
                    workspace_hash = (row[1] or '').strip()
                    workspace_name = row[2]
                    started_at = row[3]
                    ended_at = row[4]
                    workspace_path = (row[5] or '').strip()
                    
                    # Validate we have required fields
                    if not external_session_id:
                        logger.warning(
                            "Skipping Cursor session with missing external_session_id during migration"
                        )
                        continue
                    
                    workspace_hash_source = "existing"
                    original_workspace_hash = workspace_hash

                    if not workspace_hash:
                        if workspace_path:
                            workspace_hash = hashlib.sha256(workspace_path.encode()).hexdigest()[:16]
                            workspace_hash_source = "workspace_path"
                        else:
                            # Fall back to hashing the external session ID to ensure determinism
                            workspace_hash = hashlib.sha256(external_session_id.encode()).hexdigest()[:16]
                            workspace_hash_source = "external_session_id"
                        
                        logger.info(
                            "Inferred workspace_hash for session %s using %s",
                            external_session_id,
                            workspace_hash_source
                        )
                    
                    # Check for duplicates before inserting
                    if external_session_id in session_mapping:
                        logger.warning(
                            f"Duplicate external_session_id detected: {external_session_id}. "
                            f"Using first occurrence."
                        )
                        continue
                    
                    # Generate new internal session ID
                    internal_session_id = str(uuid.uuid4())
                    session_mapping[external_session_id] = {
                        "internal_id": internal_session_id,
                        "workspace_hash": workspace_hash
                    }
                    
                    metadata = {
                        'migrated': True,
                        'migration_date': datetime.now(timezone.utc).isoformat(),
                        'workspace_hash_source': workspace_hash_source,
                    }
                    if original_workspace_hash and original_workspace_hash != workspace_hash:
                        metadata['original_workspace_hash'] = original_workspace_hash
                    
                    cursor_sessions_data.append((
                        internal_session_id,
                        external_session_id,
                        workspace_hash,
                        workspace_name,
                        workspace_path,
                        started_at,
                        ended_at,
                        json.dumps(metadata)
                    ))
                
                if cursor_sessions_data:
                    conn.executemany("""
                        INSERT OR IGNORE INTO cursor_sessions 
                        (id, external_session_id, workspace_hash, workspace_name, workspace_path, started_at, ended_at, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, cursor_sessions_data)
                    
                    # Verify all sessions were inserted and check for duplicates
                    inserted_count = conn.execute("SELECT COUNT(*) FROM cursor_sessions").fetchone()[0]
                    logger.info(f"Inserted {len(cursor_sessions_data)} Cursor sessions (total in table: {inserted_count})")
                    
                    # Verify no duplicates after migration
                    cursor = conn.execute("""
                        SELECT external_session_id, COUNT(*) as cnt
                        FROM cursor_sessions
                        GROUP BY external_session_id
                        HAVING cnt > 1
                    """)
                    duplicates = cursor.fetchall()
                    if duplicates:
                        logger.error(f"Found {len(duplicates)} duplicate external_session_ids after migration!")
                        for ext_id, count in duplicates:
                            logger.error(f"  - {ext_id}: {count} occurrences")
                        raise RuntimeError("Migration failed: duplicate external_session_ids detected")
                else:
                    logger.warning("No valid Cursor sessions found to migrate")
                    session_mapping = {}
            
            # Step 4: Create new conversations table
            logger.info("Step 3: Creating new conversations table schema...")
            conn.execute("""
                CREATE TABLE conversations_new (
                    id TEXT PRIMARY KEY,
                    session_id TEXT,
                    external_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    workspace_hash TEXT,
                    workspace_name TEXT,
                    started_at TIMESTAMP NOT NULL,
                    ended_at TIMESTAMP,
                    context TEXT DEFAULT '{}',
                    metadata TEXT DEFAULT '{}',
                    tool_sequence TEXT DEFAULT '[]',
                    acceptance_decisions TEXT DEFAULT '[]',
                    interaction_count INTEGER DEFAULT 0,
                    acceptance_rate REAL,
                    total_tokens INTEGER DEFAULT 0,
                    total_changes INTEGER DEFAULT 0,
                    FOREIGN KEY (session_id) REFERENCES cursor_sessions(id),
                    CHECK (
                        (platform = 'cursor' AND session_id IS NOT NULL) OR
                        (platform = 'claude_code' AND session_id IS NULL)
                    ),
                    UNIQUE(external_id, platform)
                )
            """)
            
            # Step 5: Migrate conversation data
            logger.info("Step 4: Migrating conversation data...")
            cursor = conn.execute("SELECT * FROM conversations")
            old_columns = [desc[0] for desc in cursor.description]
            
            migrated_count = 0
            used_external_ids = set()
            for row in cursor.fetchall():
                row_dict = dict(zip(old_columns, row))
                conversation_id = row_dict['id']
                platform = row_dict['platform']
                external_session_id = row_dict.get('external_session_id', '')
                workspace_hash_override = None
                metadata_value = row_dict.get('metadata', '{}')
                
                # Determine session_id and external_id
                if platform == 'cursor':
                    # Validate this is actually a Cursor conversation
                    if not external_session_id:
                        logger.warning(f"Cursor conversation {conversation_id} missing external_session_id, skipping")
                        continue
                    
                    # Look up new internal session_id
                    mapping_entry = session_mapping.get(external_session_id)
                    if not mapping_entry:
                        logger.warning(f"No session mapping found for Cursor conversation {conversation_id} with external_session_id={external_session_id}, skipping")
                        continue
                    new_session_id = mapping_entry["internal_id"]
                    workspace_hash_override = mapping_entry.get("workspace_hash")
                    external_id = external_session_id or conversation_id

                    # Preserve original external session ID in metadata for reference
                    if external_session_id:
                        try:
                            metadata_obj = json.loads(metadata_value) if metadata_value else {}
                        except json.JSONDecodeError:
                            metadata_obj = {}
                        if metadata_obj.get('external_session_id') != external_session_id:
                            metadata_obj['external_session_id'] = external_session_id
                            metadata_value = json.dumps(metadata_obj)
                elif platform == 'claude_code':
                    # Claude Code: session_id is NULL, external_id is the session/conversation ID
                    new_session_id = None
                    external_id = external_session_id or conversation_id
                else:
                    # Unknown platform - skip or handle as Claude Code
                    logger.warning(f"Unknown platform '{platform}' for conversation {conversation_id}, treating as Claude Code")
                    new_session_id = None
                    external_id = external_session_id or conversation_id
            
                # Ensure external_id uniqueness per platform
                desired_external_id = external_id or conversation_id
                external_id_candidate = desired_external_id
                suffix = 1
                while (platform, external_id_candidate) in used_external_ids:
                    external_id_candidate = f"{desired_external_id}__{suffix}"
                    suffix += 1
                external_id = external_id_candidate
                used_external_ids.add((platform, external_id))

                # Insert into new table
                try:
                    conn.execute("""
                        INSERT INTO conversations_new (
                            id, session_id, external_id, platform,
                            workspace_hash, workspace_name, started_at, ended_at,
                            context, metadata, tool_sequence, acceptance_decisions,
                            interaction_count, acceptance_rate, total_tokens, total_changes
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        conversation_id,
                        new_session_id,
                        external_id,
                        platform,
                        row_dict.get('workspace_hash') or workspace_hash_override,
                        row_dict.get('workspace_name'),
                        row_dict.get('started_at'),
                        row_dict.get('ended_at'),
                        row_dict.get('context', '{}'),
                        metadata_value,
                        row_dict.get('tool_sequence', '[]'),
                        row_dict.get('acceptance_decisions', '[]'),
                        row_dict.get('interaction_count', 0),
                        row_dict.get('acceptance_rate'),
                        row_dict.get('total_tokens', 0),
                        row_dict.get('total_changes', 0),
                    ))
                    migrated_count += 1
                except Exception as e:
                    logger.warning(f"Failed to migrate conversation {conversation_id}: {e}")
            
            logger.info(f"Migrated {migrated_count} conversations")
            
            # Step 6: Replace old table with new table
            logger.info("Step 5: Replacing conversations table...")
            conn.execute("DROP TABLE conversations")
            conn.execute("ALTER TABLE conversations_new RENAME TO conversations")
            
            # Step 7: Create indexes
            logger.info("Step 6: Creating indexes...")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_session_cursor ON conversations(session_id) WHERE platform = 'cursor';")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_external ON conversations(external_id, platform);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_platform_time ON conversations(platform, started_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_platform_active ON conversations(platform, ended_at) WHERE ended_at IS NULL;")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_platform_started ON conversations(platform, started_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conversations_workspace ON conversations(workspace_hash) WHERE workspace_hash IS NOT NULL;")
            
            conn.commit()
            logger.info("Migration to v2 complete successfully")
            
    except Exception as e:
        logger.error(f"Migration to v2 failed: {e}", exc_info=True)
        raise

