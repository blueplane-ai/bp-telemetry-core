#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Claude Code SessionEnd Hook (HTTP version)

Zero-dependency hook that fires at the end of a session (when Claude Code closes).
Receives JSON via stdin with session_id and transcript_path, submits event via HTTP.

This hook uses ONLY Python standard library - no external dependencies.
"""

import hashlib
import sys
from pathlib import Path

# Add parent directory to path for hook_base_http import
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base_http import (
    ClaudeCodeHookBaseHTTP,
    HOOK_TYPE_SESSION_END,
    EVENT_TYPE_SESSION_END,
)


class SessionEndHook(ClaudeCodeHookBaseHTTP):
    """Hook that fires at session end (HTTP version)."""

    def __init__(self):
        super().__init__(HOOK_TYPE_SESSION_END)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract session end data from stdin
        transcript_path = self.input_data.get("transcript_path")
        session_end_hook_active = self.input_data.get("session_end_hook_active", True)

        # Build event payload
        payload = {
            "session_id": self.session_id,
            "session_end_hook_active": session_end_hook_active,
        }

        if transcript_path:
            payload["has_transcript"] = True
            # Store path hash instead of full path for privacy
            payload["transcript_path_hash"] = hashlib.sha256(
                str(transcript_path).encode()
            ).hexdigest()[:16]
            # Also store the actual path for the transcript monitor to use
            payload["transcript_path"] = transcript_path

        # Build and submit event via HTTP
        event = self.build_event(
            event_type=EVENT_TYPE_SESSION_END,
            payload=payload,
        )

        self.submit_event(event)

        return 0


if __name__ == "__main__":
    hook = SessionEndHook()
    sys.exit(hook.run())
