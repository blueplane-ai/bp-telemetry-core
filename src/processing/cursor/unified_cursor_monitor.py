# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
UnifiedCursorMonitor - Session-aware monitoring for Cursor databases.

Consolidates all Cursor database monitoring into a single unified system with:
- Session-driven workspace activation
- Dual-database monitoring (workspace ItemTable + global cursorDiskKV)
- File watching with polling fallback
- Incremental state tracking
- Redis message queue routing with ACK support
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, Set, Any
import aiosqlite
import redis

from .session_monitor import SessionMonitor
from .workspace_mapper import WorkspaceMapper
from .data_extractors import (
    ComposerDataExtractor,
    BackgroundComposerExtractor,
    AgentModeExtractor,
    GenerationExtractor,
    PromptExtractor
)
from ...capture.shared.redis_streams import TELEMETRY_MESSAGE_QUEUE_STREAM

logger = logging.getLogger(__name__)


@dataclass
class CursorMonitorConfig:
    """Configuration for UnifiedCursorMonitor."""

    query_timeout: float = 1.5
    debounce_delay: float = 10.0
    poll_interval: float = 60.0
    cache_ttl: int = 300
    max_retries: int = 3


class IncrementalSync:
    """
    Tracks processed data to avoid reprocessing.
    Uses content hash and timestamp for change detection.
    Handles timestamped arrays properly.
    """

    def __init__(self):
        self.state: Dict[str, Dict[str, Any]] = {}
        self.last_timestamps: Dict[str, int] = {}  # For timestamped arrays

    def should_process(
        self,
        storage_level: str,
        workspace_hash: str,
        key: str,
        data: Any
    ) -> bool:
        """
        Check if data should be processed based on state.

        Args:
            storage_level: 'workspace' or 'global'
            workspace_hash: Workspace identifier
            key: Database key
            data: Data to check

        Returns:
            True if data should be processed
        """
        state_key = f"{storage_level}:{workspace_hash}:{key}"

        # For timestamped array data (generations, prompts)
        if isinstance(data, list) and key in (
            "aiService.generations",
            "aiService.prompts"
        ):
            return self._check_timestamped_array(state_key, data)

        # For non-timestamped data, use content hash
        data_str = json.dumps(data, sort_keys=True) if isinstance(data, dict) else str(data)
        data_hash = hashlib.sha256(data_str.encode()).hexdigest()[:16]

        # Get last processed hash
        last_state = self.state.get(state_key, {})
        last_hash = last_state.get("hash")

        # Changed if hash differs
        if last_hash != data_hash:
            self.state[state_key] = {
                "hash": data_hash,
                "timestamp": time.time()
            }
            return True

        return False

    def _check_timestamped_array(self, state_key: str, data: list) -> bool:
        """Check timestamped array for new items."""
        if not data:
            return False

        last_ts = self.last_timestamps.get(state_key, 0)
        max_ts = last_ts

        # Check if there are any new items
        has_new = False
        for item in data:
            if isinstance(item, dict):
                item_ts = item.get("unixMs", 0)
                if item_ts > last_ts:
                    has_new = True
                    max_ts = max(max_ts, item_ts)

        if has_new:
            self.last_timestamps[state_key] = max_ts
            return True

        return False

    def get_new_items(
        self,
        storage_level: str,
        workspace_hash: str,
        key: str,
        data: list
    ) -> list:
        """Get only new items from timestamped array."""
        state_key = f"{storage_level}:{workspace_hash}:{key}"
        last_ts = self.last_timestamps.get(state_key, 0)

        new_items = []
        max_ts = last_ts

        for item in data:
            if isinstance(item, dict):
                item_ts = item.get("unixMs", 0)
                if item_ts > last_ts:
                    new_items.append(item)
                    max_ts = max(max_ts, item_ts)

        if new_items:
            self.last_timestamps[state_key] = max_ts

        return new_items

    def clear(self, workspace_hash: Optional[str] = None):
        """Clear state for a workspace or all."""
        if workspace_hash:
            keys_to_remove = [k for k in self.state if workspace_hash in k]
            for key in keys_to_remove:
                del self.state[key]

            keys_to_remove = [k for k in self.last_timestamps if workspace_hash in k]
            for key in keys_to_remove:
                del self.last_timestamps[key]
        else:
            self.state.clear()
            self.last_timestamps.clear()


