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

# Prepared INSERT statement for raw_traces (Cursor)
INSERT_QUERY = """
INSERT INTO raw_traces (
    event_id, session_id, event_type, platform, timestamp,
    workspace_hash, project_name, model, tool_name,
    duration_ms, tokens_used, lines_added, lines_removed,
    event_data
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

# Prepared INSERT statement for claude_raw_traces (Claude Code)
INSERT_CLAUDE_QUERY = """
INSERT INTO claude_raw_traces (
    event_id, session_id, event_type, platform, timestamp,
    uuid, parent_uuid, request_id, agent_id,
    workspace_hash, project_name, is_sidechain, user_type, cwd, version, git_branch,
    message_role, message_model, message_id, message_type, stop_reason, stop_sequence,
    input_tokens, cache_creation_input_tokens, cache_read_input_tokens, output_tokens,
    service_tier, cache_5m_tokens, cache_1h_tokens,
    operation, subtype, level, is_meta,
    summary, leaf_uuid,
    duration_ms, tokens_used, tool_calls_count,
    event_data
) VALUES (
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?,
    ?, ?, ?,
    ?
)
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

        # Extract lines_added (0 is a valid value, so check for None explicitly)
        lines_added = payload.get('lines_added')
        if lines_added is None:
            lines_added = metadata.get('lines_added')
        # Convert to int if present (0 is a valid value)
        if lines_added is not None:
            try:
                lines_added = int(lines_added)
            except (ValueError, TypeError):
                lines_added = None

        # Extract lines_removed (0 is a valid value, so check for None explicitly)
        lines_removed = payload.get('lines_removed')
        if lines_removed is None:
            lines_removed = metadata.get('lines_removed')
        # Convert to int if present (0 is a valid value)
        if lines_removed is not None:
            try:
                lines_removed = int(lines_removed)
            except (ValueError, TypeError):
                lines_removed = None

        return {
            'event_id': event.get('event_id', ''),
            'session_id': event.get('session_id', ''),
            'event_type': event.get('event_type', ''),
            'platform': event.get('platform', ''),
            'timestamp': event.get('timestamp', ''),
            'workspace_hash': metadata.get('workspace_hash'),
            'project_name': metadata.get('project_name'),
            'model': payload.get('model') or metadata.get('model'),
            'tool_name': payload.get('tool') or payload.get('tool_name') or metadata.get('tool_name'),
            'duration_ms': payload.get('duration_ms') or metadata.get('duration_ms'),
            'tokens_used': payload.get('tokens_used') or metadata.get('tokens_used'),
            'lines_added': lines_added,
            'lines_removed': lines_removed,
        }

    def write_batch_sync(self, events: List[Dict[str, Any]]) -> List[int]:
        """
        Synchronous batch write.

        This is the main write method used by the fast path consumer.
        All writes are synchronous for simplicity and performance.

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
                fields['project_name'],
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
            # Use a single connection for both insert and sequence retrieval
            with self.client.get_connection() as conn:
                # Insert batch
                conn.executemany(INSERT_QUERY, rows)

                # Get sequence numbers immediately after insert (same connection)
                cursor = conn.execute("SELECT last_insert_rowid()")
                last_rowid = cursor.fetchone()[0]

                # Calculate sequence numbers: if we inserted N rows, sequences are
                # last_rowid - (N-1) through last_rowid
                sequences = list(range(last_rowid - len(rows) + 1, last_rowid + 1))

                # Commit the transaction
                conn.commit()

            logger.debug(f"Wrote batch of {len(events)} events, sequences: {sequences[0]}-{sequences[-1]}")
            
            return sequences

        except Exception as e:
            logger.error(f"Failed to write batch: {e}", exc_info=True)
            raise

    # Note: async write_batch() method removed - fast path consumer now uses
    # synchronous write_batch_sync() directly for simplicity and performance.
    # If async support is needed in the future (e.g., for slow path workers),
    # this method can be restored.

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

    # ==================== Claude Code Methods ====================

    def _extract_claude_indexed_fields(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract indexed fields from Claude Code JSONL event.

        Maps JSONL schema fields to database columns for claude_raw_traces table.

        Args:
            event: Full event dictionary

        Returns:
            Dictionary with extracted fields
        """
        payload = event.get('payload', {})
        entry_data = payload.get('entry_data', {})
        metadata = event.get('metadata', {})

        # Extract message data (for user/assistant events)
        message = entry_data.get('message', {})
        usage = message.get('usage', {}) if isinstance(message, dict) else {}
        cache_creation = usage.get('cache_creation', {}) if isinstance(usage, dict) else {}

        # Calculate total tokens
        input_tokens = usage.get('input_tokens', 0)
        output_tokens = usage.get('output_tokens', 0)
        tokens_used = input_tokens + output_tokens if (input_tokens or output_tokens) else None

        # Count tool calls
        tool_calls_count = 0
        if isinstance(message, dict):
            content = message.get('content', [])
            if isinstance(content, list):
                tool_calls_count = sum(1 for item in content if isinstance(item, dict) and item.get('type') == 'tool_use')

        return {
            'event_id': entry_data.get('uuid', ''),
            'session_id': entry_data.get('sessionId', event.get('session_id', '')),
            'event_type': entry_data.get('type', ''),
            'platform': 'claude_code',
            'timestamp': entry_data.get('timestamp', event.get('timestamp', '')),

            # Claude Code specific
            'uuid': entry_data.get('uuid'),
            'parent_uuid': entry_data.get('parentUuid'),
            'request_id': entry_data.get('requestId'),
            'agent_id': entry_data.get('agentId'),

            # Context
            'workspace_hash': metadata.get('workspace_hash'),
            'project_name': metadata.get('project_name') or entry_data.get('projectName'),
            'is_sidechain': entry_data.get('isSidechain', False),
            'user_type': entry_data.get('userType'),
            'cwd': entry_data.get('cwd'),
            'version': entry_data.get('version'),
            'git_branch': entry_data.get('gitBranch'),

            # Message fields
            'message_role': message.get('role') if isinstance(message, dict) else None,
            'message_model': message.get('model') if isinstance(message, dict) else None,
            'message_id': message.get('id') if isinstance(message, dict) else None,
            'message_type': message.get('type') if isinstance(message, dict) else None,
            'stop_reason': message.get('stop_reason') if isinstance(message, dict) else None,
            'stop_sequence': message.get('stop_sequence') if isinstance(message, dict) else None,

            # Token usage
            'input_tokens': usage.get('input_tokens'),
            'cache_creation_input_tokens': usage.get('cache_creation_input_tokens'),
            'cache_read_input_tokens': usage.get('cache_read_input_tokens'),
            'output_tokens': usage.get('output_tokens'),
            'service_tier': usage.get('service_tier'),
            'cache_5m_tokens': cache_creation.get('ephemeral_5m_input_tokens'),
            'cache_1h_tokens': cache_creation.get('ephemeral_1h_input_tokens'),

            # Queue operation
            'operation': entry_data.get('operation'),

            # System event
            'subtype': entry_data.get('subtype'),
            'level': entry_data.get('level'),
            'is_meta': entry_data.get('isMeta', False),

            # Summary
            'summary': entry_data.get('summary'),
            'leaf_uuid': entry_data.get('leafUuid'),

            # Metrics
            'duration_ms': payload.get('duration_ms'),
            'tokens_used': tokens_used,
            'tool_calls_count': tool_calls_count if tool_calls_count > 0 else None,
        }

    def write_claude_batch_sync(self, events: List[Dict[str, Any]]) -> List[int]:
        """
        Synchronous batch write for Claude Code events.

        Writes to claude_raw_traces table with Claude-specific fields.

        Args:
            events: List of Claude Code event dictionaries

        Returns:
            List of sequence numbers for written events
        """
        if not events:
            return []

        # Prepare batch data
        rows = []
        for event in events:
            # Extract indexed fields
            fields = self._extract_claude_indexed_fields(event)

            # Compress full event
            compressed_data = self._compress_event(event)

            # Build row tuple (39 fields)
            row = (
                fields['event_id'],
                fields['session_id'],
                fields['event_type'],
                fields['platform'],
                fields['timestamp'],
                fields['uuid'],
                fields['parent_uuid'],
                fields['request_id'],
                fields['agent_id'],
                fields['workspace_hash'],
                fields['project_name'],
                fields['is_sidechain'],
                fields['user_type'],
                fields['cwd'],
                fields['version'],
                fields['git_branch'],
                fields['message_role'],
                fields['message_model'],
                fields['message_id'],
                fields['message_type'],
                fields['stop_reason'],
                fields['stop_sequence'],
                fields['input_tokens'],
                fields['cache_creation_input_tokens'],
                fields['cache_read_input_tokens'],
                fields['output_tokens'],
                fields['service_tier'],
                fields['cache_5m_tokens'],
                fields['cache_1h_tokens'],
                fields['operation'],
                fields['subtype'],
                fields['level'],
                fields['is_meta'],
                fields['summary'],
                fields['leaf_uuid'],
                fields['duration_ms'],
                fields['tokens_used'],
                fields['tool_calls_count'],
                compressed_data,
            )
            rows.append(row)

        # Batch insert
        try:
            with self.client.get_connection() as conn:
                # Insert batch
                conn.executemany(INSERT_CLAUDE_QUERY, rows)

                # Get sequence numbers
                cursor = conn.execute("SELECT last_insert_rowid()")
                last_rowid = cursor.fetchone()[0]
                sequences = list(range(last_rowid - len(rows) + 1, last_rowid + 1))

                # Commit
                conn.commit()

            logger.debug(f"Wrote Claude Code batch of {len(events)} events, sequences: {sequences[0]}-{sequences[-1]}")

            return sequences

        except Exception as e:
            logger.error(f"Failed to write Claude Code batch: {e}", exc_info=True)
            raise

