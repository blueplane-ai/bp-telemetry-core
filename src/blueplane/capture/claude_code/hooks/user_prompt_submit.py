#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Claude Code UserPromptSubmit Hook

Fires when user submits a prompt.
Receives JSON via stdin with session_id and prompt.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import ClaudeCodeHookBase
from shared.event_schema import EventType, HookType


class UserPromptSubmitHook(ClaudeCodeHookBase):
    """Hook that fires when user submits a prompt."""

    def __init__(self):
        super().__init__(HookType.USER_PROMPT_SUBMIT)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract prompt data from stdin
        prompt = self.input_data.get('prompt', '')

        # Build event payload
        payload = {
            'prompt_length': len(prompt),
            'prompt_text': prompt,  # Full prompt text (privacy-aware)
        }

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.USER_PROMPT,
            payload=payload
        )

        self.enqueue_event(event)

        return 0


if __name__ == '__main__':
    hook = UserPromptSubmitHook()
    sys.exit(hook.run())