class SmartCache:
    """TTL-based cache for database lookups."""

    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Dict[str, Any]] = {}

    async def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        if key in self.cache:
            entry = self.cache[key]
            if time.time() - entry["timestamp"] < self.ttl_seconds:
                return entry["value"]
            else:
                del self.cache[key]
        return None

    async def set(self, key: str, value: Any):
        """Set cached value with current timestamp."""
        self.cache[key] = {
            "value": value,
            "timestamp": time.time()
        }

    def invalidate(self, pattern: str):
        """Invalidate cache entries matching pattern (supports '*' wildcard)."""
        if "*" in pattern:
            prefix = pattern.replace("*", "")
            keys_to_remove = [k for k in self.cache if k.startswith(prefix)]
            for key in keys_to_remove:
                del self.cache[key]
        else:
            self.cache.pop(pattern, None)


class FileWatcher:
    """
    Watches database files for changes using filesystem events with fallback.

    Strategy:
    1. Primary: watchdog library for filesystem events
    2. Fallback: stat-based polling every 60 seconds
    3. Debounce: 10-second delay after change detection
    """

    def __init__(self, db_path: Path, callback: Callable):
        self.db_path = db_path
        self.callback = callback
        self.last_modified = None
        self.last_size = None
        self.watchdog_observer = None
        self.active = True
        self.debounce_task = None
        self.debounce_delay = 10.0
        self.poll_task = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def start_watching(self):
        """Start file watching with fallback."""
        # Store event loop reference for thread-safe callbacks
        self._loop = asyncio.get_running_loop()

        # Record initial state
        try:
            stat = self.db_path.stat()
            self.last_modified = stat.st_mtime
            self.last_size = stat.st_size
        except FileNotFoundError:
            logger.warning(f"Database not found: {self.db_path}")
            return

        # Try watchdog first
        if await self._try_watchdog():
            logger.info(f"Using watchdog for {self.db_path}")
        else:
            logger.info(f"Watchdog unavailable, using polling for {self.db_path}")

        # Start polling fallback
        self.poll_task = asyncio.create_task(self._polling_loop())

    async def _try_watchdog(self) -> bool:
        """Try to use watchdog for filesystem events."""
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            class DBChangeHandler(FileSystemEventHandler):
                def __init__(self, watcher):
                    self.watcher = watcher

                def on_modified(self, event):
                    if event.src_path == str(self.watcher.db_path):
                        if self.watcher._loop is not None:
                            asyncio.run_coroutine_threadsafe(
                                self.watcher._handle_change_with_debounce(),
                                self.watcher._loop
                            )

            self.watchdog_observer = Observer()
            self.watchdog_observer.schedule(
                DBChangeHandler(self),
                str(self.db_path.parent),
                recursive=False
            )
            self.watchdog_observer.start()
            return True

        except Exception as e:
            logger.warning(f"Watchdog failed: {e}")
            return False

    async def _handle_change_with_debounce(self):
        """Handle change with debouncing."""
        # Cancel existing debounce task
        if self.debounce_task:
            self.debounce_task.cancel()

        # Schedule new callback after delay
        self.debounce_task = asyncio.create_task(
            self._debounced_callback()
        )

    async def _debounced_callback(self):
        """Execute callback after debounce delay."""
        await asyncio.sleep(self.debounce_delay)
        await self.callback()

    async def _polling_loop(self):
        """Polling fallback: check for changes every 60 seconds."""
        while self.active:
            await asyncio.sleep(60)
            if await self.check_for_changes():
                await self._handle_change_with_debounce()

    async def check_for_changes(self) -> bool:
        """Polling fallback: check if file changed."""
        try:
            stat = self.db_path.stat()
            changed = (
                stat.st_mtime != self.last_modified or
                stat.st_size != self.last_size
            )
            if changed:
                self.last_modified = stat.st_mtime
                self.last_size = stat.st_size
                return True
        except FileNotFoundError:
            return False
        return False

    async def stop(self):
        """Stop watching and cleanup."""
        self.active = False

        if self.debounce_task:
            self.debounce_task.cancel()

        if self.poll_task:
            self.poll_task.cancel()

        if self.watchdog_observer:
            self.watchdog_observer.stop()
            self.watchdog_observer.join(timeout=1)


