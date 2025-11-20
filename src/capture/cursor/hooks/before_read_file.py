#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

# DEPRECATED: This hook is no longer installed or used.
# The cursor monitor now only listens for extension session_start and session_end events
# sent directly to Redis. This file is kept for reference only.

"""
Cursor beforeReadFile Hook (stdin/stdout)

Fires before agent reads a file.
Receives JSON via stdin, outputs permission decision via stdout.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import CursorHookBase
from shared.event_schema import EventType, HookType


class BeforeReadFileHook(CursorHookBase):
    """Hook that fires before file read."""

    def __init__(self):
        super().__init__(HookType.BEFORE_READ_FILE)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract file read data from stdin
        file_path = self.input_data.get('file_path', '')
        content = self.input_data.get('content', '')
        attachments = self.input_data.get('attachments', [])

        # Build event payload
        payload = {
            'file_extension': Path(file_path).suffix if file_path else None,
            'file_size': len(content),
        }

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.FILE_READ,
            payload=payload
        )

        self.enqueue_event(event)

        # Always allow file read
        self.write_output({"permission": "allow"})

        return 0


if __name__ == '__main__':
    hook = BeforeReadFileHook()
    sys.exit(hook.run())
