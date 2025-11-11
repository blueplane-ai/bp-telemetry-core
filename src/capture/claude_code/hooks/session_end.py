#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Claude Code SessionEnd Hook

Fires at the end of a session (when Claude Code closes).
Receives JSON via stdin with session_id and transcript_path.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import ClaudeCodeHookBase
from shared.event_schema import EventType, HookType


class SessionEndHook(ClaudeCodeHookBase):
    """Hook that fires at session end (when Claude Code closes)."""

    def __init__(self):
        super().__init__(HookType.SESSION_END)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract session end data from stdin
        transcript_path = self.input_data.get('transcript_path')
        session_end_hook_active = self.input_data.get('session_end_hook_active', True)

        # Build event payload
        payload = {
            'session_id': self.session_id,
            'session_end_hook_active': session_end_hook_active,
        }

        if transcript_path:
            payload['has_transcript'] = True
            # Store path hash instead of full path for privacy
            import hashlib
            payload['transcript_path_hash'] = hashlib.sha256(str(transcript_path).encode()).hexdigest()[:16]
            # Also store the actual path for the transcript monitor to use
            payload['transcript_path'] = transcript_path

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.SESSION_END,
            payload=payload
        )

        self.enqueue_event(event)

        return 0


if __name__ == '__main__':
    hook = SessionEndHook()
    sys.exit(hook.run())