class EventQueuer:
    """
    Queues all events to Redis stream for processing.
    Ensures all telemetry flows through the message queue.
    Includes local buffering when Redis is unavailable.
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis_client = redis_client
        self.stream_name = TELEMETRY_MESSAGE_QUEUE_STREAM
        self.max_stream_length = 10000
        self.consumer_group = "processors"

    async def queue_event(self, event: dict):
        """
        Queue event to Redis stream.
        Falls back to local buffering if Redis is unavailable.

        Args:
            event: Event dictionary to queue
        """
        try:
            # Serialize nested structures
            serialized = self._serialize_event(event)

            # Add to stream with MAXLEN for memory management
            self.redis_client.xadd(
                self.stream_name,
                serialized,
                maxlen=self.max_stream_length,
                approximate=True
            )

            logger.debug(f"Queued event {event.get('event_type')} to {self.stream_name}")

        except redis.ConnectionError as e:
            logger.error(f"Redis connection lost, buffering locally: {e}")
            await self._buffer_locally(event)
        except Exception as e:
            logger.error(f"Failed to queue event: {e}")
            await self._buffer_locally(event)

    def _serialize_event(self, event: dict) -> dict:
        """Serialize event for Redis."""
        serialized = {}

        for key, value in event.items():
            if isinstance(value, (dict, list)):
                serialized[key] = json.dumps(value)
            elif isinstance(value, datetime):
                serialized[key] = value.isoformat()
            elif value is not None:
                serialized[key] = str(value)
            else:
                serialized[key] = ""

        return serialized

    async def _buffer_locally(self, event: dict):
        """Buffer events locally when Redis is unavailable."""
        buffer_path = Path.home() / ".blueplane" / "event_buffer.db"
        buffer_path.parent.mkdir(exist_ok=True, parents=True)

        try:
            async with aiosqlite.connect(str(buffer_path)) as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS buffered_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        event_data TEXT NOT NULL,
                        retry_count INTEGER DEFAULT 0
                    )
                """)

                await conn.execute(
                    "INSERT INTO buffered_events (event_data) VALUES (?)",
                    (json.dumps(event),)
                )
                await conn.commit()
                logger.info("Event buffered locally")
        except Exception as e:
            logger.error(f"Failed to buffer event locally: {e}")


