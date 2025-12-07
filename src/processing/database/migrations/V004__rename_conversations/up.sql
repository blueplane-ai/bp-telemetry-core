-- Migration v4: Rename conversations table to claude_conversations
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
