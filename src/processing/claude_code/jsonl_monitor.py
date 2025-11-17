# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
JSONL File Monitor for Claude Code sessions.

Monitors JSONL files for active sessions with:
- 30-second polling interval
- Incremental file reading (offset tracking)
- Dynamic agent file detection
- Zero-impact on Claude Code performance
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional, Set
import redis

from .session_monitor import ClaudeCodeSessionMonitor
from ...capture.shared.project_utils import derive_project_name

logger = logging.getLogger(__name__)

# Claude Code JSONL file locations
CLAUDE_PROJECTS_BASE = Path.home() / ".claude" / "projects"


class FileState:
    """Track state of a monitored JSONL file."""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self.line_offset = 0  # Number of lines already processed
        self.last_size = 0
        self.last_mtime = 0.0
        self.last_read_time = 0.0

    def has_changed(self) -> bool:
        """Check if file has changed since last read."""
        if not self.file_path.exists():
            return False

        stat = self.file_path.stat()
        return stat.st_size > self.last_size or stat.st_mtime > self.last_mtime

    def update_state(self, size: int, mtime: float):
        """Update file state after reading."""
        self.last_size = size
        self.last_mtime = mtime
        self.last_read_time = time.time()


class ClaudeCodeJSONLMonitor:
    """
    Monitor Claude Code JSONL files for active sessions.

    Design Principles:
    1. Zero impact on Claude Code (read-only, incremental reads)
    2. Track file state (offset, size, mtime) to avoid re-reading
    3. Dynamic agent file detection via toolUseResult.agentId
    4. Maintain map of session → monitored agent files
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        session_monitor: ClaudeCodeSessionMonitor,
        poll_interval: float = 30.0,
    ):
        self.redis_client = redis_client
        self.session_monitor = session_monitor
        self.poll_interval = poll_interval

        # Track file states: file_path → FileState
        self.file_states: Dict[Path, FileState] = {}

        # Track agent files per session: session_id → set of agent_ids
        self.session_agents: Dict[str, Set[str]] = {}

        # Track which sessions we're currently monitoring
        self.monitored_sessions: Set[str] = set()

        self.running = False

    async def start(self):
        """Start JSONL file monitoring."""
        self.running = True
        logger.info("Claude Code JSONL monitor started")

        # Run monitoring loop directly (blocks until stopped)
        await self._monitor_loop()

    async def stop(self):
        """Stop JSONL file monitoring."""
        self.running = False
        logger.info("Claude Code JSONL monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop - polls every 30 seconds."""
        logger.info(f"JSONL monitor loop starting, poll interval: {self.poll_interval}s")
        while self.running:
            try:
                # Get active sessions from session monitor
                active_sessions = self.session_monitor.get_active_sessions()

                if active_sessions:
                    logger.debug(f"Monitoring {len(active_sessions)} active sessions")

                # Monitor each active session
                for session_id, session_info in active_sessions.items():
                    await self._monitor_session(session_id, session_info)

                # Clean up inactive sessions
                await self._cleanup_inactive_sessions(set(active_sessions.keys()))

                await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"Error in JSONL monitor loop: {e}")
                await asyncio.sleep(5)

    async def _monitor_session(self, session_id: str, session_info: dict):
        """Monitor JSONL files for a specific session."""
        try:
            workspace_path = session_info.get("workspace_path", "")

            # If no workspace_path, try to discover it from existing JSONL files
            if not workspace_path:
                logger.debug(f"No workspace_path for session {session_id}, attempting discovery...")
                workspace_path = await self._discover_workspace_path(session_id)

                if workspace_path:
                    # Update session info with discovered workspace_path
                    session_info["workspace_path"] = workspace_path
                    if self.session_monitor:
                        await self.session_monitor.update_session_workspace(session_id, workspace_path)
                    logger.info(f"Discovered workspace_path for session {session_id}: {workspace_path}")
                else:
                    logger.warning(f"Could not discover workspace_path for session {session_id}")
                    return

            # Find project directory
            project_dir = self._find_project_dir(workspace_path)
            if not project_dir:
                logger.warning(f"No project directory found for {workspace_path}")
                return

            logger.debug(f"Found project directory: {project_dir}")

            # On first monitoring, read the main session file
            if session_id not in self.monitored_sessions:
                self.monitored_sessions.add(session_id)
                self.session_agents[session_id] = set()
                logger.info(f"Started monitoring session: {session_id}")

            # Monitor main session file
            # Claude Code creates session files with the session_id as filename
            session_file = project_dir / f"{session_id}.jsonl"
            if session_file.exists():
                logger.info(f"Found session file: {session_file}")
                await self._monitor_file(session_file, session_id, session_info)
            else:
                logger.debug(f"Session file not found: {session_file}")

            # Monitor agent files
            await self._monitor_agent_files(project_dir, session_id, session_info)

        except Exception as e:
            logger.error(f"Error monitoring session {session_id}: {e}")

    def _find_project_dir(self, workspace_path: str) -> Optional[Path]:
        """
        Find Claude project directory for workspace.

        Claude creates project dirs like: ~/.claude/projects/-Users-username-path-to-workspace/
        """
        # Convert workspace path to project dir format
        # Example: /Users/bbalaran/Dev/project → -Users-bbalaran-Dev-project
        normalized = workspace_path.replace("/", "-")
        if normalized.startswith("-"):
            normalized = normalized[1:]  # Remove leading dash

        project_dir = CLAUDE_PROJECTS_BASE / f"-{normalized}"

        if project_dir.exists() and project_dir.is_dir():
            return project_dir

        # Try without leading dash
        project_dir_alt = CLAUDE_PROJECTS_BASE / normalized
        if project_dir_alt.exists() and project_dir_alt.is_dir():
            return project_dir_alt

        return None

    async def _discover_workspace_path(self, session_id: str) -> Optional[str]:
        """
        Discover workspace path for a session by searching all project directories.

        When workspace_path is not provided in session_start, we scan all project
        directories to find a matching session file and extract the workspace from its content.
        """
        try:
            # Search all project directories
            if not CLAUDE_PROJECTS_BASE.exists():
                return None

            for project_dir in CLAUDE_PROJECTS_BASE.iterdir():
                if not project_dir.is_dir():
                    continue

                # Look for session file
                session_file = project_dir / f"{session_id}.jsonl"
                if not session_file.exists():
                    continue

                logger.debug(f"Found session file at {session_file}")

                # Try to extract workspace from project directory name
                # Directory names like: -Users-bbalaran-Dev-sierra-blueplane-bp-telemetry-core
                dir_name = project_dir.name
                if dir_name.startswith("-"):
                    dir_name = dir_name[1:]  # Remove leading dash

                # Convert dashes back to slashes for path
                workspace_path = "/" + dir_name.replace("-", "/")

                # Validate by reading first few lines of JSONL to confirm
                try:
                    with open(session_file, 'r', encoding='utf-8') as f:
                        for i, line in enumerate(f):
                            if i > 10:  # Check first 10 lines max
                                break
                            line = line.strip()
                            if not line:
                                continue

                            try:
                                entry = json.loads(line)

                                # Look for IDE file references or other workspace indicators
                                content_str = json.dumps(entry)
                                if workspace_path in content_str:
                                    logger.debug(f"Confirmed workspace path {workspace_path} in JSONL content")
                                    return workspace_path

                                # Also check for explicit workspace fields
                                for key in ('cwd', 'workspace', 'workspace_path'):
                                    val = entry.get(key)
                                    if isinstance(val, str) and val:
                                        return val

                                # Check in metadata
                                metadata = entry.get('metadata', {})
                                if isinstance(metadata, dict):
                                    for key in ('cwd', 'workspace', 'workspace_path'):
                                        val = metadata.get(key)
                                        if isinstance(val, str) and val:
                                            return val

                            except json.JSONDecodeError:
                                continue

                except Exception as e:
                    logger.debug(f"Error reading session file {session_file}: {e}")
                    continue

                # If we found the file but couldn't confirm, still return the derived path
                logger.info(f"Using derived workspace path {workspace_path} for session {session_id}")
                return workspace_path

        except Exception as e:
            logger.error(f"Error discovering workspace path for session {session_id}: {e}")

        return None

    async def _monitor_file(
        self,
        file_path: Path,
        session_id: str,
        session_info: dict
    ):
        """Monitor a single JSONL file for changes."""
        # Get or create file state
        if file_path not in self.file_states:
            self.file_states[file_path] = FileState(file_path)

        file_state = self.file_states[file_path]

        # Check if file has changed
        if not file_state.has_changed():
            return

        try:
            # Read new lines only
            new_events = await self._read_new_lines(file_path, file_state)

            if not new_events:
                return

            logger.info(f"Read {len(new_events)} new events from {file_path.name}")

            # Process each event
            for entry_data in new_events:
                await self._process_event(entry_data, session_id, session_info)

            # Update file state
            stat = file_path.stat()
            file_state.update_state(stat.st_size, stat.st_mtime)

        except Exception as e:
            logger.error(f"Error monitoring file {file_path}: {e}")

    async def _read_new_lines(
        self,
        file_path: Path,
        file_state: FileState
    ) -> list:
        """Read only new lines from JSONL file since last read."""
        new_events = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Skip already-processed lines
                for _ in range(file_state.line_offset):
                    f.readline()

                # Read new lines
                line_count = 0
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        entry = json.loads(line)
                        new_events.append(entry)
                        line_count += 1
                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON in {file_path}: {e}")
                        continue

                # Update line offset
                file_state.line_offset += line_count

        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")

        return new_events

    async def _process_event(
        self,
        entry_data: dict,
        session_id: str,
        session_info: dict
    ):
        """Process a single JSONL event."""
        try:
            # Extract timestamp
            timestamp = entry_data.get("timestamp", "")
            if not timestamp:
                timestamp = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())

            # Check for new agent IDs in tool results
            await self._detect_new_agents(entry_data, session_id)

            # Build event for Redis
            project_name = session_info.get("project_name") or derive_project_name(session_info.get("workspace_path"))

            event = {
                "version": "0.1.0",
                "hook_type": "JSONLTrace",
                "event_type": entry_data.get("type", "unknown"),
                "timestamp": timestamp,
                "platform": "claude_code",
                "session_id": session_id,
                "external_session_id": session_id,
                "metadata": {
                    "workspace_hash": session_info.get("workspace_hash"),
                    "project_name": project_name,
                    "source": "jsonl_monitor",
                },
                "payload": {
                    "entry_data": entry_data,
                },
            }

            # Send to Redis stream
            self.redis_client.xadd(
                "telemetry:events",
                {
                    k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                    for k, v in event.items()
                },
                maxlen=10000,
                approximate=True
            )

            logger.debug(f"Captured event: {entry_data.get('type')} (uuid: {entry_data.get('uuid')})")

        except Exception as e:
            logger.error(f"Error processing event: {e}")

    async def _detect_new_agents(self, entry_data: dict, session_id: str):
        """
        Detect new agent IDs in tool results and add agent file monitors.

        When a TOOL-USE event completes, check if toolUseResult contains agentId.
        If it's a new agent for this session, start monitoring that agent file.
        """
        # Check for events with toolUseResult containing agentId
        # In Claude Code JSONL, toolUseResult is at the top level of the event
        tool_use_result = entry_data.get("toolUseResult", {})
        if not isinstance(tool_use_result, dict):
            return

        agent_id = tool_use_result.get("agentId")
        if not agent_id:
            return

        # Check if this is a new agent for this session
        if session_id not in self.session_agents:
            self.session_agents[session_id] = set()

        if agent_id in self.session_agents[session_id]:
            return  # Already monitoring this agent

        # New agent detected!
        self.session_agents[session_id].add(agent_id)
        logger.info(f"Detected new agent for session {session_id}: {agent_id}")

    async def _monitor_agent_files(
        self,
        project_dir: Path,
        session_id: str,
        session_info: dict
    ):
        """Monitor all agent files for a session."""
        # Get known agent IDs for this session
        agent_ids = self.session_agents.get(session_id, set())

        for agent_id in agent_ids:
            agent_file = project_dir / f"agent-{agent_id}.jsonl"

            if not agent_file.exists():
                logger.debug(f"Agent file not found yet: {agent_file}")
                continue

            # Monitor the agent file
            await self._monitor_file(agent_file, session_id, session_info)

    async def _cleanup_inactive_sessions(self, active_session_ids: Set[str]):
        """Clean up resources for inactive sessions."""
        inactive = self.monitored_sessions - active_session_ids

        for session_id in inactive:
            # Remove from monitored sessions
            self.monitored_sessions.discard(session_id)

            # Remove agent tracking
            if session_id in self.session_agents:
                del self.session_agents[session_id]

            logger.info(f"Cleaned up inactive session: {session_id}")

        # Clean up file states for files that no longer belong to active sessions
        # (This is a bit complex, so we'll just keep them for now - they're lightweight)