class WorkspaceMonitor:
    """
    Monitors a single workspace database.
    Tracks specific ItemTable keys for AI telemetry.
    Uses data extractors for comprehensive event capture.
    """

    def __init__(
        self,
        workspace_hash: str,
        db_path: Path,
        redis_client: redis.Redis,
        config: CursorMonitorConfig,
        itemtable_keys: list,
        external_session_id: Optional[str] = None
    ):
        self.workspace_hash = workspace_hash
        self.db_path = db_path
        self.redis_client = redis_client
        self.config = config
        self.itemtable_keys = itemtable_keys
        self.external_session_id = external_session_id

        self.connection = None
        self.event_queuer = EventQueuer(redis_client)
        self.incremental_sync = IncrementalSync()

        # Initialize data extractors
        self.composer_extractor = ComposerDataExtractor()
        self.background_composer_extractor = BackgroundComposerExtractor()
        self.agent_mode_extractor = AgentModeExtractor()
        self.generation_extractor = GenerationExtractor()
        self.prompt_extractor = PromptExtractor()

    async def connect(self):
        """Connect to workspace database."""
        self.connection = await aiosqlite.connect(
            str(self.db_path),
            timeout=self.config.query_timeout
        )
        self.connection.row_factory = aiosqlite.Row

    async def sync_all_data(self):
        """Initial sync of all monitored keys."""
        if not self.connection:
            await self.connect()

        for key in self.itemtable_keys:
            await self._sync_key(key)

    async def _sync_key(self, key: str):
        """Sync a specific ItemTable key."""
        try:
            cursor = await self.connection.execute(
                "SELECT key, value FROM ItemTable WHERE key = ?",
                (key,)
            )
            row = await cursor.fetchone()

            if row and row["value"]:
                value = row["value"]

                # Parse JSON value
                data = json.loads(value) if isinstance(value, str) else value

                # Check if changed using incremental sync
                if self.incremental_sync.should_process(
                    "workspace",
                    self.workspace_hash,
                    key,
                    data
                ):
                    await self._extract_and_queue_events(key, data)

        except Exception as e:
            logger.error(f"Error syncing key {key}: {e}")

    async def _extract_and_queue_events(self, key: str, data: Any):
        """Extract and queue events based on data type."""
        try:
            events = []

            # Handle different data types with appropriate extractors
            if key == "aiService.generations" and isinstance(data, list):
                # For timestamped arrays, only get new items
                new_items = self.incremental_sync.get_new_items(
                    "workspace",
                    self.workspace_hash,
                    key,
                    data
                )
                if new_items:
                    events = self.generation_extractor.extract_generations(
                        new_items,
                        self.workspace_hash,
                        "workspace",
                        "ItemTable",
                        key,
                        self.external_session_id
                    )

            elif key == "aiService.prompts" and isinstance(data, list):
                # For timestamped arrays, only get new items
                new_items = self.incremental_sync.get_new_items(
                    "workspace",
                    self.workspace_hash,
                    key,
                    data
                )
                if new_items:
                    events = self.prompt_extractor.extract_prompts(
                        new_items,
                        self.workspace_hash,
                        "workspace",
                        "ItemTable",
                        key,
                        self.external_session_id
                    )

            elif key == "composer.composerData":
                # Handle workspace composer data structure
                if isinstance(data, dict) and "allComposers" in data:
                    # Workspace storage has allComposers array
                    all_composers = data.get("allComposers", [])
                    for composer in all_composers:
                        if isinstance(composer, dict):
                            # Extract each composer individually
                            composer_events = self.composer_extractor.extract_composer_events(
                                composer,
                                self.workspace_hash,
                                "workspace",
                                "ItemTable",
                                key,
                                self.external_session_id
                            )
                            events.extend(composer_events)
                else:
                    # Single composer object (from global database)
                    events = self.composer_extractor.extract_composer_events(
                        data,
                        self.workspace_hash,
                        "workspace",
                        "ItemTable",
                        key,
                        self.external_session_id
                    )

            elif key == "workbench.backgroundComposer.workspacePersistentData":
                # Extract background composer
                event = self.background_composer_extractor.extract_background_composer(
                    data,
                    self.workspace_hash,
                    "workspace",
                    "ItemTable",
                    key,
                    self.external_session_id
                )
                events = [event]

            elif key == "workbench.agentMode.exitInfo":
                # Extract agent mode
                event = self.agent_mode_extractor.extract_agent_mode(
                    data,
                    self.workspace_hash,
                    "workspace",
                    "ItemTable",
                    key,
                    self.external_session_id
                )
                events = [event]

            else:
                # Generic event for other keys
                metadata = {
                    "storage_level": "workspace",
                    "database_table": "ItemTable",
                    "item_key": key,
                    "workspace_hash": self.workspace_hash,
                    "source": "workspace_monitor",
                }
                if self.external_session_id:
                    metadata["external_session_id"] = self.external_session_id

                event = {
                    "version": "0.1.0",
                    "hook_type": "DatabaseTrace",
                    "event_type": "other",
                    "event_id": str(uuid.uuid4()),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "platform": "cursor",  # Explicitly set platform
                    "metadata": metadata,
                    "payload": {
                        "extracted_fields": {},
                        "full_data": data
                    }
                }
                events = [event]

            # Queue all extracted events
            for event in events:
                await self.event_queuer.queue_event(event)

            if events:
                logger.info(f"Queued {len(events)} events for {key}")

        except Exception as e:
            logger.error(f"Error extracting and queuing events for {key}: {e}")

    async def close(self):
        """Close database connection."""
        if self.connection:
            await self.connection.close()


