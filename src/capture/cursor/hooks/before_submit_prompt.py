#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

# DEPRECATED: This hook is no longer installed or used.
# The cursor monitor now only listens for extension session_start and session_end events
# sent directly to Redis. This file is kept for reference only.

"""
Cursor beforeSubmitPrompt Hook (stdin/stdout)

Fires when user submits a prompt, before backend request.
Receives JSON via stdin, outputs JSON via stdout.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import CursorHookBase
from shared.event_schema import EventType, HookType


class BeforeSubmitPromptHook(CursorHookBase):
    """Hook that fires before prompt submission."""

    def __init__(self):
        super().__init__(HookType.BEFORE_SUBMIT_PROMPT)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract prompt data from stdin
        prompt = self.input_data.get('prompt', '')
        attachments = self.input_data.get('attachments', [])

        # Build event payload
        payload = {
            'prompt_length': len(prompt),
            'prompt_text': prompt,  # Full prompt text (privacy-aware)
            'attachment_count': len(attachments),
        }

        # Add attachment types
        if attachments:
            attachment_types = [att.get('type') for att in attachments]
            payload['attachment_types'] = attachment_types
            # Optionally capture attachment details
            payload['attachments'] = attachments

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.USER_PROMPT,
            payload=payload
        )

        self.enqueue_event(event)

        # Always allow prompt submission (continue: true)
        self.write_output({"continue": True})

        return 0


if __name__ == '__main__':
    hook = BeforeSubmitPromptHook()
    sys.exit(hook.run())
