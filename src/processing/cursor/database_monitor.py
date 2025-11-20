# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Database Monitor for Cursor's SQLite database.

Production-ready with:
- Aggressive timeouts (1-2s max)
- Retry with exponential backoff
- Deduplication
- Zero-impact on Cursor performance
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional, Set, Tuple
import aiosqlite
import redis

from .session_monitor import SessionMonitor
from .workspace_mapper import WorkspaceMapper

logger = logging.getLogger(__name__)

# ItemTable keys for AI service data
GENERATIONS_KEY = "aiService.generations"
PROMPTS_KEY = "aiService.prompts"


class CursorDatabaseMonitor:
    """
    Monitor Cursor's SQLite database for AI generations.

    Design Principles:
    1. Zero impact on Cursor performance (read-only, timeouts)
    2. Robust error handling (retries, fallbacks)
    3. Deduplication (prevent hook + monitor duplicates)
    """

    def __init__(
        self,
        redis_client: redis.Redis,
        session_monitor: SessionMonitor,
        poll_interval: float = 30.0,
        sync_window_hours: int = 24,
        query_timeout: float = 1.5,  # Aggressive timeout
        max_retries: int = 3,
    ):
        self.redis_client = redis_client
        self.session_monitor = session_monitor
        self.workspace_mapper = WorkspaceMapper(session_monitor)

        self.poll_interval = poll_interval
        self.sync_window_hours = sync_window_hours
        self.query_timeout = query_timeout
        self.max_retries = max_retries

        # Track last synced timestamp per workspace (unixMs milliseconds)
        self.last_synced_timestamp: Dict[str, int] = {}

        # Database connections (lazy-loaded, one per workspace)
        self.db_connections: Dict[str, aiosqlite.Connection] = {}

        # Deduplication: Track seen generation_ids
        self.seen_generations: Set[Tuple[str, str]] = set()  # (workspace_hash, generation_id)
        self.generation_ttl: Dict[Tuple[str, str], float] = {}  # TTL for cleanup
        self.dedup_window_hours = 24  # Keep dedup cache for 24 hours

        # Health tracking
        self.health_stats: Dict[str, dict] = {}  # workspace_hash -> stats

        self.running = False

    async def start(self):
        """Start database monitoring."""
        self.running = True

        # Start monitoring loop
        asyncio.create_task(self._monitor_loop())

        # Start deduplication cleanup
        asyncio.create_task(self._cleanup_dedup_cache())

        logger.info("Database monitor started")
        
        # Log initial state
        active = self.session_monitor.get_active_workspaces()
        logger.info(f"Monitoring {len(active)} active workspace(s): {list(active.keys())}")

    async def stop(self):
        """Stop database monitoring."""
        self.running = False

        # Close all connections
        for conn in self.db_connections.values():
            try:
                await conn.close()
            except:
                pass
        self.db_connections.clear()

        logger.info("Database monitor stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self.running:
            try:
                # Get active workspaces
                active_workspaces = self.session_monitor.get_active_workspaces()

                # Monitor each active workspace
                for workspace_hash, session_info in active_workspaces.items():
                    await self._monitor_workspace(workspace_hash, session_info)

                # Clean up inactive workspaces
                await self._cleanup_inactive_workspaces(active_workspaces.keys())

                await asyncio.sleep(self.poll_interval)

            except Exception as e:
                logger.error(f"Error in monitor loop: {e}")
                await asyncio.sleep(5)

    async def _monitor_workspace(self, workspace_hash: str, session_info: dict):
        """Monitor a specific workspace."""
        try:
            # Find database path
            workspace_path = session_info.get("workspace_path")
            db_path = await self.workspace_mapper.find_database(
                workspace_hash,
                workspace_path
            )

            if not db_path or not db_path.exists():
                logger.warning(f"No database found for workspace {workspace_hash} (path: {workspace_path})")
                return
            
            logger.debug(f"Found database for workspace {workspace_hash}: {db_path}")

            # Ensure connection exists (lazy loading)
            if workspace_hash not in self.db_connections:
                success = await self._open_database(workspace_hash, db_path)
                if not success:
                    return

                # Sync on first open (session start)
                await self._sync_session_start(workspace_hash, session_info, db_path)

            # Check for new generations
            await self._check_for_changes(workspace_hash, session_info, db_path)

        except Exception as e:
            logger.error(f"Error monitoring workspace {workspace_hash}: {e}")
            self._update_health(workspace_hash, "error", str(e))

    async def _open_database(
        self,
        workspace_hash: str,
        db_path: Path
    ) -> bool:
        """Open database connection with aggressive timeouts."""
        try:
            # Open connection with short timeout
            conn = await asyncio.wait_for(
                aiosqlite.connect(
                    str(db_path),
                    timeout=self.query_timeout,
                    check_same_thread=False
                ),
                timeout=self.query_timeout
            )

            # Configure for read-only, non-blocking
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA read_uncommitted=1")
            await conn.execute("PRAGMA query_only=1")  # Read-only mode

            # Verify ItemTable exists and has generations key
            try:
                cursor = await conn.execute('''
                    SELECT COUNT(*) FROM ItemTable WHERE key = ?
                ''', (GENERATIONS_KEY,))
                row = await cursor.fetchone()
                if row and row[0] == 0:
                    logger.debug(f"Generations key {GENERATIONS_KEY} not found in {db_path} (may be empty)")
                    # Don't fail - empty databases are valid
            except Exception as e:
                logger.warning(f"Error checking ItemTable: {e}")
                await conn.close()
                return False

            self.db_connections[workspace_hash] = conn

            logger.info(f"Opened database for workspace {workspace_hash}")
            self._update_health(workspace_hash, "connected", None)
            return True

        except asyncio.TimeoutError:
            logger.warning(f"Timeout opening database {db_path}")
            return False
        except Exception as e:
            logger.error(f"Failed to open database {db_path}: {e}")
            return False

    async def _sync_session_start(
        self,
        workspace_hash: str,
        session_info: dict,
        db_path: Path
    ):
        """Sync all generations since last sync on session start."""
        conn = self.db_connections.get(workspace_hash)
        if not conn:
            return

        try:
            # Get last synced timestamp
            last_timestamp_ms = self.last_synced_timestamp.get(workspace_hash, 0)

            # If no last timestamp, sync from sync window
            if last_timestamp_ms == 0:
                cutoff_timestamp_ms = int(time.time() * 1000) - (self.sync_window_hours * 3600 * 1000)
                last_timestamp_ms = cutoff_timestamp_ms

            # Capture new generations since last timestamp
            await self._capture_new_generations(
                workspace_hash,
                session_info,
                db_path,
                last_timestamp_ms
            )

        except Exception as e:
            logger.error(f"Error syncing session start for {workspace_hash}: {e}")

    async def _check_for_changes(
        self,
        workspace_hash: str,
        session_info: dict,
        db_path: Path
    ):
        """Check for new generations with retry logic."""
        conn = self.db_connections.get(workspace_hash)
        if not conn:
            return

        last_timestamp_ms = self.last_synced_timestamp.get(workspace_hash, 0)

        # Retry logic with exponential backoff
        for attempt in range(self.max_retries):
            try:
                # Check for new generations since last timestamp
                await asyncio.wait_for(
                    self._capture_new_generations(
                        workspace_hash,
                        session_info,
                        db_path,
                        last_timestamp_ms
                    ),
                    timeout=self.query_timeout
                )

                self._update_health(workspace_hash, "synced", None)
                break  # Success, exit retry loop

            except asyncio.TimeoutError:
                logger.warning(
                    f"Query timeout for {workspace_hash} (attempt {attempt + 1})"
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                else:
                    self._update_health(workspace_hash, "timeout", None)

            except Exception as e:
                error_str = str(e).lower()
                if "locked" in error_str:
                    logger.debug(f"Database locked for {workspace_hash}, retrying...")
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        self._update_health(workspace_hash, "locked", None)
                else:
                    logger.error(f"Error checking changes for {workspace_hash}: {e}")
                    break

    async def _get_generations_from_itemtable(
        self,
        conn: aiosqlite.Connection
    ) -> list:
        """Read generations array from ItemTable."""
        try:
            cursor = await conn.execute('''
                SELECT value FROM ItemTable WHERE key = ?
            ''', (GENERATIONS_KEY,))
            row = await cursor.fetchone()
            
            if not row or not row[0]:
                return []
            
            # Parse JSON array
            value_str = row[0]
            if isinstance(value_str, bytes):
                value_str = value_str.decode('utf-8')
            
            generations = json.loads(value_str)
            
            if not isinstance(generations, list):
                logger.warning(f"Expected list for {GENERATIONS_KEY}, got {type(generations)}")
                return []
            
            return generations
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse generations JSON: {e}")
            return []
        except Exception as e:
            logger.debug(f"Error reading generations from ItemTable: {e}")
            return []

    async def _get_prompts_from_itemtable(
        self,
        conn: aiosqlite.Connection
    ) -> list:
        """Read prompts array from ItemTable."""
        try:
            cursor = await conn.execute('''
                SELECT value FROM ItemTable WHERE key = ?
            ''', (PROMPTS_KEY,))
            row = await cursor.fetchone()
            
            if not row or not row[0]:
                return []
            
            # Parse JSON array
            value_str = row[0]
            if isinstance(value_str, bytes):
                value_str = value_str.decode('utf-8')
            
            prompts = json.loads(value_str)
            
            if not isinstance(prompts, list):
                logger.warning(f"Expected list for {PROMPTS_KEY}, got {type(prompts)}")
                return []
            
            return prompts
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse prompts JSON: {e}")
            return []
        except Exception as e:
            logger.debug(f"Error reading prompts from ItemTable: {e}")
            return []

    async def _capture_new_generations(
        self,
        workspace_hash: str,
        session_info: dict,
        db_path: Path,
        last_timestamp_ms: int
    ):
        """Capture new generations since last timestamp."""
        conn = self.db_connections.get(workspace_hash)
        if not conn:
            return

        try:
            # Read generations array from ItemTable
            all_generations = await self._get_generations_from_itemtable(conn)
            
            if not all_generations:
                logger.debug(f"No generations found for {workspace_hash}")
                return
            
            # Filter generations newer than last timestamp
            new_generations = [
                gen for gen in all_generations
                if isinstance(gen, dict) and gen.get('unixMs', 0) > last_timestamp_ms
            ]
            
            # Sort by timestamp
            new_generations.sort(key=lambda g: g.get('unixMs', 0))
            
            logger.info(f"Found {len(new_generations)} new generations for {workspace_hash} (since {last_timestamp_ms})")
            
            # Update last synced timestamp
            if new_generations:
                max_timestamp = max(gen.get('unixMs', 0) for gen in new_generations)
                self.last_synced_timestamp[workspace_hash] = max_timestamp
            
            # Process each generation
            for gen in new_generations:
                await self._process_generation(gen, workspace_hash, session_info)

        except asyncio.TimeoutError:
            logger.warning(f"Query timeout capturing changes for {workspace_hash}")
        except Exception as e:
            logger.error(f"Error capturing changes: {e}")

    async def _process_generation(
        self,
        gen: dict,
        workspace_hash: str,
        session_info: dict
    ):
        """Process generation with deduplication."""
        # Extract generation UUID (actual field name is generationUUID)
        generation_id = gen.get("generationUUID")
        if not generation_id:
            logger.warning(f"Generation missing generationUUID: {gen}")
            return

        # Deduplication check
        dedup_key = (workspace_hash, generation_id)
        if dedup_key in self.seen_generations:
            logger.debug(f"Skipping duplicate generation: {generation_id}")
            return

        # Mark as seen
        self.seen_generations.add(dedup_key)
        self.generation_ttl[dedup_key] = time.time()

        try:
            # Extract timestamp (unixMs is in milliseconds, convert to ISO format)
            unix_ms = gen.get("unixMs", 0)
            if unix_ms:
                timestamp_iso = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(unix_ms / 1000))
            else:
                timestamp_iso = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())

            # Build event payload
            # Note: Cursor ItemTable structure does not contain model, tokens, or duration fields
            # Only includes fields that actually exist in the data structure
            payload = {
                "trace_type": "generation",
                "generation_id": generation_id,
                "generation_type": gen.get("type", "unknown"),
                "description": gen.get("textDescription", ""),

                # Timestamps
                "generation_timestamp_ms": unix_ms,
                "generation_timestamp": timestamp_iso,

                # model, tokens_used, duration_ms not included - not in Cursor ItemTable structure
                # response_text, prompt_text, prompt_id not included - not in data structure

                # Full data for complete capture
                "full_generation_data": gen,
            }

            # Build event
            external_session_id = session_info.get("external_session_id") or session_info.get("session_id")
            internal_session_id = session_info.get("internal_session_id")

            event = {
                "version": "0.1.0",
                "hook_type": "DatabaseTrace",
                "event_type": "database_trace",
                "timestamp": timestamp_iso or time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime()),
                "platform": "cursor",
                "session_id": external_session_id,
                "external_session_id": external_session_id,
                "metadata": {
                    "workspace_hash": workspace_hash,
                    "source": "python_monitor",
                },
                "payload": payload,
            }

            if internal_session_id:
                event["metadata"]["internal_session_id"] = internal_session_id

            # Send to Redis
            self.redis_client.xadd(
                "telemetry:events",
                {
                    k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                    for k, v in event.items()
                },
                maxlen=10000,
                approximate=True
            )

            logger.debug(f"Captured generation: {generation_id}")

        except Exception as e:
            logger.error(f"Error processing generation: {e}")

    async def _cleanup_dedup_cache(self):
        """Clean up old deduplication cache entries."""
        while self.running:
            await asyncio.sleep(3600)  # Every hour

            cutoff_time = time.time() - (self.dedup_window_hours * 3600)
            to_remove = [
                key for key, ttl in self.generation_ttl.items()
                if ttl < cutoff_time
            ]

            for key in to_remove:
                self.seen_generations.discard(key)
                del self.generation_ttl[key]

            if to_remove:
                logger.debug(f"Cleaned up {len(to_remove)} deduplication entries")

    async def _cleanup_inactive_workspaces(self, active_hashes: set):
        """Clean up resources for inactive workspaces."""
        inactive = set(self.db_connections.keys()) - active_hashes

        for workspace_hash in inactive:
            if workspace_hash in self.db_connections:
                try:
                    await self.db_connections[workspace_hash].close()
                except:
                    pass
                del self.db_connections[workspace_hash]

            # Clear health stats
            if workspace_hash in self.health_stats:
                del self.health_stats[workspace_hash]

            logger.info(f"Cleaned up inactive workspace: {workspace_hash}")

    def _update_health(self, workspace_hash: str, status: str, value):
        """Update health statistics."""
        if workspace_hash not in self.health_stats:
            self.health_stats[workspace_hash] = {
                "last_check": time.time(),
                "status": "unknown",
                "errors": 0,
            }

        self.health_stats[workspace_hash]["last_check"] = time.time()
        self.health_stats[workspace_hash]["status"] = status

        if status == "error":
            self.health_stats[workspace_hash]["errors"] += 1



