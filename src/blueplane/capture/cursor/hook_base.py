#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Base class for Cursor hooks using stdin/stdout JSON communication.

Cursor hooks communicate via stdio:
- Input: JSON on stdin
- Output: JSON on stdout (for hooks that need responses)
- Errors: Log to stderr (never block)
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


class CursorHookBase:
    """
    Base class for Cursor hooks using stdin/stdout JSON communication.

    All Cursor hooks receive JSON input via stdin with this common schema:
    {
      "conversation_id": "string",
      "generation_id": "string",
      "hook_event_name": "string",
      "workspace_roots": ["<path>"]
    }

    Provides:
    - JSON stdin reading
    - Session ID retrieval from workspace-specific files
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
        self.workspace_root: Optional[str] = None
        self.queue_writer: Optional[MessageQueueWriter] = None
        self.sanitizer: Optional[PrivacySanitizer] = None

        # Read input from stdin
        self._read_input()

        # Extract common fields
        self.conversation_id = self.input_data.get('conversation_id')
        self.generation_id = self.input_data.get('generation_id')
        self.hook_event_name = self.input_data.get('hook_event_name')
        workspace_roots = self.input_data.get('workspace_roots', [])
        if workspace_roots:
            self.workspace_root = workspace_roots[0]

        # Get session ID from workspace-specific file
        self.session_id = self._get_session_id()

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

    def _get_workspace_path(self) -> str:
        """
        Get workspace path.

        Uses workspace_root from input if available, otherwise falls back to cwd.

        Returns:
            Workspace path
        """
        return self.workspace_root if self.workspace_root else os.getcwd()

    def _get_session_id(self) -> Optional[str]:
        """
        Get session ID from workspace-specific session file.

        Tries in order:
        1. CURSOR_SESSION_ID environment variable
        2. Workspace-specific session file (~/.blueplane/cursor-session/<hash>.json)
        3. Legacy global file (~/.cursor-session-env)

        Returns:
            Session ID or None if not set
        """
        # First try environment variable
        session_id = os.environ.get('CURSOR_SESSION_ID')
        if session_id:
            return session_id

        # Compute workspace hash
        workspace_path = self._get_workspace_path()
        workspace_hash = hashlib.sha256(workspace_path.encode()).hexdigest()[:16]

        # Try workspace-specific session file
        workspace_session_file = Path.home() / '.blueplane' / 'cursor-session' / f'{workspace_hash}.json'
        if workspace_session_file.exists():
            try:
                with open(workspace_session_file, 'r') as f:
                    data = json.load(f)
                    session_id = data.get('CURSOR_SESSION_ID')
                    if session_id:
                        return session_id
            except Exception:
                pass

        # Fall back to legacy global file
        legacy_file = Path.home() / '.cursor-session-env'
        if legacy_file.exists():
            try:
                with open(legacy_file, 'r') as f:
                    data = json.load(f)
                    session_id = data.get('CURSOR_SESSION_ID')
                    if session_id:
                        return session_id
            except Exception:
                pass

        return None

    def _get_workspace_hash(self) -> Optional[str]:
        """
        Get workspace hash.

        Returns:
            Workspace hash computed from workspace path
        """
        workspace_path = self._get_workspace_path()
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
        # Get version - use a default if import fails
        # hook_base.py is in ~/.cursor/hooks/, capture module may not be available
        try:
            hooks_dir = Path(__file__).parent
            if str(hooks_dir) not in sys.path:
                sys.path.insert(0, str(hooks_dir))
            from capture import __version__
        except ImportError:
            # Fallback to default version if capture module not available
            __version__ = "0.1.0"

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

        # Add generation ID if available
        if self.generation_id:
            event['metadata']['generation_id'] = self.generation_id

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

            # Write to Redis
            success = self.queue_writer.enqueue(event, 'cursor', self.session_id)
            return success
        except Exception:
            # Silent failure
            return False

    def write_output(self, output: Dict[str, Any]) -> None:
        """
        Write JSON output to stdout.

        Args:
            output: Output dictionary to write
        """
        try:
            print(json.dumps(output), flush=True)
        except Exception as e:
            print(f"Error writing output: {e}", file=sys.stderr)

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
