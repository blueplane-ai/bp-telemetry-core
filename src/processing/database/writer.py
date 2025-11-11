# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
SQLite batch writer for raw traces.

Implements high-performance batch inserts with zlib compression.
Target: <8ms P95 latency for 100 events.
"""

import json
import zlib
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

from .sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)

# Compression level (6 provides good balance: 7-10x compression ratio)
COMPRESSION_LEVEL = 6

# Prepared INSERT statement for raw_traces
INSERT_QUERY = """
INSERT INTO raw_traces (
    event_id, session_id, event_type, platform, timestamp,
    workspace_hash, model, tool_name,
    duration_ms, tokens_used, lines_added, lines_removed,
    event_data
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class SQLiteBatchWriter:
    """
    Batch writer for raw traces with zlib compression.
    
    Features:
    - Batch inserts with executemany() for performance
    - zlib compression (level 6) for event_data BLOB
    - Extracts indexed fields from event JSON
    - Zero reads - pure write path
    """

    def __init__(self, client: SQLiteClient):
        """
        Initialize batch writer.

        Args:
            client: SQLiteClient instance
        """
        self.client = client

    def _compress_event(self, event: Dict[str, Any]) -> bytes:
        """
        Compress event data using zlib.

        Args:
            event: Event dictionary

        Returns:
            Compressed bytes
        """
        json_str = json.dumps(event, separators=(',', ':'))
        return zlib.compress(json_str.encode('utf-8'), COMPRESSION_LEVEL)

    def _extract_indexed_fields(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract indexed fields from event for fast filtering.

        Args:
            event: Full event dictionary

        Returns:
            Dictionary with extracted fields
        """
        metadata = event.get('metadata', {})
        payload = event.get('payload', {})

        return {
            'event_id': event.get('event_id', ''),
            'session_id': event.get('session_id', ''),
            'event_type': event.get('event_type', ''),
            'platform': event.get('platform', ''),
            'timestamp': event.get('timestamp', ''),
            'workspace_hash': metadata.get('workspace_hash'),
            'model': payload.get('model') or metadata.get('model'),
            'tool_name': payload.get('tool') or payload.get('tool_name') or metadata.get('tool_name'),
            'duration_ms': payload.get('duration_ms') or metadata.get('duration_ms'),
            'tokens_used': payload.get('tokens_used') or metadata.get('tokens_used'),
            'lines_added': payload.get('lines_added') or metadata.get('lines_added'),
            'lines_removed': payload.get('lines_removed') or metadata.get('lines_removed'),
        }

    async def write_batch(self, events: List[Dict[str, Any]]) -> List[int]:
        """
        Write batch of events to SQLite with compression.

        This is the fast path - zero reads, pure writes.
        Target: <8ms P95 for 100 events.

        Args:
            events: List of event dictionaries

        Returns:
            List of sequence numbers for written events
        """
        if not events:
            return []

        # Prepare batch data
        rows = []
        for event in events:
            # Extract indexed fields
            fields = self._extract_indexed_fields(event)

            # Compress full event
            compressed_data = self._compress_event(event)

            # Build row tuple
            row = (
                fields['event_id'],
                fields['session_id'],
                fields['event_type'],
                fields['platform'],
                fields['timestamp'],
                fields['workspace_hash'],
                fields['model'],
                fields['tool_name'],
                fields['duration_ms'],
                fields['tokens_used'],
                fields['lines_added'],
                fields['lines_removed'],
                compressed_data,
            )
            rows.append(row)

        # Batch insert
        try:
            self.client.executemany(INSERT_QUERY, rows)

            # Get sequence numbers (last_insert_rowid() gives us the last one)
            # For batch, we need to query the last N rows
            with self.client.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT sequence FROM raw_traces ORDER BY sequence DESC LIMIT ?",
                    (len(events),)
                )
                sequences = [row[0] for row in cursor.fetchall()]
                sequences.reverse()  # Return in insertion order

            logger.debug(f"Wrote batch of {len(events)} events, sequences: {sequences[0]}-{sequences[-1]}")
            return sequences

        except Exception as e:
            logger.error(f"Failed to write batch: {e}")
            raise

    def get_by_sequence(self, sequence: int) -> Optional[Dict[str, Any]]:
        """
        Read single event by sequence number (used by slow path workers).

        Args:
            sequence: Sequence number

        Returns:
            Decompressed event dictionary or None if not found
        """
        with self.client.get_connection() as conn:
            cursor = conn.execute(
                "SELECT event_data FROM raw_traces WHERE sequence = ?",
                (sequence,)
            )
            row = cursor.fetchone()
            if not row:
                return None

            # Decompress and parse
            compressed_data = row[0]
            json_str = zlib.decompress(compressed_data).decode('utf-8')
            return json.loads(json_str)

