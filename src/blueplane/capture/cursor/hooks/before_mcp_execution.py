#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

# DEPRECATED: This hook is no longer installed or used.
# The cursor monitor now only listens for extension session_start and session_end events
# sent directly to Redis. This file is kept for reference only.

"""
Cursor beforeMCPExecution Hook (stdin/stdout)

Fires before an MCP tool is executed.
Receives JSON via stdin, outputs permission decision via stdout.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import CursorHookBase
from shared.event_schema import EventType, HookType


class BeforeMCPExecutionHook(CursorHookBase):
    """Hook that fires before MCP tool execution."""

    def __init__(self):
        super().__init__(HookType.BEFORE_MCP_EXECUTION)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract MCP data from stdin
        tool_name = self.input_data.get('tool_name', '')
        tool_input = self.input_data.get('tool_input', '')

        # Build event payload
        payload = {
            'tool_name': tool_name,
            'input_size': len(str(tool_input)),
            'tool_input': tool_input,  # Full tool input (privacy-aware)
        }

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.MCP_EXECUTION,
            payload=payload
        )

        self.enqueue_event(event)

        # Always allow execution
        self.write_output({"permission": "allow"})

        return 0


if __name__ == '__main__':
    hook = BeforeMCPExecutionHook()
    sys.exit(hook.run())
