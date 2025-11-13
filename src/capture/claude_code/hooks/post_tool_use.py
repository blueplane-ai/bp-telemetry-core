#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Claude Code PostToolUse Hook

Fires after tool execution completes.
Receives JSON via stdin with session_id, tool_name, tool_input, tool_result, and error info.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import ClaudeCodeHookBase
from shared.event_schema import EventType, HookType


class PostToolUseHook(ClaudeCodeHookBase):
    """Hook that fires after tool execution."""

    def __init__(self):
        super().__init__(HookType.POST_TOOL_USE)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract tool data from stdin
        tool_name = self.input_data.get('tool_name', 'unknown')
        tool_input = self.input_data.get('tool_input', {})
        tool_result = self.input_data.get('tool_result')
        tool_response = self.input_data.get('tool_response', {})
        error = self.input_data.get('error')
        tool_use_error = self.input_data.get('tool_use_error')

        # Determine success/failure
        success = error is None and tool_use_error is None
        if tool_response and isinstance(tool_response, dict):
            success = tool_response.get('success', success)

        # Build event payload
        payload = {
            'tool_name': tool_name,
            'tool_input': tool_input,
            'phase': 'post',
            'success': success,
        }

        # Calculate lines added/removed for Edit tool
        if tool_name == 'Edit' and success and isinstance(tool_input, dict):
            old_string = tool_input.get('old_string', '')
            new_string = tool_input.get('new_string', '')

            # Count lines in old and new strings
            old_lines = len(old_string.splitlines()) if old_string else 0
            new_lines = len(new_string.splitlines()) if new_string else 0

            # Calculate net change
            if new_lines > old_lines:
                payload['lines_added'] = new_lines - old_lines
                payload['lines_removed'] = 0
            elif old_lines > new_lines:
                payload['lines_added'] = 0
                payload['lines_removed'] = old_lines - new_lines
            else:
                # Same number of lines - consider it a modification
                payload['lines_added'] = 0
                payload['lines_removed'] = 0

        # Add result size info (not full content for privacy)
        if tool_result is not None:
            if isinstance(tool_result, str):
                payload['result_length'] = len(tool_result)
            elif isinstance(tool_result, dict):
                payload['result_keys'] = list(tool_result.keys())

        # Add error info if present
        if error:
            payload['error'] = str(error)
        if tool_use_error:
            payload['tool_use_error'] = str(tool_use_error)

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.TOOL_USE,
            payload=payload
        )

        self.enqueue_event(event)

        return 0


if __name__ == '__main__':
    hook = PostToolUseHook()
    sys.exit(hook.run())
