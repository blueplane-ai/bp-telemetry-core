#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Session Event Sender

Sends session start/end events to the telemetry queue.
Called by the Cursor extension on activation/deactivation.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add shared modules to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.queue_writer import MessageQueueWriter
from shared.event_schema import EventType


def send_session_event(event_type: str, workspace_path: str, session_id: str, workspace_hash: str) -> bool:
    """
    Send session start or end event.

    Args:
        event_type: Either 'start' or 'end'
        workspace_path: Path to the workspace
        session_id: Session ID
        workspace_hash: Workspace hash

    Returns:
        True if successful, False otherwise
    """
    # Get version
    from capture import __version__

    # Build event
    event = {
        'version': __version__,
        'hook_type': 'session',
        'event_type': f'session_{event_type}',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'payload': {
            'workspace_path': workspace_path,
            'session_id': session_id,
            'workspace_hash': workspace_hash,
        },
        'metadata': {
            'pid': os.getpid(),
            'workspace_hash': workspace_hash,
            'platform': 'cursor',
        },
    }

    # Write to queue
    queue_writer = MessageQueueWriter()
    success = queue_writer.enqueue(event, 'cursor', session_id)

    return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Send session event to telemetry queue')
    parser.add_argument('event_type', choices=['start', 'end'], help='Event type (start or end)')
    parser.add_argument('--workspace-path', required=True, help='Workspace path')
    parser.add_argument('--session-id', required=True, help='Session ID')
    parser.add_argument('--workspace-hash', required=True, help='Workspace hash')

    args = parser.parse_args()

    # Send event (silent failure)
    try:
        success = send_session_event(
            args.event_type,
            args.workspace_path,
            args.session_id,
            args.workspace_hash
        )
        # Always exit 0 to not block extension
        sys.exit(0)
    except Exception:
        # Silent failure
        sys.exit(0)


if __name__ == '__main__':
    main()
