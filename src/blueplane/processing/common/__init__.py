# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Common processing utilities shared across platforms.

This module contains utilities used by both Claude and Cursor event consumers:
- Batch management for efficient event processing
- CDC (Change Data Capture) publishing for async workers
"""

from .batch_manager import BatchManager
from .cdc_publisher import CDCPublisher

__all__ = ["BatchManager", "CDCPublisher"]
