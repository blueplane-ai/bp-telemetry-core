-- Migration v3: Add workspaces and git_commits tables
-- Created: 2025-01-04
-- Author: Blueplane Telemetry Core

-- ============================================================================
-- Part 1: Create workspaces table
-- ============================================================================

CREATE TABLE IF NOT EXISTS workspaces (
    workspace_hash TEXT PRIMARY KEY,
    workspace_path TEXT NOT NULL,
    workspace_name TEXT,
    first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT DEFAULT '{}'
);

-- Create workspaces indexes
CREATE INDEX IF NOT EXISTS idx_workspaces_path
ON workspaces(workspace_path);

CREATE INDEX IF NOT EXISTS idx_workspaces_last_seen
ON workspaces(last_seen_at DESC);

-- ============================================================================
-- Part 2: Create git_commits table
-- ============================================================================

CREATE TABLE IF NOT EXISTS git_commits (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_hash TEXT NOT NULL,
    repo_id TEXT NOT NULL,
    workspace_hash TEXT NOT NULL,
    author_name TEXT,
    author_email TEXT,
    commit_timestamp TIMESTAMP NOT NULL,
    commit_message TEXT,
    files_changed INTEGER DEFAULT 0,
    insertions INTEGER DEFAULT 0,
    deletions INTEGER DEFAULT 0,
    branch_name TEXT,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    event_id TEXT,
    UNIQUE(repo_id, commit_hash)
);

-- Create git_commits indexes
CREATE INDEX IF NOT EXISTS idx_git_commits_workspace
ON git_commits(workspace_hash, commit_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_git_commits_repo
ON git_commits(repo_id, commit_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_git_commits_timestamp
ON git_commits(commit_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_git_commits_author
ON git_commits(author_email, commit_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_git_commits_branch
ON git_commits(branch_name, commit_timestamp DESC);
