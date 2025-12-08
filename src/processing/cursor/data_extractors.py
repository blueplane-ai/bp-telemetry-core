# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Data Extractors for Cursor telemetry.

Handles extraction of:
- Nested composer conversations with bubbles
- Background composer data
- Agent mode sessions
- AI generations and prompts
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ComposerDataExtractor:
    """
    Extracts complete composer data including nested bubbles.
    Handles both workspace metadata and global conversation data.
    """

    def extract_composer_events(
        self,
        composer_data: dict,
        workspace_hash: str,
        storage_level: str,
        database_table: str,
        item_key: str,
        external_session_id: Optional[str] = None
    ) -> List[dict]:
        """
        Extract all events from a composer conversation.
        Returns list of events: 1 composer event + N bubble events.
        """
        events = []

        # Extract composer-level event
        composer_event = self._extract_composer_event(
            composer_data,
            workspace_hash,
            storage_level,
            database_table,
            item_key,
            external_session_id
        )
        events.append(composer_event)

        # Extract bubble events from conversation
        conversation = (
            composer_data.get("conversation", []) or
            composer_data.get("fullConversationHeadersOnly", []) or
            []
        )

        for bubble in conversation:
            bubble_event = self._extract_bubble_event(
                bubble,
                composer_data.get("composerId"),
                workspace_hash,
                storage_level,
                database_table,
                item_key,
                external_session_id
            )
            events.append(bubble_event)

        # Extract capability events if present
        capabilities = composer_data.get("capabilitiesRan", {})
        if isinstance(capabilities, dict):
            for cap_name, cap_data in capabilities.items():
                cap_event = self._extract_capability_event(
                    cap_name,
                    cap_data,
                    composer_data.get("composerId"),
                    workspace_hash,
                    storage_level,
                    database_table,
                    item_key,
                    external_session_id
                )
                events.append(cap_event)

        return events

    def _extract_composer_event(
        self,
        data: dict,
        workspace_hash: str,
        storage_level: str,
        database_table: str,
        item_key: str,
        external_session_id: Optional[str] = None
    ) -> dict:
        """
        Extract composer-level fields.

        Note: Field availability varies by storage level and Cursor version:
        - globalStorage: Has unifiedMode, forceMode, status, tokenCount (newer versions)
        - globalStorage: Does NOT have lastUpdatedAt, isArchived, hasUnreadMessages,
          totalLinesAdded, totalLinesRemoved, or conversation array
        - workspace ItemTable: May have different field set

        All fields use .get() for null-safety.
        """
        metadata = {
            "storage_level": storage_level,
            "workspace_hash": workspace_hash,
            "database_table": database_table,
            "item_key": item_key,
            "source": "composer_extractor",
        }
        if external_session_id:
            metadata["external_session_id"] = external_session_id

        return {
            "version": "0.1.0",
            "hook_type": "DatabaseTrace",
            "event_type": "composer",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": "cursor",
            "metadata": metadata,
            "payload": {
                "extracted_fields": {
                    "composer_id": data.get("composerId"),
                    "created_at": data.get("createdAt"),
                    "last_updated_at": data.get("lastUpdatedAt"),  # May not exist in globalStorage
                    "is_agentic": data.get("isAgentic"),
                    "is_archived": data.get("isArchived"),  # May not exist in globalStorage
                    "has_unread_messages": data.get("hasUnreadMessages"),  # May not exist in globalStorage
                    "conversation_count": len(
                        data.get("conversation", []) or
                        data.get("fullConversationHeadersOnly", []) or
                        []
                    ),
                    "lines_added": data.get("totalLinesAdded") or data.get("linesAdded"),  # May not exist
                    "lines_removed": data.get("totalLinesRemoved") or data.get("linesRemoved"),  # May not exist
                    # Additional fields from globalStorage
                    "unified_mode": data.get("unifiedMode"),
                    "force_mode": data.get("forceMode"),
                    "status": data.get("status"),
                    "token_count": data.get("tokenCount"),
                    # Model usage from usageData field (model name is the key!)
                    # Example: {"claude-4.5-opus-high-thinking": {"costInCents": 141, "amount": 23}}
                    **self._extract_model_usage(data.get("usageData", {})),
                },
                "full_data": data
            }
        }

    def _extract_model_usage(self, usage_data: Optional[dict]) -> dict:
        """
        Extract model usage information from composer's usageData field.
        
        The model name is stored as the KEY of the usageData dictionary!
        Example input:
            {"claude-4.5-opus-high-thinking": {"costInCents": 141, "amount": 23}}
        
        Returns:
            dict with model_name, model_cost_cents, model_response_count, models_used
        """
        if not usage_data or not isinstance(usage_data, dict):
            return {
                "model_name": None,
                "model_cost_cents": None,
                "model_response_count": None,
                "models_used": None,
            }
        
        # Get all model names (keys of the dict)
        model_names = list(usage_data.keys())
        
        if not model_names:
            return {
                "model_name": None,
                "model_cost_cents": None,
                "model_response_count": None,
                "models_used": None,
            }
        
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
        
        # Calculate totals across all models
        total_cost = sum(
            stats.get("costInCents", 0) 
            for stats in usage_data.values() 
            if isinstance(stats, dict)
        )
        total_responses = sum(
            stats.get("amount", 0) 
            for stats in usage_data.values() 
            if isinstance(stats, dict)
        )
        
        return {
            "model_name": primary_model,
            "model_cost_cents": primary_stats.get("costInCents"),
            "model_response_count": primary_stats.get("amount"),
            "models_used": json.dumps(model_names) if len(model_names) > 1 else None,
            "total_cost_cents": total_cost if total_cost > 0 else None,
            "total_model_responses": total_responses if total_responses > 0 else None,
        }

    def _extract_bubble_event(
        self,
        bubble: dict,
        composer_id: str,
        workspace_hash: str,
        storage_level: str,
        database_table: str,
        item_key: str,
        external_session_id: Optional[str] = None
    ) -> dict:
        """Extract data from a single bubble."""
        timing_info = bubble.get("timingInfo", {})

        metadata = {
            "storage_level": storage_level,
            "workspace_hash": workspace_hash,
            "database_table": database_table,
            "item_key": item_key,
            "source": "bubble_extractor",
        }
        if external_session_id:
            metadata["external_session_id"] = external_session_id

        return {
            "version": "0.1.0",
            "hook_type": "DatabaseTrace",
            "event_type": "bubble",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": "cursor",
            "metadata": metadata,
            "payload": {
                "extracted_fields": {
                    "composer_id": composer_id,
                    "bubble_id": bubble.get("bubbleId"),
                    "server_bubble_id": bubble.get("serverBubbleId"),
                    "message_type": bubble.get("type"),  # 1=user, 2=ai
                    "text_description": bubble.get("text"),
                    "raw_text": bubble.get("rawText"),
                    "rich_text": json.dumps(bubble.get("richText")) if bubble.get("richText") else None,
                    "capabilities_ran": json.dumps(bubble.get("capabilitiesRan")) if bubble.get("capabilitiesRan") else None,
                    "capability_statuses": json.dumps(bubble.get("capabilityStatuses")) if bubble.get("capabilityStatuses") else None,
                    "token_count_up_until_here": bubble.get("tokenCountUpUntilHere"),
                    "client_start_time": timing_info.get("clientStartTime"),
                    "client_end_time": timing_info.get("clientEndTime"),
                    "unix_ms": bubble.get("unixMs"),
                    "relevant_files": json.dumps(bubble.get("relevantFiles")) if bubble.get("relevantFiles") else None,
                    "selections": json.dumps(bubble.get("selections")) if bubble.get("selections") else None,
                },
                "full_data": bubble
            }
        }

    def _extract_capability_event(
        self,
        cap_name: str,
        cap_data: dict,
        composer_id: str,
        workspace_hash: str,
        storage_level: str,
        database_table: str,
        item_key: str,
        external_session_id: Optional[str] = None
    ) -> dict:
        """Extract capability execution data."""
        metadata = {
            "storage_level": storage_level,
            "workspace_hash": workspace_hash,
            "database_table": database_table,
            "item_key": item_key,
            "source": "capability_extractor",
        }
        if external_session_id:
            metadata["external_session_id"] = external_session_id

        return {
            "version": "0.1.0",
            "hook_type": "DatabaseTrace",
            "event_type": "capability",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": "cursor",
            "metadata": metadata,
            "payload": {
                "extracted_fields": {
                    "composer_id": composer_id,
                    "capability_name": cap_name,
                    "capability_type": cap_data.get("type") if isinstance(cap_data, dict) else None,
                    "status": cap_data.get("status") if isinstance(cap_data, dict) else None,
                },
                "full_data": {
                    "capability_name": cap_name,
                    "capability_data": cap_data
                }
            }
        }


