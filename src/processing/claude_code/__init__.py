# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Claude Code processing components.

This module contains all Claude Code telemetry processing:
- Event consumption from Redis Streams
- Raw traces writing to claude_raw_traces table
- JSONL file monitoring
- Session management
"""

from .event_consumer import ClaudeEventConsumer
from .raw_traces_writer import ClaudeRawTracesWriter
from .session_monitor import ClaudeCodeSessionMonitor
from .jsonl_monitor import ClaudeCodeJSONLMonitor

__version__ = "0.1.0"

__all__ = [
    "ClaudeEventConsumer",
    "ClaudeRawTracesWriter",
    "ClaudeCodeSessionMonitor",
    "ClaudeCodeJSONLMonitor",
]
