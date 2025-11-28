#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Claude Code SessionStart Hook (HTTP version)

Zero-dependency hook that fires at the start of a new Claude Code session.
Receives JSON via stdin with session_id and submits event via HTTP.

This hook uses ONLY Python standard library - no external dependencies.
"""

import sys
from pathlib import Path

# Add parent directory to path for hook_base_http import
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base_http import (
    ClaudeCodeHookBaseHTTP,
    HOOK_TYPE_SESSION_START,
    EVENT_TYPE_SESSION_START,
)


class SessionStartHook(ClaudeCodeHookBaseHTTP):
    """Hook that fires at session start (HTTP version)."""

    def __init__(self):
        super().__init__(HOOK_TYPE_SESSION_START)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract session data from stdin
        source = self.input_data.get("source", "unknown")
        workspace_path = self.input_data.get("workspace_path", "")

        # Build event payload
        payload = {
            "source": source,
            "session_id": self.session_id,
            "workspace_path": workspace_path,
        }

        # Build and submit event via HTTP
        event = self.build_event(
            event_type=EVENT_TYPE_SESSION_START,
            payload=payload,
        )

        self.submit_event(event)

        return 0


if __name__ == "__main__":
    hook = SessionStartHook()
    sys.exit(hook.run())
