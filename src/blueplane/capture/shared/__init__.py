# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Shared capture components used by all platforms.
"""

from .queue_writer import MessageQueueWriter
from .event_schema import EventSchema, EventType, Platform
from .privacy import PrivacySanitizer
from .config import Config

__all__ = [
    "MessageQueueWriter",
    "EventSchema",
    "EventType",
    "Platform",
    "PrivacySanitizer",
    "Config",
]
