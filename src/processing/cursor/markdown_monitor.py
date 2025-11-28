# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Cursor Markdown History Monitor.

Watches Cursor workspace databases and writes Markdown history files.
"""

import asyncio
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Set
import aiosqlite

from .session_monitor import SessionMonitor
from .workspace_mapper import WorkspaceMapper
from .markdown_writer import CursorMarkdownWriter, TRACE_RELEVANT_KEYS

logger = logging.getLogger(__name__)

# Optional DuckDB support
try:
    from .duckdb_writer import CursorDuckDBWriter, DUCKDB_AVAILABLE
except ImportError:
    DUCKDB_AVAILABLE = False
    CursorDuckDBWriter = None


class CursorMarkdownMonitor:
    """
    Monitor Cursor workspace databases and write Markdown history files.
    
    Uses file watching with polling fallback for reliability.
    Implements debounce to avoid excessive writes.
    """

    def __init__(
        self,
        session_monitor: SessionMonitor,
        output_dir: Optional[Path] = None,
        poll_interval: float = 120.0,  # 2-minute polling fallback
        debounce_delay: float = 10.0,  # Default 10-12s for normal operation
        query_timeout: float = 1.5,
        enable_duckdb: bool = False,
        duckdb_path: Optional[Path] = None,
    ):
        """
        Initialize Markdown monitor.

        Args:
            session_monitor: Session monitor for workspace tracking
            output_dir: Base directory for output (default: workspace/.history/)
            poll_interval: Polling interval in seconds (default: 120s / 2 minutes)
            debounce_delay: Delay before writing after change (default: 10s)
            query_timeout: Timeout for database queries (default: 1.5s)
            enable_duckdb: Enable DuckDB sink (default: False)
            duckdb_path: Path to DuckDB database (default: ~/.blueplane/cursor_history.duckdb)
        """
        self.session_monitor = session_monitor
        self.workspace_mapper = WorkspaceMapper(session_monitor)
        self.markdown_writer = CursorMarkdownWriter(output_dir)
        
        self.poll_interval = poll_interval
        self.debounce_delay = debounce_delay
        self.query_timeout = query_timeout
        
        # Optional DuckDB support
        self.enable_duckdb = enable_duckdb and DUCKDB_AVAILABLE
        self.duckdb_writer: Optional[CursorDuckDBWriter] = None
        
        if self.enable_duckdb:
            if DUCKDB_AVAILABLE:
                self.duckdb_writer = CursorDuckDBWriter(duckdb_path)
                logger.info("DuckDB sink enabled")
            else:
                logger.warning(
                    "DuckDB sink requested but DuckDB not available. "
                    "Install with: pip install duckdb>=0.9.0"
                )
                self.enable_duckdb = False
        
        # Track last written state per workspace
        self.last_data_hash: Dict[str, str] = {}  # workspace_hash -> data hash
        self.pending_writes: Dict[str, asyncio.Task] = {}  # workspace_hash -> debounce task
        
        # Database connections (lazy-loaded)
        self.db_connections: Dict[str, aiosqlite.Connection] = {}
        
        self.running = False

    async def start(self):
        """Start monitoring."""
        self.running = True
        
        # Start polling loop (acts as both poller and file watcher fallback)
        asyncio.create_task(self._polling_loop())
        
        logger.info(
            f"Markdown monitor started (poll_interval={self.poll_interval}s, "
            f"debounce_delay={self.debounce_delay}s)"
        )

    async def stop(self):
        """Stop monitoring."""
        self.running = False
        
        # Cancel pending writes
        for task in self.pending_writes.values():
            task.cancel()
        self.pending_writes.clear()
        
        # Close all connections
        for conn in self.db_connections.values():
            try:
                await conn.close()
            except Exception:
                pass
        self.db_connections.clear()
        
        # Close DuckDB connection
        if self.duckdb_writer:
            try:
                self.duckdb_writer.close()
            except Exception:
                pass
        
        logger.info("Markdown monitor stopped")

    async def _polling_loop(self):
        """Main polling loop - checks all active workspaces periodically."""
        while self.running:
            try:
                # Get active workspaces
                active_workspaces = self.session_monitor.get_active_workspaces()
                
                # Check each workspace
                for workspace_hash, session_info in active_workspaces.items():
                    await self._check_workspace(workspace_hash, session_info)
                
                # Clean up inactive workspaces
                await self._cleanup_inactive_workspaces(active_workspaces.keys())
                
                # Sleep until next poll
                await asyncio.sleep(self.poll_interval)
            
            except Exception as e:
                logger.error(f"Error in polling loop: {e}")
                await asyncio.sleep(5)

    async def _check_workspace(self, workspace_hash: str, session_info: dict):
        """
        Check a workspace for changes and trigger write if needed.

        Args:
            workspace_hash: Hash of workspace path
            session_info: Session information dictionary
        """
        try:
            # Find database path
            workspace_path = session_info.get("workspace_path")
            session_id = session_info.get("session_id")
            
            logger.debug(
                f"Checking workspace {workspace_hash} (session: {session_id}, path: {workspace_path})"
            )
            
            db_path = await self.workspace_mapper.find_database(
                workspace_hash,
                workspace_path
            )
            
            if not db_path or not db_path.exists():
                logger.debug(f"No database found for workspace {workspace_hash}")
                return
            
            logger.debug(f"Found database for workspace {workspace_hash}: {db_path}")
            
            # Ensure connection exists
            if workspace_hash not in self.db_connections:
                success = await self._open_database(workspace_hash, db_path)
                if not success:
                    return

                logger.info(
                    f"Workspace mapping: hash={workspace_hash}, session={session_id}, "
                    f"path={workspace_path}, db={db_path}"
                )
            
            # Read current data
            current_data = await self._read_workspace_data(workspace_hash, db_path)
            
            if not current_data:
                logger.debug(f"No data available for workspace {workspace_hash}")
                return
            
            # Compute hash of current data
            current_hash = self._compute_data_hash(current_data)
            
            # Check if data changed
            last_hash = self.last_data_hash.get(workspace_hash)
            
            if current_hash != last_hash:
                logger.info(
                    f"Detected change in workspace {workspace_hash} (session: {session_id}), "
                    f"scheduling write after {self.debounce_delay}s debounce"
                )
                
                # Cancel existing pending write if any
                if workspace_hash in self.pending_writes:
                    self.pending_writes[workspace_hash].cancel()
                
                # Schedule debounced write
                task = asyncio.create_task(
                    self._debounced_write(
                        workspace_hash,
                        workspace_path,
                        current_data,
                        current_hash
                    )
                )
                self.pending_writes[workspace_hash] = task
        
        except Exception as e:
            logger.error(f"Error checking workspace {workspace_hash}: {e}")

    async def _open_database(
        self,
        workspace_hash: str,
        db_path: Path
    ) -> bool:
        """
        Open database connection.

        Args:
            workspace_hash: Hash of workspace path
            db_path: Path to database file

        Returns:
            True if successful, False otherwise
        """
        try:
            conn = await asyncio.wait_for(
                aiosqlite.connect(
                    str(db_path),
                    timeout=self.query_timeout,
                    check_same_thread=False
                ),
                timeout=self.query_timeout
            )
            
            # Configure for read-only
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA read_uncommitted=1")
            await conn.execute("PRAGMA query_only=1")
            
            self.db_connections[workspace_hash] = conn
            logger.info(f"Opened database for workspace {workspace_hash}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to open database {db_path}: {e}")
            return False

    async def _read_workspace_data(
        self,
        workspace_hash: str,
        db_path: Path
    ) -> Optional[Dict[str, any]]:
        """
        Read all relevant data from workspace database.

        Args:
            workspace_hash: Hash of workspace path
            db_path: Path to database file

        Returns:
            Dictionary of key-value pairs or None if error
        """
        conn = self.db_connections.get(workspace_hash)
        if not conn:
            return None
        
        try:
            data = {}
            
            # Read each relevant key from ItemTable
            for key in TRACE_RELEVANT_KEYS:
                try:
                    cursor = await asyncio.wait_for(
                        conn.execute(
                            'SELECT value FROM ItemTable WHERE key = ?',
                            (key,)
                        ),
                        timeout=self.query_timeout
                    )
                    row = await cursor.fetchone()
                    
                    if row and row[0]:
                        data[key] = row[0]
                
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout reading key {key} for workspace {workspace_hash}")
                except Exception as e:
                    logger.debug(f"Error reading key {key} for workspace {workspace_hash}: {e}")
            
            return data if data else None
        
        except Exception as e:
            logger.error(f"Error reading workspace data for {workspace_hash}: {e}")
            return None

    def _compute_data_hash(self, data: Dict[str, any]) -> str:
        """
        Compute hash of data to detect changes.

        Args:
            data: Dictionary of key-value pairs

        Returns:
            SHA256 hash of data
        """
        # Create a stable representation of data
        sorted_items = sorted(data.items())
        
        # Build hash input
        hash_input = []
        for key, value in sorted_items:
            if isinstance(value, bytes):
                hash_input.append(f"{key}:{value.hex()}")
            else:
                hash_input.append(f"{key}:{value}")
        
        # Compute hash
        hash_str = "|".join(hash_input)
        return hashlib.sha256(hash_str.encode('utf-8')).hexdigest()

    async def _debounced_write(
        self,
        workspace_hash: str,
        workspace_path: str,
        data: Dict[str, any],
        data_hash: str
    ):
        """
        Write Markdown file after debounce delay.

        Args:
            workspace_hash: Hash of workspace path
            workspace_path: Path to workspace
            data: Data to write
            data_hash: Hash of data
        """
        try:
            # Wait for debounce delay
            await asyncio.sleep(self.debounce_delay)
            
            # Write Markdown file
            timestamp = datetime.now()
            filepath = self.markdown_writer.write_workspace_history(
                workspace_path,
                workspace_hash,
                data,
                timestamp
            )
            
            # Write to DuckDB if enabled
            if self.enable_duckdb and self.duckdb_writer:
                try:
                    self.duckdb_writer.write_workspace_history(
                        workspace_hash,
                        workspace_path,
                        data,
                        data_hash,
                        timestamp,
                        filepath
                    )
                    logger.info(f"Wrote workspace snapshot to DuckDB for {workspace_hash}")
                except Exception as e:
                    logger.error(f"Error writing to DuckDB for workspace {workspace_hash}: {e}")
            
            # Update last hash
            self.last_data_hash[workspace_hash] = data_hash
            
            logger.info(f"Wrote Markdown history for workspace {workspace_hash} to {filepath}")
        
        except asyncio.CancelledError:
            logger.debug(f"Debounced write cancelled for workspace {workspace_hash}")
        except Exception as e:
            logger.error(f"Error writing Markdown for workspace {workspace_hash}: {e}")
        finally:
            # Remove from pending writes
            self.pending_writes.pop(workspace_hash, None)

    async def _cleanup_inactive_workspaces(self, active_hashes: Set[str]):
        """
        Clean up connections and state for inactive workspaces.

        Args:
            active_hashes: Set of currently active workspace hashes
        """
        inactive_hashes = set(self.db_connections.keys()) - set(active_hashes)
        
        for workspace_hash in inactive_hashes:
            # Cancel pending write
            if workspace_hash in self.pending_writes:
                self.pending_writes[workspace_hash].cancel()
                self.pending_writes.pop(workspace_hash, None)
            
            # Close connection
            conn = self.db_connections.pop(workspace_hash, None)
            if conn:
                try:
                    await conn.close()
                    logger.info(f"Closed database connection for inactive workspace {workspace_hash}")
                except Exception:
                    pass
            
            # Clean up state
            self.last_data_hash.pop(workspace_hash, None)
