#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Cursor afterFileEdit Hook (stdin/stdout)

Fires after a file is edited by the agent.
Receives JSON via stdin.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import CursorHookBase
from shared.event_schema import EventType, HookType


class AfterFileEditHook(CursorHookBase):
    """Hook that fires after file edits."""

    def __init__(self):
        super().__init__(HookType.AFTER_FILE_EDIT)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract file edit data from stdin
        # Note: 'file' is the standard field name, 'file_path' for backwards compat
        file_path = self.input_data.get('file', self.input_data.get('file_path', ''))
        changes = self.input_data.get('changes', {})
        edits = self.input_data.get('edits', [])

        # Extract line change statistics
        lines_added = changes.get('added', 0)
        lines_removed = changes.get('removed', 0)

        # Build event payload
        payload = {
            'file_extension': Path(file_path).suffix if file_path else None,
            'edit_count': len(edits) if edits else 1,
            'lines_added': lines_added,
            'lines_removed': lines_removed,
        }

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.FILE_EDIT,
            payload=payload
        )

        self.enqueue_event(event)

        # No output needed for this hook
        return 0


if __name__ == '__main__':
    hook = AfterFileEditHook()
    sys.exit(hook.run())
