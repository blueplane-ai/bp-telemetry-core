# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
CursorRawTracesWriter - Fast path writer for cursor_raw_traces table.

Handles batch writes to the cursor_raw_traces table with:
- Field extraction from Cursor events
- zlib compression of full payload
- Batched inserts for performance
- Error handling with logging
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..database.sqlite_client import SQLiteClient
from ..database.writer import SQLiteBatchWriter

logger = logging.getLogger(__name__)


class CursorRawTracesWriter:
    """
    Fast path writer for cursor_raw_traces table.
    Extracts fields and writes compressed events in batches.
    """

    def __init__(self, sqlite_client: SQLiteClient):
        self.sqlite_client = sqlite_client
        self.batch_writer = SQLiteBatchWriter(sqlite_client)

    async def write_events(self, events: List[dict]) -> int:
        """
        Write events to cursor_raw_traces table.

        Args:
            events: List of event dictionaries

        Returns:
            Number of events written
        """
        if not events:
            return 0

        rows = []
        for event in events:
            try:
                row = self._extract_row(event)
                if row:
                    rows.append(row)
            except Exception as e:
                logger.error(f"Error extracting row from event: {e}")
                logger.debug(f"Event type: {type(event)}, Event keys: {list(event.keys()) if isinstance(event, dict) else 'not a dict'}")
                continue

        if not rows:
            return 0

        # Batch insert
        written = self._batch_insert(rows)
        logger.info(f"Wrote {written} events to cursor_raw_traces")
        return written

    def _extract_row(self, event: dict) -> Optional[tuple]:
        """
        Extract row data from event.

        Args:
            event: Event dictionary

        Returns:
            Tuple of values for INSERT statement
        """
        metadata = event.get("metadata", {})
        payload = event.get("payload", {})

        # Handle full_data which can be either a dict or a list
        full_data_raw = payload.get("full_data", {})
        if isinstance(full_data_raw, list):
            # For list data (like interactive.sessions or history.entries),
            # store the list in a wrapper dict for consistent handling
            full_data = {"items": full_data_raw} if full_data_raw else {}
        else:
            full_data = full_data_raw if isinstance(full_data_raw, dict) else {}

        extracted = payload.get("extracted_fields", {})

        # Generate event_id if not present
        event_id = event.get("event_id") or str(uuid.uuid4())

        # Parse timestamp
        timestamp_str = event.get("timestamp")
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except:
                timestamp = datetime.now(timezone.utc)
        else:
            timestamp = datetime.now(timezone.utc)

        # Extract fields
        external_session_id = self._extract_session_id(event, metadata, full_data)
        event_type = event.get("event_type", "unknown")

        # Source location
        storage_level = metadata.get("storage_level", "workspace")
        workspace_hash = metadata.get("workspace_hash", "")
        database_table = metadata.get("database_table", "ItemTable")
        item_key = metadata.get("item_key", "")

        # AI Service fields
        generation_uuid = self._safe_get(full_data, "generationUUID")
        generation_type = self._safe_get(full_data, "type")
        command_type = self._safe_get(full_data, "commandType")

        # Composer/Bubble fields
        composer_id = self._safe_get(full_data, "composerId") or self._safe_get(full_data, "id")
        bubble_id = self._safe_get(full_data, "bubbleId")
        server_bubble_id = self._safe_get(full_data, "serverBubbleId")
        message_type = self._safe_get(full_data, "messageType")
        is_agentic = self._safe_get_bool(full_data, "isAgentic")

        # Content fields
        text_description = self._safe_get(full_data, "textDescription")
        raw_text = self._safe_get(full_data, "text") or self._safe_get(full_data, "rawText")
        rich_text = self._safe_get_json(full_data, "richText")

        # Timing fields (milliseconds)
        unix_ms = self._safe_get_int(full_data, "unixMs")
        created_at = self._safe_get_int(full_data, "createdAt")
        last_updated_at = self._safe_get_int(full_data, "lastUpdatedAt")
        completed_at = self._safe_get_int(full_data, "completedAt")

        timing_info = full_data.get("timingInfo", {})
        client_start_time = self._safe_get_int(timing_info, "clientStartTime")
        client_end_time = self._safe_get_int(timing_info, "clientEndTime")

        # Metrics fields
        lines_added = self._safe_get_int(full_data, "linesAdded")
        lines_removed = self._safe_get_int(full_data, "linesRemoved")
        token_count = self._safe_get_int(full_data, "tokenCountUpUntilHere")

        # Capability/Tool fields
        capabilities_ran = self._safe_get_json(full_data, "capabilitiesRan")
        capability_statuses = self._safe_get_json(full_data, "capabilityStatuses")

        # Context fields
        project_name = self._extract_project_name(metadata, full_data)
        relevant_files = self._safe_get_json(full_data, "relevantFiles")
        selections = self._safe_get_json(full_data, "selections")

        # Status fields
        is_archived = self._safe_get_bool(full_data, "isArchived")
        has_unread_messages = self._safe_get_bool(full_data, "hasUnreadMessages")

        # Model usage fields (extracted from usageData in composerData)
        # The model name is the KEY of the usageData dictionary!
        model_name, model_cost_cents, model_response_count, models_used = self._extract_model_usage(full_data)

        # Compress full event data (use original full_data_raw to preserve lists)
        event_data_compressed = self.batch_writer.compress_event(full_data_raw)

        return (
            event_id,
            external_session_id,
            event_type,
            timestamp.isoformat(),
            storage_level,
            workspace_hash,
            database_table,
            item_key,
            generation_uuid,
            generation_type,
            command_type,
            composer_id,
            bubble_id,
            server_bubble_id,
            message_type,
            is_agentic,
            text_description,
            raw_text,
            rich_text,
            unix_ms,
            created_at,
            last_updated_at,
            completed_at,
            client_start_time,
            client_end_time,
            lines_added,
            lines_removed,
            token_count,
            capabilities_ran,
            capability_statuses,
            project_name,
            relevant_files,
            selections,
            is_archived,
            has_unread_messages,
            model_name,
            model_cost_cents,
            model_response_count,
            models_used,
            event_data_compressed,
        )

    def _batch_insert(self, rows: List[tuple]) -> int:
        """
        Batch insert rows into cursor_raw_traces.

        Args:
            rows: List of row tuples

        Returns:
            Number of rows inserted
        """
        sql = """
        INSERT INTO cursor_raw_traces (
            event_id, external_session_id, event_type, timestamp,
            storage_level, workspace_hash, database_table, item_key,
            generation_uuid, generation_type, command_type,
            composer_id, bubble_id, server_bubble_id, message_type, is_agentic,
            text_description, raw_text, rich_text,
            unix_ms, created_at, last_updated_at, completed_at,
            client_start_time, client_end_time,
            lines_added, lines_removed, token_count_up_until_here,
            capabilities_ran, capability_statuses,
            project_name, relevant_files, selections,
            is_archived, has_unread_messages,
            model_name, model_cost_cents, model_response_count, models_used,
            event_data
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        try:
            with self.sqlite_client.get_connection() as conn:
                conn.executemany(sql, rows)
                conn.commit()
                return len(rows)
        except Exception as e:
            logger.error(f"Error batch inserting cursor_raw_traces: {e}")
            return 0

    def _extract_session_id(self, event: dict, metadata: dict, data: dict) -> Optional[str]:
        """Extract session ID from various possible locations."""
        # Try metadata first
        session_id = metadata.get("external_session_id") or metadata.get("session_id")
        if session_id:
            return session_id

        # Try data
        session_id = data.get("sessionId") or data.get("session_id")
        if session_id:
            return session_id

        return None

    def _extract_project_name(self, metadata: dict, data: dict) -> Optional[str]:
        """Extract project name from various possible locations."""
        # Try metadata
        project_name = metadata.get("project_name") or metadata.get("workspace_name")
        if project_name:
            return project_name

        # Try data
        project_name = data.get("projectName") or data.get("workspaceName")
        if project_name:
            return project_name

        return None

    def _safe_get(self, d: dict, key: str) -> Optional[str]:
        """Safely get string value from dict."""
        value = d.get(key)
        if value is None:
            return None
        return str(value) if not isinstance(value, str) else value

    def _safe_get_int(self, d: dict, key: str) -> Optional[int]:
        """Safely get int value from dict."""
        value = d.get(key)
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _safe_get_bool(self, d: dict, key: str) -> Optional[bool]:
        """Safely get bool value from dict."""
        value = d.get(key)
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        return bool(value)

    def _safe_get_json(self, d: dict, key: str) -> Optional[str]:
        """Safely get JSON string from dict."""
        value = d.get(key)
        if value is None:
            return None
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return None

    def _extract_model_usage(self, data: dict) -> tuple:
        """
        Extract model usage information from composer's usageData field.
        
        The model name is stored as the KEY of the usageData dictionary!
        Example input:
            {"usageData": {"claude-4.5-opus-high-thinking": {"costInCents": 141, "amount": 23}}}
        
        Returns:
            Tuple of (model_name, model_cost_cents, model_response_count, models_used)
        """
        usage_data = data.get("usageData", {})
        
        if not usage_data or not isinstance(usage_data, dict):
            return (None, None, None, None)
        
        # Get all model names (keys of the dict)
        model_names = list(usage_data.keys())
        
        if not model_names:
            return (None, None, None, None)
        
        # Use primary model (first one, or highest cost if multiple)
        if len(model_names) == 1:
            primary_model = model_names[0]
        else:
            # Sort by cost to get the primary model
            primary_model = max(
                model_names,
                key=lambda m: usage_data.get(m, {}).get("costInCents", 0)
            )
        
        primary_stats = usage_data.get(primary_model, {})
        model_cost_cents = primary_stats.get("costInCents")
        model_response_count = primary_stats.get("amount")
        
        # Include all models JSON if multiple
        models_used = json.dumps(model_names) if len(model_names) > 1 else None
        
        return (primary_model, model_cost_cents, model_response_count, models_used)
