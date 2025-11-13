#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Cursor afterAgentResponse Hook (stdin/stdout)

Fires after agent completes an assistant message.
Receives JSON via stdin.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hook_base import CursorHookBase
from shared.event_schema import EventType, HookType


class AfterAgentResponseHook(CursorHookBase):
    """Hook that fires after agent response."""

    def __init__(self):
        super().__init__(HookType.AFTER_AGENT_RESPONSE)

    def execute(self) -> int:
        """Execute hook logic."""
        # Extract response data from stdin
        text = self.input_data.get('text', '')
        model = self.input_data.get('model', '')
        tokens = self.input_data.get('tokens', 0)
        duration_ms = self.input_data.get('duration_ms', 0)

        # Build event payload
        payload = {
            'response_length': len(text),
            'response_text': text,  # Full response text (privacy-aware)
            'model': model,
            'tokens_used': tokens,  # Standardized field name
            'duration_ms': duration_ms,
        }

        # Build and enqueue event
        event = self.build_event(
            event_type=EventType.ASSISTANT_RESPONSE,
            payload=payload
        )

        self.enqueue_event(event)

        # No output needed for this hook
        return 0


if __name__ == '__main__':
    hook = AfterAgentResponseHook()
    sys.exit(hook.run())
