# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Event schema definitions and validation.

Defines the standard event format used across all platforms.
"""

import json
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict


class Platform(str, Enum):
    """Supported IDE platforms."""
    CLAUDE_CODE = "claude_code"
    CURSOR = "cursor"


class EventType(str, Enum):
    """Event types captured by the system."""
    # Session events
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # User interaction
    USER_PROMPT = "user_prompt"
    ASSISTANT_RESPONSE = "assistant_response"

    # Tool execution
    TOOL_USE = "tool_use"
    MCP_EXECUTION = "mcp_execution"

    # Code changes
    FILE_EDIT = "file_edit"
    FILE_READ = "file_read"

    # Shell commands
    SHELL_EXECUTION = "shell_execution"

    # Database traces
    DATABASE_TRACE = "database_trace"

    # Acceptance tracking
    ACCEPTANCE_DECISION = "acceptance_decision"

    # Context management
    CONTEXT_COMPACT = "context_compact"

    # Errors
    ERROR = "error"


class HookType(str, Enum):
    """Hook types for different platforms."""
    # Claude Code hooks
    SESSION_START = "SessionStart"
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    STOP = "Stop"
    PRE_COMPACT = "PreCompact"

    # Cursor hooks
    BEFORE_SUBMIT_PROMPT = "beforeSubmitPrompt"
    AFTER_AGENT_RESPONSE = "afterAgentResponse"
    BEFORE_MCP_EXECUTION = "beforeMCPExecution"
    AFTER_MCP_EXECUTION = "afterMCPExecution"
    AFTER_FILE_EDIT = "afterFileEdit"
    BEFORE_SHELL_EXECUTION = "beforeShellExecution"
    AFTER_SHELL_EXECUTION = "afterShellExecution"
    BEFORE_READ_FILE = "beforeReadFile"
    CURSOR_STOP = "stop"

    # Extension-generated events (not actual hooks)
    SESSION = "session"
    DATABASE_TRACE = "DatabaseTrace"


@dataclass
class EventMetadata:
    """Standard metadata for all events."""
    workspace_hash: Optional[str] = None
    project_hash: Optional[str] = None
    model: Optional[str] = None
    git_branch_hash: Optional[str] = None
    sequence_num: Optional[int] = None


@dataclass
class Event:
    """
    Standard event structure for all telemetry events.

    This is the canonical format written to the message queue.
    """
    # Core identification
    timestamp: str
    platform: str
    session_id: str
    event_type: str
    hook_type: str

    # Event metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Event-specific payload
    payload: Dict[str, Any] = field(default_factory=dict)

    # System fields (added by queue writer)
    event_id: Optional[str] = None
    enqueued_at: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create event from dictionary."""
        return cls(**data)


class EventSchema:
    """
    Event schema validator and builder.

    Provides utilities for creating and validating events.
    """

    @staticmethod
    def create_event(
        platform: Platform,
        session_id: str,
        event_type: EventType,
        hook_type: HookType,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Event:
        """
        Create a new event with standard structure.

        Args:
            platform: IDE platform
            session_id: Session identifier
            event_type: Type of event
            hook_type: Hook that generated the event
            payload: Event-specific data
            metadata: Additional metadata

        Returns:
            Validated Event object
        """
        return Event(
            timestamp=datetime.now(timezone.utc).isoformat(),
            platform=platform.value,
            session_id=session_id,
            event_type=event_type.value,
            hook_type=hook_type.value,
            payload=payload or {},
            metadata=metadata or {},
        )

    @staticmethod
    def validate_event(event: Dict[str, Any]) -> bool:
        """
        Validate event structure.

        Args:
            event: Event dictionary to validate

        Returns:
            True if valid, raises ValueError if invalid
        """
        required_fields = [
            "timestamp",
            "platform",
            "session_id",
            "event_type",
            "hook_type",
        ]

        for field in required_fields:
            if field not in event:
                raise ValueError(f"Missing required field: {field}")

        # Validate platform
        if event["platform"] not in [p.value for p in Platform]:
            raise ValueError(f"Invalid platform: {event['platform']}")

        # Validate event_type
        if event["event_type"] not in [e.value for e in EventType]:
            raise ValueError(f"Invalid event_type: {event['event_type']}")

        # Validate timestamp format
        try:
            datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raise ValueError(f"Invalid timestamp format: {event.get('timestamp')}")

        return True

    @staticmethod
    def map_hook_to_event_type(hook_type: HookType) -> EventType:
        """
        Map hook type to event type.

        Args:
            hook_type: Hook type

        Returns:
            Corresponding EventType
        """
        mapping = {
            # Claude Code
            HookType.SESSION_START: EventType.SESSION_START,
            HookType.STOP: EventType.SESSION_END,
            HookType.USER_PROMPT_SUBMIT: EventType.USER_PROMPT,
            HookType.PRE_TOOL_USE: EventType.TOOL_USE,
            HookType.POST_TOOL_USE: EventType.TOOL_USE,
            HookType.PRE_COMPACT: EventType.CONTEXT_COMPACT,

            # Cursor
            HookType.BEFORE_SUBMIT_PROMPT: EventType.USER_PROMPT,
            HookType.AFTER_AGENT_RESPONSE: EventType.ASSISTANT_RESPONSE,
            HookType.BEFORE_MCP_EXECUTION: EventType.MCP_EXECUTION,
            HookType.AFTER_MCP_EXECUTION: EventType.MCP_EXECUTION,
            HookType.AFTER_FILE_EDIT: EventType.FILE_EDIT,
            HookType.BEFORE_SHELL_EXECUTION: EventType.SHELL_EXECUTION,
            HookType.AFTER_SHELL_EXECUTION: EventType.SHELL_EXECUTION,
            HookType.BEFORE_READ_FILE: EventType.FILE_READ,
            HookType.CURSOR_STOP: EventType.SESSION_END,
        }

        return mapping.get(hook_type, EventType.ERROR)
