# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""Consumer for git commit telemetry events."""

import asyncio
import json
import logging
from typing import Any, Dict, Optional

import redis

from ..database.sqlite_client import SQLiteClient
from .repo_utils import generate_repo_id

logger = logging.getLogger(__name__)


class GitEventConsumer:
    """
    Consumes git commit events from Redis stream and writes to SQLite.

    Filters events where platform == "git" and processes commit metadata.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        sqlite_client: SQLiteClient,
        stream_name: str = "telemetry:message_queue",
        consumer_group: str = "git_processors",
        consumer_name: str = "git-consumer-1",
    ):
        """
        Initialize GitEventConsumer.

        Args:
            redis_client: Redis connection
            sqlite_client: SQLite database client
            stream_name: Redis stream name
            consumer_group: Consumer group name
            consumer_name: Individual consumer name
        """
        self.redis_client = redis_client
        self.sqlite_client = sqlite_client
        self.stream_name = stream_name
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name

    async def start(self) -> None:
        """Start consuming git events from Redis stream."""
        logger.info(f"Starting Git event consumer on stream {self.stream_name}")

        try:
            # Ensure consumer group exists
            try:
                self.redis_client.xgroup_create(self.stream_name, self.consumer_group, id='0', mkstream=True)
                logger.info(f"Created consumer group {self.consumer_group}")
            except redis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise
                logger.info(f"Consumer group {self.consumer_group} already exists")

            # Main consumer loop
            while True:
                try:
                    # Read pending messages first (in case of restart)
                    messages = self.redis_client.xreadgroup(
                        {self.stream_name: '0'},
                        self.consumer_group,
                        self.consumer_name,
                        count=10,
                        block=1000,  # 1 second timeout
                    )

                    if messages:
                        for stream_name, stream_messages in messages:
                            for message_id, message_data in stream_messages:
                                await self._process_message(message_id, message_data)

                    # Then read new messages
                    messages = self.redis_client.xreadgroup(
                        {self.stream_name: '>'},
                        self.consumer_group,
                        self.consumer_name,
                        count=10,
                        block=1000,  # 1 second timeout
                    )

                    if messages:
                        for stream_name, stream_messages in messages:
                            for message_id, message_data in stream_messages:
                                await self._process_message(message_id, message_data)

                except Exception as e:
                    logger.error(f"Error in consumer loop: {e}", exc_info=True)
                    await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Fatal error in git event consumer: {e}", exc_info=True)
            raise

    async def _process_message(self, message_id: bytes, message_data: Dict[bytes, bytes]) -> None:
        """
        Process a single message from the stream.

        Args:
            message_id: Redis message ID
            message_data: Message data dictionary
        """
        try:
            # Decode message data
            decoded_data = {
                key.decode(): value.decode() if isinstance(value, bytes) else value
                for key, value in message_data.items()
            }

            platform = decoded_data.get('platform', '')

            # Only process git events
            if platform != 'git':
                # Acknowledge but skip non-git events
                self.redis_client.xack(self.stream_name, self.consumer_group, message_id)
                return

            # Process git commit event
            await self._process_git_event(message_id, decoded_data)

        except Exception as e:
            logger.error(f"Error processing message {message_id}: {e}", exc_info=True)
            # Acknowledge even on error to avoid infinite loops
            try:
                self.redis_client.xack(self.stream_name, self.consumer_group, message_id)
            except Exception as ack_error:
                logger.error(f"Error acknowledging message {message_id}: {ack_error}")

    async def _process_git_event(self, message_id: bytes, event_data: Dict[str, Any]) -> None:
        """
        Process a git commit event.

        Args:
            message_id: Redis message ID
            event_data: Decoded event data
        """
        try:
            # Extract event fields
            event_id = event_data.get('event_id')
            payload_str = event_data.get('payload', '{}')
            metadata_str = event_data.get('metadata', '{}')

            try:
                payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
                metadata = json.loads(metadata_str) if isinstance(metadata_str, str) else metadata_str
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON in event {event_id}: {e}")
                self.redis_client.xack(self.stream_name, self.consumer_group, message_id)
                return

            # Extract commit data
            commit_hash = payload.get('commit_hash')
            if not commit_hash:
                logger.warning(f"Event {event_id} missing commit_hash")
                self.redis_client.xack(self.stream_name, self.consumer_group, message_id)
                return

            repo_path = payload.get('repo_path')
            remote_url = payload.get('remote_url')
            workspace_hash = metadata.get('workspace_hash')
            workspace_path = metadata.get('workspace_path', '')
            project_name = metadata.get('project_name')

            # Generate repo_id
            repo_id = generate_repo_id(repo_path, remote_url)

            # Ensure workspace exists
            self._ensure_workspace(workspace_hash, workspace_path, project_name)

            # Insert commit
            self._insert_commit(
                commit_hash=commit_hash,
                repo_id=repo_id,
                workspace_hash=workspace_hash,
                author_name=payload.get('author_name'),
                author_email=payload.get('author_email'),
                commit_timestamp=payload.get('commit_timestamp'),
                commit_message=payload.get('commit_message'),
                files_changed=payload.get('files_changed', 0),
                insertions=payload.get('insertions', 0),
                deletions=payload.get('deletions', 0),
                branch_name=payload.get('branch_name'),
                event_id=event_id,
            )

            # Acknowledge successful processing
            self.redis_client.xack(self.stream_name, self.consumer_group, message_id)
            logger.debug(f"Processed git commit {commit_hash[:8]} from repo {repo_id[:8]}")

        except Exception as e:
            logger.error(f"Error processing git event {message_id}: {e}", exc_info=True)
            # Acknowledge to avoid infinite retry
            try:
                self.redis_client.xack(self.stream_name, self.consumer_group, message_id)
            except Exception as ack_error:
                logger.error(f"Error acknowledging message: {ack_error}")

    def _ensure_workspace(
        self,
        workspace_hash: str,
        workspace_path: str,
        project_name: Optional[str] = None,
    ) -> None:
        """
        Insert or update workspace record.

        Args:
            workspace_hash: SHA256 hash of workspace path
            workspace_path: Full workspace path
            project_name: Human-readable project name
        """
        try:
            with self.sqlite_client.get_connection() as conn:
                conn.execute("""
                    INSERT INTO workspaces (workspace_hash, workspace_path, workspace_name, last_seen_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(workspace_hash) DO UPDATE SET
                        last_seen_at = CURRENT_TIMESTAMP,
                        workspace_path = COALESCE(excluded.workspace_path, workspaces.workspace_path),
                        workspace_name = COALESCE(excluded.workspace_name, workspaces.workspace_name)
                """, (workspace_hash, workspace_path, project_name))
                conn.commit()
        except Exception as e:
            logger.error(f"Error ensuring workspace {workspace_hash}: {e}")

    def _insert_commit(
        self,
        commit_hash: str,
        repo_id: str,
        workspace_hash: str,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None,
        commit_timestamp: Optional[str] = None,
        commit_message: Optional[str] = None,
        files_changed: int = 0,
        insertions: int = 0,
        deletions: int = 0,
        branch_name: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> None:
        """
        Insert commit record into database.

        Duplicates (same repo_id + commit_hash) are ignored.

        Args:
            commit_hash: Git commit SHA
            repo_id: Repository identifier (UUID)
            workspace_hash: Workspace identifier
            author_name: Commit author name
            author_email: Commit author email
            commit_timestamp: ISO 8601 timestamp
            commit_message: Commit message
            files_changed: Number of files changed
            insertions: Lines added
            deletions: Lines removed
            branch_name: Branch name
            event_id: Telemetry event ID
        """
        try:
            with self.sqlite_client.get_connection() as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO git_commits (
                        commit_hash, repo_id, workspace_hash,
                        author_name, author_email, commit_timestamp, commit_message,
                        files_changed, insertions, deletions, branch_name, event_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    commit_hash, repo_id, workspace_hash,
                    author_name, author_email, commit_timestamp, commit_message,
                    files_changed, insertions, deletions, branch_name, event_id
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error inserting commit {commit_hash}: {e}")
