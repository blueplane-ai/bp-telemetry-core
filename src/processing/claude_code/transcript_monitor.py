# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Claude Code Transcript Monitor.

Monitors for session_end events and processes Claude Code transcript files (.jsonl).
Sends trace events to Redis Streams for processing.
"""

import asyncio
import json
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Set
import redis
from ...capture.shared.project_utils import derive_project_name
from ...capture.shared.redis_streams import TELEMETRY_EVENTS_STREAM

logger = logging.getLogger(__name__)


class ClaudeCodeTranscriptMonitor:
    """
    Monitor Claude Code transcripts and send trace events to Redis.

    This monitor:
    1. Listens for session_end events on Redis stream (from Stop hook)
    2. Extracts transcript_path from the event payload
    3. Reads and processes the JSONL transcript file
    4. Sends trace events to Redis for each entry in the transcript
    5. Tracks processed sessions to avoid duplicates
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        stream_name: str = TELEMETRY_EVENTS_STREAM,
        consumer_group: str = "transcript_processors",
        consumer_name: str = "transcript_monitor",
        poll_interval: float = 1.0,
    ):
        """
        Initialize transcript monitor.

        Args:
            redis_client: Redis client instance
            stream_name: Redis stream to monitor
            consumer_group: Consumer group name
            consumer_name: Consumer name
            poll_interval: Polling interval in seconds
        """
        self.redis_client = redis_client
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name
        self.poll_interval = poll_interval

        # Track processed transcripts to avoid duplicates
        # Key format: "session_id:transcript_path_hash"
        self.processed_transcripts: Set[str] = set()

        # Running flag
        self.running = False

    async def start(self) -> None:
        """Start the transcript monitor."""
        logger.info("Starting Claude Code transcript monitor")

        # Ensure consumer group exists
        try:
            self.redis_client.xgroup_create(
                self.stream_name,
                self.consumer_group,
                id='0',
                mkstream=True
            )
            logger.info("Created consumer group: %s", self.consumer_group)
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                logger.error("Failed to create consumer group: %s", e)
                raise
            logger.debug("Consumer group already exists: %s", self.consumer_group)

        self.running = True

        # Start monitoring loop
        await self._monitor_loop()

    async def stop(self) -> None:
        """Stop the transcript monitor."""
        logger.info("Stopping Claude Code transcript monitor")
        self.running = False

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        logger.info("Transcript monitor loop started")

        while self.running:
            try:
                # Read from Redis stream using consumer group
                events = self.redis_client.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={self.stream_name: '>'},
                    count=10,
                    block=int(self.poll_interval * 1000)
                )

                if not events:
                    continue

                # Process each event
                for stream_name, messages in events:
                    for message_id, data in messages:
                        try:
                            await self._process_event(message_id, data)

                            # Acknowledge message
                            self.redis_client.xack(
                                self.stream_name,
                                self.consumer_group,
                                message_id
                            )
                        except Exception as e:
                            logger.error(
                                "Error processing message %s: %s",
                                message_id,
                                e,
                                exc_info=True
                            )
                            # Still acknowledge to prevent reprocessing
                            self.redis_client.xack(
                                self.stream_name,
                                self.consumer_group,
                                message_id
                            )

            except Exception as e:
                logger.error("Error in monitor loop: %s", e, exc_info=True)
                await asyncio.sleep(self.poll_interval)

    async def _process_event(self, message_id: bytes, data: Dict[bytes, bytes]) -> None:
        """
        Process a single event from the stream.

        Args:
            message_id: Redis stream message ID
            data: Event data dictionary
        """
        # Decode bytes to strings
        decoded_data = {
            k.decode('utf-8') if isinstance(k, bytes) else k:
            v.decode('utf-8') if isinstance(v, bytes) else v
            for k, v in data.items()
        }

        # Check if this is a Stop or SessionEnd hook from claude_code platform
        platform = decoded_data.get('platform', '')
        hook_type = decoded_data.get('hook_type', '')

        if platform != 'claude_code' or hook_type not in ('Stop', 'SessionEnd'):
            # Not a Claude Code Stop or SessionEnd hook, skip
            return

        # Extract session_id and payload
        session_id = decoded_data.get('external_session_id')
        if not session_id:
            logger.warning("%s hook missing session_id", hook_type)
            return

        # Parse payload to get transcript_path
        payload_str = decoded_data.get('payload', '{}')
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            logger.error("Failed to parse payload: %s", payload_str)
            return

        transcript_path = payload.get('transcript_path')
        if not transcript_path:
            logger.debug("%s hook has no transcript_path, skipping", hook_type)
            return

        # Check if this specific transcript has already been processed
        # Use hash of transcript path to create unique key
        import hashlib
        path_hash = hashlib.sha256(str(transcript_path).encode()).hexdigest()[:16]
        dedup_key = f"{session_id}:{path_hash}"

        if dedup_key in self.processed_transcripts:
            logger.debug("Transcript %s for session %s already processed, skipping",
                        transcript_path, session_id)
            return

        # Process the transcript
        logger.info("Processing transcript for session %s from %s hook: %s",
                   session_id, hook_type, transcript_path)
        await self._process_transcript(session_id, transcript_path, hook_type)

        # Mark as processed
        self.processed_transcripts.add(dedup_key)

    async def _process_transcript(self, session_id: str, transcript_path: str, hook_type: str = None) -> None:
        """
        Process a Claude Code transcript file.

        Args:
            session_id: Session ID
            transcript_path: Path to transcript JSONL file
            hook_type: Hook type that triggered processing (for logging)
        """
        try:
            path = Path(transcript_path)
            if not path.exists():
                logger.warning("Transcript file not found: %s", transcript_path)
                return

            # Read JSONL file
            with open(path, 'r') as f:
                lines = f.readlines()

            # Parse all entries first (needed for workspace hash extraction)
            entries = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

            logger.info("Processing %d transcript entries for session %s (from %s hook)",
                       len(entries), session_id, hook_type or "unknown")

            # Extract workspace metadata from transcript
            workspace_path = self._derive_workspace_path_from_transcript(transcript_path, entries)
            workspace_hash = self._get_workspace_hash_from_transcript(transcript_path, entries, workspace_path)
            logger.debug("Extracted workspace hash: %s for transcript: %s",
                        workspace_hash, transcript_path)

            # Process each entry
            for line_num, entry in enumerate(entries, start=1):
                await self._process_transcript_entry(
                    session_id,
                    entry,
                    line_num,
                    workspace_hash,
                    workspace_path=workspace_path,
                )

        except Exception as e:
            logger.error("Error processing transcript %s: %s", transcript_path, e, exc_info=True)

    async def _process_transcript_entry(
        self,
        session_id: str,
        entry: Dict[str, Any],
        line_num: int,
        workspace_hash: str = None,
        workspace_path: Optional[str] = None,
    ) -> None:
        """
        Process a single transcript entry and send to Redis.

        Args:
            session_id: Session ID
            entry: Transcript entry dictionary
            line_num: Line number in transcript file
            workspace_hash: Pre-computed workspace hash
        """
        # Extract metadata from transcript entry
        # Claude Code transcript format typically includes:
        # - role (user/assistant)
        # - content (text or tool_calls)
        # - timestamp
        # - model info
        # - usage stats

        role = entry.get('role', 'unknown')
        content = entry.get('content', '')
        timestamp = entry.get('timestamp')

        # Build trace event
        event = {
            "version": "0.1.0",
            "hook_type": "TranscriptTrace",
            "event_type": "transcript_trace",  # Distinct event type for Claude Code transcripts
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
            "platform": "claude_code",
            "session_id": session_id,
            "external_session_id": session_id,
            "metadata": {
                "workspace_hash": workspace_hash,
                "project_name": derive_project_name(workspace_path),
                "source": "transcript_monitor",
                "line_number": line_num,
            },
            "payload": {
                "trace_type": "transcript_entry",
                "role": role,
                "line_number": line_num,
                "entry_data": entry,  # Full transcript entry
            }
        }

        # Add model info if present (nested in message object)
        message = entry.get('message', {})
        if isinstance(message, dict):
            if 'model' in message:
                event['payload']['model'] = message['model']

            # Add usage info if present (nested in message object)
            if 'usage' in message:
                usage = message['usage']
                if isinstance(usage, dict):
                    # Calculate total tokens from input_tokens + output_tokens
                    input_tokens = usage.get('input_tokens', 0)
                    output_tokens = usage.get('output_tokens', 0)
                    total_tokens = input_tokens + output_tokens
                    if total_tokens > 0:
                        event['payload']['tokens_used'] = total_tokens
                        # Also store detailed usage info
                        event['payload']['prompt_tokens'] = input_tokens
                        event['payload']['completion_tokens'] = output_tokens

        # Send to Redis stream
        try:
            stream_entry = {
                k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                for k, v in event.items()
            }

            self.redis_client.xadd(
                self.stream_name,
                stream_entry,
                maxlen=10000,
                approximate=True
            )

            logger.debug(
                "Sent transcript trace for session %s, line %d",
                session_id,
                line_num
            )

        except Exception as e:
            logger.error(
                "Failed to send transcript trace for session %s, line %d: %s",
                session_id,
                line_num,
                e
            )

    def _get_workspace_hash_from_transcript(
        self,
        transcript_path: str,
        transcript_content: list = None,
        workspace_path: Optional[str] = None,
    ) -> str:
        """
        Extract workspace hash from transcript path and content.

        Tries multiple strategies:
        1. Extract from transcript file path (often contains workspace directory)
        2. Look for workspace/cwd in transcript content (first entries often have this)
        3. Fall back to transcript path hash

        Args:
            transcript_path: Path to transcript file
            transcript_content: Optional parsed transcript content

        Returns:
            Workspace hash
        """
        # Strategy 1: Extract workspace from transcript path
        # Claude Code typically stores transcripts in workspace-specific locations
        # e.g., /path/to/workspace/.claude/sessions/session_id/transcript.jsonl
        path_obj = Path(transcript_path)
        resolved_path = workspace_path or self._derive_workspace_path_from_transcript(transcript_path, transcript_content)
        if resolved_path:
            return hashlib.sha256(resolved_path.encode()).hexdigest()[:16]

        # Strategy 3: Fall back to hashing the transcript directory path
        # This at least gives us a consistent hash per workspace
        transcript_dir = str(path_obj.parent.parent)  # Go up from file to session to workspace area
        return hashlib.sha256(transcript_dir.encode()).hexdigest()[:16]

    def _derive_workspace_path_from_transcript(self, transcript_path: str, transcript_content: list = None) -> Optional[str]:
        """
        Attempt to determine the original workspace path associated with a transcript.
        """
        path_obj = Path(transcript_path)

        # Strategy 1: detect `.claude` directory structure
        for parent in path_obj.parents:
            if parent.name == '.claude' and parent.parent:
                return str(parent.parent)

        # Strategy 2: inspect transcript content for cwd/workspace hints
        if transcript_content:
            for entry in transcript_content[:5]:
                if not isinstance(entry, dict):
                    continue

                for key in ('cwd', 'workspace', 'workspace_path'):
                    val = entry.get(key)
                    if isinstance(val, str):
                        return val

                metadata = entry.get('metadata', {})
                if isinstance(metadata, dict):
                    for key in ('cwd', 'workspace', 'workspace_path'):
                        val = metadata.get(key)
                        if isinstance(val, str):
                            return val

        return None
