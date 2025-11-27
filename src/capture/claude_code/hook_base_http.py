#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Zero-dependency base class for Claude Code hooks using HTTP submission.

Uses ONLY Python stdlib - no external dependencies (no yaml, redis, etc.).
Hooks use environment variables, NOT config files.

Environment vars:
  BLUEPLANE_SERVER_URL    - Server URL (default: http://127.0.0.1:8787)
  BLUEPLANE_HOOK_TIMEOUT  - Request timeout seconds (default: 0.1)

Architecture:
  Hook (env vars) → HTTP POST → Server (config.yaml) → Redis → Database
"""

import json
import os
import sys
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, Optional


# =============================================================================
# INLINE CONSTANTS (avoid importing from shared modules)
# =============================================================================

# HookType values (from shared/event_schema.py)
HOOK_TYPE_SESSION_START = "SessionStart"
HOOK_TYPE_SESSION_END = "SessionEnd"
HOOK_TYPE_PRE_TOOL_USE = "PreToolUse"
HOOK_TYPE_POST_TOOL_USE = "PostToolUse"
HOOK_TYPE_USER_PROMPT_SUBMIT = "UserPromptSubmit"
HOOK_TYPE_STOP = "Stop"
HOOK_TYPE_PRE_COMPACT = "PreCompact"

# EventType values (from shared/event_schema.py)
EVENT_TYPE_SESSION_START = "session_start"
EVENT_TYPE_SESSION_END = "session_end"
EVENT_TYPE_USER_PROMPT = "user_prompt"
EVENT_TYPE_ASSISTANT_RESPONSE = "assistant_response"
EVENT_TYPE_TOOL_USE = "tool_use"
EVENT_TYPE_CONTEXT_COMPACT = "context_compact"

# Platform identifier
PLATFORM_CLAUDE_CODE = "claude_code"

# Version
__version__ = "0.1.0"


# =============================================================================
# HTTP CLIENT (zero-dependency)
# =============================================================================

class HookHTTPClient:
    """
    Zero-dependency HTTP client for hook event submission.

    Uses only Python stdlib (urllib.request).
    Implements fire-and-forget pattern with silent failure.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8787",
        timeout: float = 0.1,
    ):
        """
        Initialize HTTP client.

        Args:
            base_url: Server base URL
            timeout: Request timeout in seconds (default: 100ms)
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def submit_event(
        self,
        event: Dict[str, Any],
        platform: str,
        session_id: str,
    ) -> bool:
        """
        Submit event to telemetry server via HTTP POST.

        Returns True on success (202 Accepted), False on any failure.
        Never raises exceptions - implements fire-and-forget pattern.

        Args:
            event: Event dictionary with hook_type, timestamp, payload
            platform: Platform identifier (claude_code)
            session_id: Session identifier

        Returns:
            True on success, False on failure
        """
        try:
            payload = {
                "event": event,
                "platform": platform,
                "session_id": session_id,
            }

            data = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                f"{self.base_url}/events",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status == 202

        except urllib.error.URLError:
            # Server not reachable (connection refused, DNS failure, etc.)
            return False
        except urllib.error.HTTPError:
            # Server returned error status
            return False
        except TimeoutError:
            # Request timed out
            return False
        except OSError:
            # Network error
            return False
        except Exception:
            # Catch-all for unexpected errors
            return False


# =============================================================================
# HOOK BASE CLASS
# =============================================================================

class ClaudeCodeHookBaseHTTP:
    """
    Zero-dependency base class for Claude Code hooks using HTTP submission.

    All Claude Code hooks receive JSON input via stdin with a common schema containing:
    - session_id: Unique session identifier
    - Hook-specific fields (tool_name, prompt, etc.)

    Provides:
    - JSON stdin reading
    - Session ID retrieval
    - Event building and HTTP submission
    - Silent failure mode (never blocks IDE)
    """

    def __init__(self, hook_type: str):
        """
        Initialize hook.

        Args:
            hook_type: Type of hook being executed (use HOOK_TYPE_* constants)
        """
        self.hook_type = hook_type
        self.input_data: Dict[str, Any] = {}
        self.session_id: Optional[str] = None
        self.http_client: Optional[HookHTTPClient] = None

        # Read input from stdin
        self._read_input()

        # Extract common fields
        self.session_id = self.input_data.get("session_id")

        # Initialize HTTP client only if we have a session
        if self.session_id:
            try:
                # Get server URL from environment or use default
                server_url = os.environ.get(
                    "BLUEPLANE_SERVER_URL",
                    "http://127.0.0.1:8787"
                )
                timeout = float(os.environ.get("BLUEPLANE_HOOK_TIMEOUT", "0.1"))

                self.http_client = HookHTTPClient(
                    base_url=server_url,
                    timeout=timeout,
                )
            except Exception:
                # Silent failure - don't block IDE
                pass

    def _read_input(self) -> None:
        """Read JSON input from stdin."""
        try:
            self.input_data = json.load(sys.stdin)
        except Exception as e:
            # Log to stderr (not stdout which is reserved for hook output)
            print(f"Error reading stdin: {e}", file=sys.stderr)
            self.input_data = {}

    def _get_workspace_hash(self, workspace_path: Optional[str] = None) -> Optional[str]:
        """
        Get workspace hash from current working directory.

        Returns:
            Workspace hash computed from workspace path (16 char hex)
        """
        path = workspace_path or self.input_data.get("cwd") or os.getcwd()
        return hashlib.sha256(path.encode()).hexdigest()[:16]

    def _derive_project_name(self, workspace_path: Optional[str] = None) -> Optional[str]:
        """
        Derive project name from workspace path.

        Simple implementation: returns the last directory component.

        Args:
            workspace_path: Optional workspace path

        Returns:
            Project name or None
        """
        path = workspace_path or self.input_data.get("cwd") or os.getcwd()
        if path:
            # Get last non-empty component
            parts = path.rstrip("/").split("/")
            for part in reversed(parts):
                if part:
                    return part
        return None

    def build_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build event dictionary.

        Args:
            event_type: Type of event (use EVENT_TYPE_* constants)
            payload: Event payload data
            metadata: Additional metadata

        Returns:
            Event dictionary ready for submission
        """
        metadata_dict = dict(metadata) if metadata else {}
        workspace_path_input = self.input_data.get("cwd") or self.input_data.get("workspace_path")

        event = {
            "version": __version__,
            "hook_type": self.hook_type,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
            "metadata": metadata_dict,
        }

        if workspace_path_input:
            event["metadata"]["workspace_path"] = workspace_path_input

        # Add process ID
        event["metadata"]["pid"] = os.getpid()

        # Add workspace hash if available
        workspace_hash = self._get_workspace_hash(workspace_path_input)
        if workspace_hash:
            event["metadata"]["workspace_hash"] = workspace_hash

        # Attach project name for downstream analytics
        project_name = event["metadata"].get("project_name")
        if not project_name:
            project_name = self._derive_project_name(workspace_path_input)

        if project_name:
            event["metadata"]["project_name"] = project_name

        return event

    def submit_event(self, event: Dict[str, Any]) -> bool:
        """
        Submit event via HTTP to telemetry server.

        Args:
            event: Event to submit

        Returns:
            True if successful, False otherwise
        """
        if not self.session_id:
            return False

        if not self.http_client:
            return False

        try:
            success = self.http_client.submit_event(
                event=event,
                platform=PLATFORM_CLAUDE_CODE,
                session_id=self.session_id,
            )
            return success
        except Exception:
            # Silent failure
            return False

    def execute(self) -> int:
        """
        Execute hook logic. Override in subclasses.

        Returns:
            Exit code (always 0 for silent failure)
        """
        raise NotImplementedError("Subclasses must implement execute()")

    def run(self) -> int:
        """
        Main entry point. Executes hook and handles errors.

        Returns:
            Exit code (always 0 for silent failure)
        """
        try:
            return self.execute()
        except Exception as e:
            # Log to stderr but never fail
            print(f"Hook error: {e}", file=sys.stderr)
            return 0
