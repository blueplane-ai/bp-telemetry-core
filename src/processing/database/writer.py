# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Generic database writer utilities.

Provides compression and basic database operations.
Platform-specific writers should be in their respective modules:
- claude/raw_traces_writer.py for Claude Code
- cursor/raw_traces_writer.py for Cursor
"""

import json
import zlib
import logging
from typing import Dict, Any

from .sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)

# Compression level (6 provides good balance: 7-10x compression ratio)
COMPRESSION_LEVEL = 6


class SQLiteBatchWriter:
    """
    Generic batch writer utilities.

    Provides shared compression functionality for platform-specific writers.
    Platform-specific field extraction and writes should be in dedicated modules.
    """

    def __init__(self, client: SQLiteClient):
        """
        Initialize batch writer.

        Args:
            client: SQLiteClient instance
        """
        self.client = client

    def compress_event(self, event: Dict[str, Any]) -> bytes:
        """
        Compress event data using zlib.

        Args:
            event: Event dictionary

        Returns:
            Compressed bytes
        """
        json_str = json.dumps(event, separators=(',', ':'))
        return zlib.compress(json_str.encode('utf-8'), COMPRESSION_LEVEL)
