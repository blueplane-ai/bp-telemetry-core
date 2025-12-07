-- Rollback v4: Rename claude_conversations back to conversations
-- Created: 2025-01-04

-- Disable foreign keys for migration
PRAGMA foreign_keys = OFF;

-- Rename table back
ALTER TABLE claude_conversations RENAME TO conversations;

-- Re-enable foreign keys
PRAGMA foreign_keys = ON;
