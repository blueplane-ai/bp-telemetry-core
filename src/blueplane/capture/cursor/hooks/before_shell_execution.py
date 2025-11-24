#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

# DEPRECATED: This hook is no longer installed or used.
# The cursor monitor now only listens for extension session_start and session_end events
# sent directly to Redis. This file is kept for reference only.

"""
Cursor beforeShellExecution Hook (stdin/stdout)

Fires before a shell command is executed.
Receives JSON via stdin, outputs permission decision via stdout.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import CursorHookBase
from shared.event_schema import EventType, HookType


class BeforeShellExecutionHook(CursorHookBase):
    """Hook that fires before shell command execution."""

    def __init__(self):
        super().__init__(HookType.BEFORE_SHELL_EXECUTION)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract shell command data from stdin
        command = self.input_data.get('command', '')
        cwd = self.input_data.get('cwd', '')

        # Build event payload
        payload = {
            'command_length': len(command),
            'command': command,  # Full command text (privacy-aware)
            'cwd': cwd,
        }

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.SHELL_EXECUTION,
            payload=payload
        )

        self.enqueue_event(event)

        # Always allow execution
        self.write_output({"permission": "allow"})

        return 0


if __name__ == '__main__':
    hook = BeforeShellExecutionHook()
    sys.exit(hook.run())
