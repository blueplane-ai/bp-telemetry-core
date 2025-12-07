-- Rollback v2: Remove cursor_sessions table changes
-- Created: 2025-01-04

-- Drop cursor_sessions indexes
DROP INDEX IF EXISTS idx_cursor_sessions_workspace;
DROP INDEX IF EXISTS idx_cursor_sessions_machine;
DROP INDEX IF EXISTS idx_cursor_sessions_last_seen;

-- Drop cursor_sessions table
DROP TABLE IF EXISTS cursor_sessions;

-- Note: Rollback of conversations table changes is not supported
-- due to data transformation complexity. Restore from backup if needed.
