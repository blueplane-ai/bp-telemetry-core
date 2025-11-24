#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Claude Code PreCompact Hook

Fires before context window compaction.
Receives JSON via stdin with session_id, trigger, and transcript_path.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import ClaudeCodeHookBase
from shared.event_schema import EventType, HookType


class PreCompactHook(ClaudeCodeHookBase):
    """Hook that fires before context compaction."""

    def __init__(self):
        super().__init__(HookType.PRE_COMPACT)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract compaction data from stdin
        trigger = self.input_data.get('trigger', 'unknown')
        transcript_path = self.input_data.get('transcript_path')
        custom_instructions = self.input_data.get('custom_instructions')

        # Build event payload
        payload = {
            'trigger': trigger,
        }

        if transcript_path:
            payload['has_transcript'] = True
            # Store path hash instead of full path for privacy
            import hashlib
            payload['transcript_path_hash'] = hashlib.sha256(str(transcript_path).encode()).hexdigest()[:16]

        if custom_instructions:
            payload['has_custom_instructions'] = True
            payload['custom_instructions_length'] = len(custom_instructions)

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.CONTEXT_COMPACT,
            payload=payload
        )

        self.enqueue_event(event)

        return 0


if __name__ == '__main__':
    hook = PreCompactHook()
    sys.exit(hook.run())