class UserLevelListener:
    """
    Monitors user-level Cursor database (~/Library/Application Support/Cursor/User/globalStorage/state.vscdb).
    Started once on UnifiedCursorMonitor startup.
    Remains active for entire monitor lifetime.
    """

    def __init__(self, redis_client: redis.Redis, config: CursorMonitorConfig):
        self.redis_client = redis_client
        self.config = config
        self.db_path = None
        self.connection = None
        self.file_watcher = None
        self.incremental_sync = IncrementalSync()
        self.event_queuer = EventQueuer(redis_client)
        self.active_workspaces: Set[str] = set()

    async def start(self):
        """Start monitoring user-level database."""
        # Find user database
        self.db_path = await self._find_user_db()
        if not self.db_path or not self.db_path.exists():
            logger.warning("User-level Cursor database not found")
            return

        # Establish connection
        self.connection = await aiosqlite.connect(
            str(self.db_path),
            timeout=self.config.query_timeout
        )
        self.connection.row_factory = aiosqlite.Row

        # Start file watcher
        self.file_watcher = FileWatcher(
            self.db_path,
            self._on_user_db_change
        )
        await self.file_watcher.start_watching()

        # Initial sync
        await self._sync_composer_data()
        await self._sync_bubble_data()

        logger.info(f"Started user-level listener for {self.db_path}")

    async def _find_user_db(self) -> Optional[Path]:
        """Find user-level Cursor database."""
        # Mac-only path: ~/Library/Application Support/Cursor/User/globalStorage/state.vscdb
        db_path = Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb"

        if db_path.exists():
            return db_path

        return None

    async def _on_user_db_change(self):
        """Handle user database changes."""
        try:
            await self._sync_composer_data()
            await self._sync_bubble_data()
        except Exception as e:
            logger.error(f"Error syncing user database: {e}")

    async def _sync_composer_data(self):
        """
        Sync composer data from global database.
        Only processes composers for active workspaces.
        """
        if not self.connection:
            return

        try:
            # Query composer data
            cursor = await self.connection.execute("""
                SELECT key, value
                FROM cursorDiskKV
                WHERE key LIKE 'composerData:%'
            """)

            rows = await cursor.fetchall()

            for row in rows:
                key = row["key"]
                value = row["value"]

                if not value:
                    continue

                # Parse composer data
                try:
                    composer_data = json.loads(value)
                except json.JSONDecodeError:
                    continue

                # Check if data changed using incremental sync
                if self.incremental_sync.should_process("global", "all", key, value):
                    await self._queue_composer_event(key, composer_data)

        except Exception as e:
            logger.error(f"Error syncing composer data: {e}")

    async def _queue_composer_event(self, key: str, data: dict):
        """Queue composer event to Redis."""
        event = {
            "version": "0.1.0",
            "hook_type": "DatabaseTrace",
            "event_type": "composer",
            "platform": "cursor",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "storage_level": "global",
                "database_table": "cursorDiskKV",
                "item_key": key,
                "source": "user_level_listener",
            },
            "payload": {
                "extracted_fields": self._extract_composer_fields(data),
                "full_data": data
            }
        }

        await self.event_queuer.queue_event(event)

    def _extract_composer_fields(self, data: dict) -> dict:
        """Extract relevant fields from composer data."""
        # Note: workspaceId does not exist in globalStorage composerData
        # Workspace correlation must be done via other means
        return {
            "composerId": data.get("composerId"),
            "createdAt": data.get("createdAt"),
            "unifiedMode": data.get("unifiedMode"),
            "forceMode": data.get("forceMode"),
            "isAgentic": data.get("isAgentic"),
            "tokenCount": data.get("tokenCount"),
            "status": data.get("status"),
        }

    async def _sync_bubble_data(self):
        """
        Sync bubble data from globalStorage database.
        Bubbles are stored in keys matching pattern: bubbleId:{composerId}:{bubbleId}
        The first UUID is the composerId, providing the link to composers.
        """
        if not self.connection:
            return

        try:
            # Query bubble data
            # Note: This gets ALL bubbles. For production, consider pagination or filtering.
            cursor = await self.connection.execute("""
                SELECT key, value
                FROM cursorDiskKV
                WHERE key LIKE 'bubbleId:%'
            """)

            rows = await cursor.fetchall()

            for row in rows:
                key = row["key"]
                value = row["value"]

                if not value:
                    continue

                # Parse bubble data
                try:
                    bubble_data = json.loads(value)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse bubble data for key: {key}")
                    continue

                # Extract composerId from key pattern: bubbleId:{composerId}:{bubbleId}
                key_parts = key.split(":")
                if len(key_parts) != 3:
                    logger.warning(f"Unexpected bubbleId key format: {key}")
                    continue

                composer_id = key_parts[1]
                bubble_id = key_parts[2]

                # Check if data changed using incremental sync
                if self.incremental_sync.should_process("global", composer_id, key, value):
                    await self._queue_bubble_event(key, composer_id, bubble_id, bubble_data)

        except Exception as e:
            logger.error(f"Error syncing bubble data: {e}")

    async def _queue_bubble_event(self, key: str, composer_id: str, bubble_id: str, data: dict):
        """Queue bubble event to Redis."""
        # Extract relevant bubble fields
        extracted_fields = {
            "composer_id": composer_id,
            "bubble_id": bubble_id,
            "type": data.get("type"),  # 1=user, 2=ai
            "text": data.get("text"),
            "rich_text": data.get("richText"),
            "is_agentic": data.get("isAgentic"),
            "token_count": data.get("tokenCount"),
            "unified_mode": data.get("unifiedMode"),
            "relevant_files": data.get("relevantFiles"),
            "capabilities_ran": data.get("capabilitiesRan"),
            "capability_statuses": data.get("capabilityStatuses"),
            "checkpoint_id": data.get("checkpointId"),
        }

        event = {
            "version": "0.1.0",
            "hook_type": "DatabaseTrace",
            "event_type": "bubble",
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "platform": "cursor",
            "metadata": {
                "storage_level": "global",
                "database_table": "cursorDiskKV",
                "item_key": key,
                "source": "user_level_listener_bubble",
            },
            "payload": {
                "extracted_fields": extracted_fields,
                "full_data": data
            }
        }

        await self.event_queuer.queue_event(event)

    def set_active_workspaces(self, workspaces: Set[str]):
        """Update set of active workspaces."""
        self.active_workspaces = workspaces

    async def stop(self):
        """Stop user-level listener."""
        if self.file_watcher:
            await self.file_watcher.stop()

        if self.connection:
            await self.connection.close()


