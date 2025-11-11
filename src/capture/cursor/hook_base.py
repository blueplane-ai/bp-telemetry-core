# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Base utilities for Cursor hooks.

Provides common functionality for all Cursor hook scripts.
"""

import os
import sys
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path


# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.queue_writer import MessageQueueWriter
from shared.event_schema import Platform, HookType, EventType
from shared.privacy import PrivacySanitizer
from shared.config import Config


def str_to_bool(value: str) -> bool:
    """
    Convert string to boolean properly.

    Args:
        value: String value ("true", "false", "1", "0", etc.)

    Returns:
        Boolean value

    Note:
        This is needed because argparse type=bool doesn't work correctly.
        It treats any non-empty string as True.
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lower_value = value.lower().strip()
        if lower_value in ('true', '1', 'yes', 'on'):
            return True
        elif lower_value in ('false', '0', 'no', 'off', ''):
            return False
        else:
            raise ValueError(f"Cannot convert '{value}' to boolean")

    raise ValueError(f"Expected string or bool, got {type(value)}")


class CursorHookBase:
    """
    Base class for Cursor hooks.

    Provides common functionality:
    - Environment variable reading
    - Session ID retrieval
    - Event building
    - Message queue integration
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
        self.session_id = self._get_session_id()
        self.workspace_root = None
        self.queue_writer = None
        self.sanitizer = None

        # Only initialize queue writer and sanitizer if we have a session
        if self.session_id:
            try:
                self.queue_writer = MessageQueueWriter()
                # Initialize privacy sanitizer with config
                config = Config()
                privacy_config = config.privacy
                self.sanitizer = PrivacySanitizer({
                    'opt_out': privacy_config.opt_out
                })
            except Exception:
                # Silent failure - don't block IDE
                pass

    def _get_workspace_path(self) -> str:
        """
        Get workspace path.

        Uses workspace_root if provided by Cursor, otherwise falls back to cwd.

        Returns:
            Workspace path
        """
        return self.workspace_root if self.workspace_root else os.getcwd()

    def _get_session_id(self) -> Optional[str]:
        """
        Get session ID from environment variable or extension file.

        Tries multiple sources in order:
        1. CURSOR_SESSION_ID environment variable
        2. Workspace-specific session file (~/.blueplane/cursor-session/<hash>.json)
        3. Legacy global file (~/.cursor-session-env)
        4. VSCode global storage (platform-specific paths)

        Returns:
            Session ID or None if not set
        """
        # First try environment variable (if extension can set it)
        session_id = os.environ.get('CURSOR_SESSION_ID')
        if session_id:
            return session_id

        # Try reading from extension-written file
        import json
        from pathlib import Path
        import hashlib

        # Try workspace-specific session file first
        # Use workspace_root argument if available, otherwise fall back to cwd
        workspace_path = self._get_workspace_path()
        workspace_hash = hashlib.sha256(workspace_path.encode()).hexdigest()[:16]

        workspace_session_file = Path.home() / '.blueplane' / 'cursor-session' / f'{workspace_hash}.json'
        if workspace_session_file.exists():
            try:
                with open(workspace_session_file, 'r') as f:
                    data = json.load(f)
                    session_id = data.get('CURSOR_SESSION_ID')
                    if session_id:
                        return session_id
            except Exception:
                # Silent failure - continue to fallback
                pass

        # Fall back to legacy global file and other locations
        possible_paths = [
            Path.home() / '.cursor-session-env',
            Path.home() / '.vscode' / '.cursor-session-env',
            Path.home() / 'Library' / 'Application Support' / 'Cursor' / '.cursor-session-env',
            Path.home() / '.config' / 'Cursor' / '.cursor-session-env',
            Path.home() / 'AppData' / 'Roaming' / 'Cursor' / '.cursor-session-env',
        ]

        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                        session_id = data.get('CURSOR_SESSION_ID')
                        if session_id:
                            return session_id
                except Exception:
                    # Silent failure - continue to next path
                    continue

        return None

    def _get_workspace_hash(self) -> Optional[str]:
        """
        Get workspace hash from environment variable or extension file.

        Returns:
            Workspace hash or None if not set
        """
        # First try environment variable
        workspace_hash = os.environ.get('CURSOR_WORKSPACE_HASH')
        if workspace_hash:
            return workspace_hash

        # Try reading from extension file (same as session ID)
        import json
        from pathlib import Path
        import hashlib

        # Try workspace-specific session file first
        # Use workspace_root argument if available, otherwise fall back to cwd
        workspace_path = self._get_workspace_path()
        computed_hash = hashlib.sha256(workspace_path.encode()).hexdigest()[:16]

        workspace_session_file = Path.home() / '.blueplane' / 'cursor-session' / f'{computed_hash}.json'
        if workspace_session_file.exists():
            try:
                with open(workspace_session_file, 'r') as f:
                    data = json.load(f)
                    workspace_hash = data.get('CURSOR_WORKSPACE_HASH')
                    if workspace_hash:
                        return workspace_hash
            except Exception:
                pass

        # Fall back to legacy global file and other locations
        possible_paths = [
            Path.home() / '.cursor-session-env',
            Path.home() / '.vscode' / '.cursor-session-env',
            Path.home() / 'Library' / 'Application Support' / 'Cursor' / '.cursor-session-env',
            Path.home() / '.config' / 'Cursor' / '.cursor-session-env',
            Path.home() / 'AppData' / 'Roaming' / 'Cursor' / '.cursor-session-env',
        ]

        for path in possible_paths:
            if path.exists():
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                        workspace_hash = data.get('CURSOR_WORKSPACE_HASH')
                        if workspace_hash:
                            return workspace_hash
                except Exception:
                    continue

        return None

    def parse_args(self, args_spec: Dict[str, Dict[str, Any]]) -> argparse.Namespace:
        """
        Parse command-line arguments.

        Automatically saves workspace_root to self.workspace_root if present.

        Args:
            args_spec: Dictionary of argument specifications
                      Format: {arg_name: {type: str, help: str, default: None}}

        Returns:
            Parsed arguments namespace
        """
        parser = argparse.ArgumentParser(description=f"Cursor {self.hook_type.value} hook")

        for arg_name, spec in args_spec.items():
            arg_type = spec.get('type', str)
            arg_help = spec.get('help', '')
            arg_default = spec.get('default')

            parser.add_argument(
                f'--{arg_name.replace("_", "-")}',
                dest=arg_name,
                type=arg_type,
                help=arg_help,
                default=arg_default
            )

        args = parser.parse_args()

        # Save workspace_root for hash computation if provided
        if hasattr(args, 'workspace_root') and args.workspace_root:
            self.workspace_root = args.workspace_root

        return args

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
        # Import version from package
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from capture import __version__

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
            event: Event dictionary

        Returns:
            True on success, False on failure (silent)
        """
        if not self.session_id:
            # No session active - skip silently
            return False

        if not self.queue_writer:
            # Queue writer not initialized - skip silently
            return False

        try:
            # Sanitize event before enqueueing
            sanitized_event = event
            if self.sanitizer:
                sanitized_event = self.sanitizer.sanitize_event(event)

            return self.queue_writer.enqueue(
                event=sanitized_event,
                platform=Platform.CURSOR.value,
                session_id=self.session_id
            )
        except Exception:
            # Silent failure - never block IDE
            return False

    def execute(self) -> int:
        """
        Execute hook (to be implemented by subclasses).

        Returns:
            Exit code (always 0 for hooks)
        """
        raise NotImplementedError("Subclasses must implement execute()")

    def run(self) -> int:
        """
        Run hook with error handling.

        Returns:
            Always returns 0 (success) - never fails
        """
        try:
            return self.execute()
        except Exception:
            # Silent failure - always return success
            return 0