class BackgroundComposerExtractor:
    """
    Extracts background composer persistent data.
    Background composers run without user interaction.
    """

    def extract_background_composer(
        self,
        data: dict,
        workspace_hash: str,
        storage_level: str,
        database_table: str,
        item_key: str,
        external_session_id: Optional[str] = None
    ) -> dict:
        """Extract background composer persistent data."""
        metadata = {
            "storage_level": storage_level,
            "workspace_hash": workspace_hash,
            "database_table": database_table,
            "item_key": item_key,
            "source": "background_composer_extractor",
        }
        if external_session_id:
            metadata["external_session_id"] = external_session_id

        return {
            "version": "0.1.0",
            "hook_type": "DatabaseTrace",
            "event_type": "background_composer",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": "cursor",
            "metadata": metadata,
            "payload": {
                "extracted_fields": {
                    "last_active_timestamp": data.get("lastActiveTimestamp"),
                    "state": data.get("state"),
                },
                "full_data": data
            }
        }


class AgentModeExtractor:
    """
    Extracts agent mode session data.
    Agent mode allows Cursor to perform autonomous actions.
    """

    def extract_agent_mode(
        self,
        exit_info: dict,
        workspace_hash: str,
        storage_level: str,
        database_table: str,
        item_key: str,
        external_session_id: Optional[str] = None
    ) -> dict:
        """Extract agent mode exit information."""
        metadata = {
            "storage_level": storage_level,
            "workspace_hash": workspace_hash,
            "database_table": database_table,
            "item_key": item_key,
            "source": "agent_mode_extractor",
        }
        if external_session_id:
            metadata["external_session_id"] = external_session_id

        return {
            "version": "0.1.0",
            "hook_type": "DatabaseTrace",
            "event_type": "agent_mode",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": "cursor",
            "metadata": metadata,
            "payload": {
                "extracted_fields": {
                    "session_id": exit_info.get("sessionId"),
                    "exit_reason": exit_info.get("reason"),
                    "exit_timestamp": exit_info.get("timestamp"),
                    "duration_ms": exit_info.get("duration"),
                    "success": exit_info.get("success", False),
                },
                "full_data": exit_info
            }
        }