class UnifiedCursorMonitor:
    """
    Unified monitor with session-aware workspace activation.
    Consolidates all Cursor database telemetry monitoring.
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        session_monitor: SessionMonitor,
        config: Optional[CursorMonitorConfig] = None
    ):
        # Core dependencies
        self.redis_client = redis_client
        self.session_monitor = session_monitor
        self.config = config or CursorMonitorConfig()

        # Initialize components
        self.user_listener = UserLevelListener(redis_client, self.config)
        self.event_queuer = EventQueuer(redis_client)
        self.incremental_sync = IncrementalSync()
        self.smart_cache = SmartCache(ttl_seconds=self.config.cache_ttl)

        # Workspace management
        self.workspace_monitors: Dict[str, WorkspaceMonitor] = {}
        self.file_watchers: Dict[str, FileWatcher] = {}

        # Keys to monitor in workspace ItemTable
        self.workspace_itemtable_keys = [
            "aiService.generations",
            "aiService.prompts",
            "composer.composerData",
            "workbench.backgroundComposer.workspacePersistentData",
            "workbench.agentMode.exitInfo",
            "interactive.sessions",
            "history.entries",
            "cursorAuth/workspaceOpenedDate",
        ]

        # State
        self.running = False
        self.monitoring_task = None

    async def start(self):
        """Start the unified monitor."""
        self.running = True

        # Start user-level listener (runs for entire lifetime)
        await self.user_listener.start()

        # Register session callbacks
        self.session_monitor.on_session_start = self.on_session_start
        self.session_monitor.on_session_end = self.on_session_end

        # Process existing active sessions
        active = self.session_monitor.get_active_workspaces()
        for workspace_hash, session_info in active.items():
            await self.on_session_start(workspace_hash, session_info)

        logger.info("UnifiedCursorMonitor started")

    async def stop(self):
        """Stop the unified monitor."""
        self.running = False

        # Stop all workspace monitors
        for workspace_hash in list(self.workspace_monitors.keys()):
            await self.on_session_end(workspace_hash)

        # Stop user-level listener
        await self.user_listener.stop()

        if self.monitoring_task:
            self.monitoring_task.cancel()

        logger.info("UnifiedCursorMonitor stopped")

    async def on_session_start(self, workspace_hash: str, session_info: dict):
        """
        Activate monitoring for a workspace when session starts.
        Called by SessionMonitor when a new Cursor session begins.
        """
        logger.info(f"Activating monitoring for workspace {workspace_hash}")

        # Skip if already monitoring
        if workspace_hash in self.workspace_monitors:
            logger.debug(f"Already monitoring workspace {workspace_hash}")
            return

        # Find workspace database
        workspace_path = session_info.get("workspace_path")
        db_path = await self._find_workspace_db(workspace_hash, workspace_path)

        if not db_path or not db_path.exists():
            logger.warning(f"Database not found for workspace {workspace_hash}")
            return

        # Extract session_id from session_info
        external_session_id = (
            session_info.get("external_session_id") or
            session_info.get("session_id")
        )

        # Create workspace monitor with session_id
        monitor = WorkspaceMonitor(
            workspace_hash=workspace_hash,
            db_path=db_path,
            redis_client=self.redis_client,
            config=self.config,
            itemtable_keys=self.workspace_itemtable_keys,
            external_session_id=external_session_id
        )
        await monitor.connect()
        self.workspace_monitors[workspace_hash] = monitor

        # Start file watcher
        watcher = FileWatcher(
            db_path,
            lambda: self._on_workspace_db_change(workspace_hash)
        )
        await watcher.start_watching()
        self.file_watchers[workspace_hash] = watcher

        # Initial sync of all data
        await monitor.sync_all_data()

        # Update user-level listener with active workspaces
        self.user_listener.set_active_workspaces(set(self.workspace_monitors.keys()))

        logger.info(f"Activated monitoring for workspace {workspace_hash}")

    async def on_session_end(self, workspace_hash: str):
        """
        Deactivate monitoring when session ends.
        Called by SessionMonitor when a Cursor session terminates.
        """
        logger.info(f"Deactivating monitoring for workspace {workspace_hash}")

        # Stop file watcher
        if workspace_hash in self.file_watchers:
            await self.file_watchers[workspace_hash].stop()
            del self.file_watchers[workspace_hash]

        # Close workspace monitor
        if workspace_hash in self.workspace_monitors:
            await self.workspace_monitors[workspace_hash].close()
            del self.workspace_monitors[workspace_hash]

        # Clear from cache
        self.smart_cache.invalidate(f"{workspace_hash}:*")

        # Update user-level listener with active workspaces
        self.user_listener.set_active_workspaces(set(self.workspace_monitors.keys()))

        logger.info(f"Deactivated monitoring for workspace {workspace_hash}")

    async def _on_workspace_db_change(self, workspace_hash: str):
        """Handle workspace database change."""
        if workspace_hash in self.workspace_monitors:
            await self.workspace_monitors[workspace_hash].sync_all_data()

    async def _find_workspace_db(
        self,
        workspace_hash: str,
        workspace_path: Optional[str]
    ) -> Optional[Path]:
        """Find workspace database file."""
        # Use smart cache
        cache_key = f"db_path:{workspace_hash}"
        cached = await self.smart_cache.get(cache_key)
        if cached:
            db_path = Path(cached)
            if db_path.exists():
                return db_path

        # Try workspace mapper first
        mapper = WorkspaceMapper(self.session_monitor)
        db_path = await mapper.find_database(workspace_hash, workspace_path)

        if db_path and db_path.exists():
            await self.smart_cache.set(cache_key, str(db_path))
            return db_path

        # Check Cursor workspace storage
        # ~/Library/Application Support/Cursor/User/workspaceStorage/{uuid}/state.vscdb
        cursor_storage = Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "workspaceStorage"
        if cursor_storage.exists():
            # Try to find the right workspace directory
            best_match = None
            best_mtime = 0

            for workspace_dir in cursor_storage.iterdir():
                if workspace_dir.is_dir():
                    state_db = workspace_dir / "state.vscdb"
                    if state_db.exists():
                        # Check if workspace.json matches our workspace path
                        workspace_json = workspace_dir / "workspace.json"
                        if workspace_json.exists() and workspace_path:
                            try:
                                import json
                                with open(workspace_json) as f:
                                    data = json.load(f)
                                    folder = data.get("folder", "")
                                    # Remove file:// prefix if present
                                    if folder.startswith("file://"):
                                        folder = folder[7:]
                                    # Check if paths match
                                    if workspace_path == folder or workspace_path in folder or folder in workspace_path:
                                        await self.smart_cache.set(cache_key, str(state_db))
                                        logger.info(f"Found workspace DB at {state_db} (matched by path)")
                                        return state_db
                            except Exception as e:
                                logger.debug(f"Could not read workspace.json: {e}")

                        # Track most recent as fallback
                        mtime = state_db.stat().st_mtime
                        if mtime > best_mtime:
                            best_mtime = mtime
                            best_match = state_db

            # Use most recent database as fallback
            if best_match:
                await self.smart_cache.set(cache_key, str(best_match))
                logger.info(f"Using most recent workspace DB at {best_match}")
                return best_match

        # Fallback: Try workspace path .vscode directory (legacy)
        if workspace_path:
            workspace_dir = Path(workspace_path)

            # Check .vscode directory
            vscode_db = workspace_dir / ".vscode" / ".vscdb"
            if vscode_db.exists():
                await self.smart_cache.set(cache_key, str(vscode_db))
                return vscode_db

            # Check numbered versions
            for i in range(10):
                vscode_db = workspace_dir / ".vscode" / f"{i}.vscdb"
                if vscode_db.exists():
                    await self.smart_cache.set(cache_key, str(vscode_db))
                    return vscode_db

        logger.warning(f"Could not find workspace database for {workspace_hash} at path {workspace_path}")
        return None
