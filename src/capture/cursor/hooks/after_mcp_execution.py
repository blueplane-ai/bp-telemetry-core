#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Cursor afterMCPExecution Hook (stdin/stdout)

Fires after an MCP tool executes.
Receives JSON via stdin.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import CursorHookBase
from shared.event_schema import EventType, HookType


class AfterMCPExecutionHook(CursorHookBase):
    """Hook that fires after MCP tool execution."""

    def __init__(self):
        super().__init__(HookType.AFTER_MCP_EXECUTION)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract MCP execution data from stdin
        tool_name = self.input_data.get('tool_name', '')
        tool_input = self.input_data.get('tool_input', '')
        result_json = self.input_data.get('result_json', '')

        # Build event payload
        payload = {
            'tool_name': tool_name,
            'input_size': len(str(tool_input)),
            'output_size': len(str(result_json)),
        }

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.MCP_EXECUTION,
            payload=payload
        )

        self.enqueue_event(event)

        # No output needed for this hook
        return 0


if __name__ == '__main__':
    hook = AfterMCPExecutionHook()
    sys.exit(hook.run())