class GenerationExtractor:
    """
    Extracts AI generation events with proper field mapping.
    """

    def extract_generations(
        self,
        generations: List[dict],
        workspace_hash: str,
        storage_level: str,
        database_table: str,
        item_key: str,
        external_session_id: Optional[str] = None
    ) -> List[dict]:
        """Extract generation events from array."""
        events = []

        for gen in generations:
            if not isinstance(gen, dict):
                continue

            metadata = {
                "storage_level": storage_level,
                "workspace_hash": workspace_hash,
                "database_table": database_table,
                "item_key": item_key,
                "source": "generation_extractor",
            }
            if external_session_id:
                metadata["external_session_id"] = external_session_id

            event = {
                "version": "0.1.0",
                "hook_type": "DatabaseTrace",
                "event_type": "generation",
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "platform": "cursor",
                "metadata": metadata,
                "payload": {
                    "extracted_fields": {
                        "generation_uuid": gen.get("generationUUID"),
                        "generation_type": gen.get("type"),
                        "unix_ms": gen.get("unixMs"),
                        "text_description": gen.get("textDescription"),
                        "lines_added": gen.get("linesAdded"),
                        "lines_removed": gen.get("linesRemoved"),
                    },
                    "full_data": gen
                }
            }
            events.append(event)

        return events


class PromptExtractor:
    """
    Extracts AI prompt events with proper field mapping.
    """

    def extract_prompts(
        self,
        prompts: List[dict],
        workspace_hash: str,
        storage_level: str,
        database_table: str,
        item_key: str,
        external_session_id: Optional[str] = None
    ) -> List[dict]:
        """Extract prompt events from array."""
        events = []

        for prompt in prompts:
            if not isinstance(prompt, dict):
                continue

            metadata = {
                "storage_level": storage_level,
                "workspace_hash": workspace_hash,
                "database_table": database_table,
                "item_key": item_key,
                "source": "prompt_extractor",
            }
            if external_session_id:
                metadata["external_session_id"] = external_session_id

            event = {
                "version": "0.1.0",
                "hook_type": "DatabaseTrace",
                "event_type": "prompt",
                "event_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "platform": "cursor",
                "metadata": metadata,
                "payload": {
                    "extracted_fields": {
                        "command_type": prompt.get("commandType"),
                        "unix_ms": prompt.get("unixMs"),
                        "text_description": prompt.get("text") or prompt.get("textDescription"),
                    },
                    "full_data": prompt
                }
            }
            events.append(event)

        return events
