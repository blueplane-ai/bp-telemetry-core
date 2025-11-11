#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Claude Code SessionStart Hook

Fires at the start of a new Claude Code session.
Receives JSON via stdin with session_id.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import ClaudeCodeHookBase
from shared.event_schema import EventType, HookType


class SessionStartHook(ClaudeCodeHookBase):
    """Hook that fires at session start."""

    def __init__(self):
        super().__init__(HookType.SESSION_START)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract session data from stdin
        source = self.input_data.get('source', 'unknown')

        # Build event payload
        payload = {
            'source': source,
            'session_id': self.session_id,
        }

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.SESSION_START,
            payload=payload
        )

        self.enqueue_event(event)

        return 0


if __name__ == '__main__':
    hook = SessionStartHook()
    sys.exit(hook.run())
