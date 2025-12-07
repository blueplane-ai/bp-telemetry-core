-- Rollback v3: Remove workspaces and git_commits tables
-- Created: 2025-01-04

-- Drop git_commits indexes
DROP INDEX IF EXISTS idx_git_commits_workspace;
DROP INDEX IF EXISTS idx_git_commits_repo;
DROP INDEX IF EXISTS idx_git_commits_timestamp;
DROP INDEX IF EXISTS idx_git_commits_author;
DROP INDEX IF EXISTS idx_git_commits_branch;

-- Drop git_commits table
DROP TABLE IF EXISTS git_commits;

-- Drop workspaces indexes
DROP INDEX IF EXISTS idx_workspaces_path;
DROP INDEX IF EXISTS idx_workspaces_last_seen;

-- Drop workspaces table
DROP TABLE IF EXISTS workspaces;
