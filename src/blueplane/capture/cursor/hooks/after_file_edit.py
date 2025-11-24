#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

# DEPRECATED: This hook is no longer installed or used.
# The cursor monitor now only listens for extension session_start and session_end events
# sent directly to Redis. This file is kept for reference only.

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
        # Cursor sends: { "file_path": "...", "edits": [{ "old_string": "...", "new_string": "..." }] }
        file_path = self.input_data.get('file_path', self.input_data.get('file', ''))
        edits = self.input_data.get('edits', [])

        # Calculate line changes from edits
        # Count lines in old_string (removed) and new_string (added) for each edit
        lines_added = 0
        lines_removed = 0

        for edit in edits:
            # Support both 'old_string'/'new_string' and 'oldText'/'newText' (check both)
            old_string = edit.get('old_string', edit.get('oldText', ''))
            new_string = edit.get('new_string', edit.get('newText', ''))

            # Count lines in old_string and new_string
            # Empty string = 0 lines
            # Non-empty string: count newlines + 1 (if doesn't end with newline)
            old_lines = 0
            if old_string:
                old_lines = old_string.count('\n')
                if not old_string.endswith('\n'):
                    old_lines += 1

            new_lines = 0
            if new_string:
                new_lines = new_string.count('\n')
                if not new_string.endswith('\n'):
                    new_lines += 1

            # For replacements: count both removed and added lines
            # For pure additions (old_string empty): only count added
            # For pure deletions (new_string empty): only count removed
            if not old_string:
                # Pure addition
                lines_added += new_lines
            elif not new_string:
                # Pure deletion
                lines_removed += old_lines
            else:
                # Replacement: count both removed and added
                lines_removed += old_lines
                lines_added += new_lines

        # Build event payload
        # Always include lines_added and lines_removed (even if 0)
        # Ensure these are always set as integers (not None)
        payload = {
            'file_extension': Path(file_path).suffix if file_path else None,
            'edit_count': len(edits) if edits else 1,
            'lines_added': int(lines_added) if lines_added is not None else 0,
            'lines_removed': int(lines_removed) if lines_removed is not None else 0,
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
