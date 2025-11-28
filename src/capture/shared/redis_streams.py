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

# Main event stream for all telemetry events from hooks/monitors
# Used by: hooks, monitors → event consumers
TELEMETRY_EVENTS_STREAM = "telemetry:events"

# Message queue for asynchronous event processing
# Used by: JSONL monitor, transcript monitor → event processors
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
    "events": TELEMETRY_EVENTS_STREAM,
    "message_queue": TELEMETRY_MESSAGE_QUEUE_STREAM,
    "dlq": TELEMETRY_DLQ_STREAM,
    "cdc": CDC_EVENTS_STREAM,
}


def get_stream_name(stream_type: str) -> str:
    """
    Get the full stream name for a given stream type.

    Args:
        stream_type: Stream type identifier (e.g., "events", "message_queue", "dlq", "cdc")

    Returns:
        Full stream name (e.g., "telemetry:events")

    Raises:
        ValueError: If stream_type is not recognized
    """
    if stream_type not in STREAM_NAME_MAP:
        raise ValueError(
            f"Unknown stream type: {stream_type}. "
            f"Valid types: {', '.join(STREAM_NAME_MAP.keys())}"
        )
    return STREAM_NAME_MAP[stream_type]
