#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Claude Code PreToolUse Hook

Fires before tool execution.
Receives JSON via stdin with session_id, tool_name, and tool_input.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import ClaudeCodeHookBase
from shared.event_schema import EventType, HookType


class PreToolUseHook(ClaudeCodeHookBase):
    """Hook that fires before tool execution."""

    def __init__(self):
        super().__init__(HookType.PRE_TOOL_USE)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract tool data from stdin
        tool_name = self.input_data.get('tool_name', 'unknown')
        tool_input = self.input_data.get('tool_input', {})

        # Build event payload
        payload = {
            'tool_name': tool_name,
            'tool_input': tool_input,
            'phase': 'pre',
        }

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.TOOL_USE,
            payload=payload
        )

        self.enqueue_event(event)

        return 0


if __name__ == '__main__':
    hook = PreToolUseHook()
    sys.exit(hook.run())
