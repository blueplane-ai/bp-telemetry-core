#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

# DEPRECATED: This hook is no longer installed or used.
# The cursor monitor now only listens for extension session_start and session_end events
# sent directly to Redis. This file is kept for reference only.

"""
Cursor stop Hook (stdin/stdout)

Fires when agent loop ends.
Receives JSON via stdin.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import CursorHookBase
from shared.event_schema import EventType, HookType


class StopHook(CursorHookBase):
    """Hook that fires when agent loop stops."""

    def __init__(self):
        super().__init__(HookType.CURSOR_STOP)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract stop data from stdin
        status = self.input_data.get('status', 'completed')
        loop_count = self.input_data.get('loop_count', 0)

        # Build event payload
        payload = {
            'status': status,
            'loop_count': loop_count,
        }

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.SESSION_END,
            payload=payload
        )

        self.enqueue_event(event)

        # No output needed (or optional followup_message for auto-iteration)
        return 0


if __name__ == '__main__':
    hook = StopHook()
    sys.exit(hook.run())
