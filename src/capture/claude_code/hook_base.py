#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Base class for Claude Code hooks using stdin JSON communication.

Claude Code hooks receive JSON input via stdin at key points during development sessions.
"""

import json
import os
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional

# Add shared modules to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.queue_writer import MessageQueueWriter
from shared.event_schema import EventType, HookType
from shared.config import Config
from shared.privacy import PrivacySanitizer


class ClaudeCodeHookBase:
    """
    Base class for Claude Code hooks using stdin JSON communication.

    All Claude Code hooks receive JSON input via stdin with a common schema containing:
    - session_id: Unique session identifier
    - Hook-specific fields (tool_name, prompt, etc.)

    Provides:
    - JSON stdin reading
    - Session ID retrieval
    - Event building and queueing to Redis
    - Privacy sanitization
    - Silent failure mode
    """

    def __init__(self, hook_type: HookType):
        """
        Initialize hook.

        Args:
            hook_type: Type of hook being executed
        """
        self.hook_type = hook_type
        self.input_data: Dict[str, Any] = {}
        self.session_id: Optional[str] = None
        self.queue_writer: Optional[MessageQueueWriter] = None
        self.sanitizer: Optional[PrivacySanitizer] = None

        # Read input from stdin
        self._read_input()

        # Extract common fields
        self.session_id = self.input_data.get('session_id')

        # Initialize queue writer and sanitizer only if we have a session
        if self.session_id:
            try:
                self.queue_writer = MessageQueueWriter()
                config = Config()
                privacy_config = config.privacy
                self.sanitizer = PrivacySanitizer({
                    'opt_out': privacy_config.opt_out
                })
            except Exception:
                # Silent failure - don't block IDE
                pass

    def _read_input(self) -> None:
        """Read JSON input from stdin."""
        try:
            self.input_data = json.load(sys.stdin)
        except Exception as e:
            # Log to stderr (not stdout which is reserved for hook output)
            print(f"Error reading stdin: {e}", file=sys.stderr)
            self.input_data = {}

    def _get_workspace_hash(self) -> Optional[str]:
        """
        Get workspace hash from current working directory.

        Returns:
            Workspace hash computed from workspace path
        """
        workspace_path = os.getcwd()
        return hashlib.sha256(workspace_path.encode()).hexdigest()[:16]

    def build_event(
        self,
        event_type: EventType,
        payload: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build event dictionary.

        Args:
            event_type: Type of event
            payload: Event payload data
            metadata: Additional metadata

        Returns:
            Event dictionary
        """
        # Get version - read from parent __init__.py or use default
        __version__ = "0.1.0"
        try:
            hooks_dir = Path(__file__).parent.parent
            init_path = hooks_dir / "__init__.py"
            if init_path.exists():
                with open(init_path, 'r') as f:
                    for line in f:
                        if line.startswith('__version__'):
                            # Extract version from line like: __version__ = "0.1.0"
                            import re
                            match = re.search(r'["\']([^"\']+)["\']', line)
                            if match:
                                __version__ = match.group(1)
                            break
        except Exception:
            pass  # Use default version

        event = {
            'version': __version__,
            'hook_type': self.hook_type.value,
            'event_type': event_type.value,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'payload': payload,
            'metadata': metadata or {},
        }

        # Add process ID
        event['metadata']['pid'] = os.getpid()

        # Add workspace hash if available
        workspace_hash = self._get_workspace_hash()
        if workspace_hash:
            event['metadata']['workspace_hash'] = workspace_hash

        return event

    def enqueue_event(self, event: Dict[str, Any]) -> bool:
        """
        Enqueue event to message queue after privacy sanitization.

        Args:
            event: Event to enqueue

        Returns:
            True if successful, False otherwise
        """
        if not self.session_id:
            return False

        if not self.queue_writer:
            return False

        try:
            # Apply privacy sanitization
            if self.sanitizer:
                event = self.sanitizer.sanitize_event(event)

            # Write to Redis (note: using 'claude_code' as platform)
            success = self.queue_writer.enqueue(event, 'claude_code', self.session_id)
            return success
        except Exception:
            # Silent failure
            return False

    def execute(self) -> int:
        """
        Execute hook logic. Override in subclasses.

        Returns:
            Exit code (always 0 for silent failure)
        """
        raise NotImplementedError("Subclasses must implement execute()")

    def run(self) -> int:
        """
        Main entry point. Executes hook and handles errors.

        Returns:
            Exit code (always 0 for silent failure)
        """
        try:
            return self.execute()
        except Exception as e:
            # Log to stderr but never fail
            print(f"Hook error: {e}", file=sys.stderr)
            return 0
