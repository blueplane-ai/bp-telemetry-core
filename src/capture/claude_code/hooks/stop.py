#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Claude Code Stop Hook

Fires when the assistant stops generating a response (end of turn/interaction).
Receives JSON via stdin with session_id.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import ClaudeCodeHookBase
from shared.event_schema import EventType, HookType


class StopHook(ClaudeCodeHookBase):
    """Hook that fires when assistant stops responding (end of turn)."""

    def __init__(self):
        super().__init__(HookType.STOP)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract stop data from stdin
        # Stop hook fires at the end of each assistant response
        transcript_path = self.input_data.get('transcript_path')
        stop_hook_active = self.input_data.get('stop_hook_active', True)

        # Build event payload
        payload = {
            'session_id': self.session_id,
            'stop_type': 'assistant_response_complete',
            'stop_hook_active': stop_hook_active,
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
            event_type=EventType.ASSISTANT_RESPONSE,
            payload=payload
        )

        self.enqueue_event(event)

        return 0


if __name__ == '__main__':
    hook = StopHook()
    sys.exit(hook.run())
