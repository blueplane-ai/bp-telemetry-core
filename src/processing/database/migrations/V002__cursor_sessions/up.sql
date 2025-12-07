-- Migration v2: Add cursor_sessions table and update conversations table
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
