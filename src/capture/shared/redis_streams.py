# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Redis Stream Name Constants.

Centralized definitions for all Redis stream names used across the telemetry system.
This avoids hardcoded string values and confusion about stream naming.
"""

# =============================================================================
# TELEMETRY STREAMS
# =============================================================================

# Primary event stream for all telemetry events
# This is the central message queue for real-time telemetry event processing.
#
# Producers (write to this stream):
#   - HTTP endpoint: Claude Code hooks (session_start, session_end, tool_use, etc.)
#   - JSONL monitor: Claude Code transcript trace events
#   - Database monitors: Cursor workspace database change events
#
# Consumers (read from this stream):
#   - ClaudeEventConsumer: Processes Claude Code events → claude_raw_traces table
#   - CursorEventConsumer: Processes Cursor events → cursor_raw_traces table
#   - Session monitors: Track active Claude Code and Cursor sessions
TELEMETRY_MESSAGE_QUEUE_STREAM = "telemetry:message_queue"

# Dead Letter Queue for failed messages
# Used by: event consumers (for messages that fail max retries)
TELEMETRY_DLQ_STREAM = "telemetry:dlq"

# =============================================================================
# CDC (Change Data Capture) STREAMS
# =============================================================================

# CDC events stream for database change notifications
# Used by: fast path writers → slow path workers
CDC_EVENTS_STREAM = "cdc:events"

# =============================================================================
# STREAM NAME MAPPINGS
# =============================================================================

# Map stream types to their full names (for config lookup)
STREAM_NAME_MAP = {
    "message_queue": TELEMETRY_MESSAGE_QUEUE_STREAM,
    "dlq": TELEMETRY_DLQ_STREAM,
    "cdc": CDC_EVENTS_STREAM,
}


def get_stream_name(stream_type: str) -> str:
    """
    Get the full stream name for a given stream type.

    Args:
        stream_type: Stream type identifier (e.g., "message_queue", "dlq", "cdc")

    Returns:
        Full stream name (e.g., "telemetry:message_queue")

    Raises:
        ValueError: If stream_type is not recognized
    """
    if stream_type not in STREAM_NAME_MAP:
        raise ValueError(
            f"Unknown stream type: {stream_type}. "
            f"Valid types: {', '.join(STREAM_NAME_MAP.keys())}"
        )
    return STREAM_NAME_MAP[stream_type]
