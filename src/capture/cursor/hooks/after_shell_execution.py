#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

# DEPRECATED: This hook is no longer installed or used.
# The cursor monitor now only listens for extension session_start and session_end events
# sent directly to Redis. This file is kept for reference only.

"""
Cursor afterShellExecution Hook (stdin/stdout)

Fires after a shell command executes.
Receives JSON via stdin.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import CursorHookBase
from shared.event_schema import EventType, HookType


class AfterShellExecutionHook(CursorHookBase):
    """Hook that fires after shell command execution."""

    def __init__(self):
        super().__init__(HookType.AFTER_SHELL_EXECUTION)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract shell execution data from stdin
        # Note: Cursor does not provide duration_ms in hook input
        command = self.input_data.get('command', '')
        output = self.input_data.get('output', '')
        exit_code = self.input_data.get('exit_code', 0)

        # Build event payload
        payload = {
            'command_length': len(command),
            'command': command,  # Full command text (privacy-aware)
            'output_lines': output.count('\n') if output else 0,
            'output': output,  # Full command output (privacy-aware)
            'exit_code': exit_code,
            # duration_ms not included - Cursor doesn't provide this field
        }

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.SHELL_EXECUTION,
            payload=payload
        )

        self.enqueue_event(event)

        # No output needed for this hook
        return 0


if __name__ == '__main__':
    hook = AfterShellExecutionHook()
    sys.exit(hook.run())
