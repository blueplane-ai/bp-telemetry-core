# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Workspace-to-Database Mapper.

Maps workspace_hash to state.vscdb files using workspace path hash matching.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List
import aiosqlite

from .platform import get_cursor_database_paths

logger = logging.getLogger(__name__)


class WorkspaceMapper:
    """
    Map workspace_hash to database files using workspace path hash matching.

    Strategy:
    1. Hash workspace path (SHA256, first 16 chars)
    2. Match against database directory names
    3. Search database contents if directory name doesn't match
    4. Cache successful mappings
    """

    def __init__(self, session_monitor):
        self.session_monitor = session_monitor
        self.mapping_cache: Dict[str, Path] = {}  # workspace_hash -> db_path
        self.cache_file = Path.home() / ".blueplane" / "workspace_db_cache.json"
        self._load_cache()

    def _load_cache(self):
        """Load cached mappings from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file) as f:
                    cache_data = json.load(f)
                    for workspace_hash, db_path_str in cache_data.items():
                        db_path = Path(db_path_str)
                        if db_path.exists():
                            self.mapping_cache[workspace_hash] = db_path
                logger.info(f"Loaded {len(self.mapping_cache)} cached mappings")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

    def _save_cache(self):
        """Save mappings to disk."""
        try:
            cache_data = {
                hash: str(path)
                for hash, path in self.mapping_cache.items()
            }
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f)
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    async def find_database(
        self,
        workspace_hash: str,
        workspace_path: Optional[str] = None
    ) -> Optional[Path]:
        """
        Find database file for workspace using path hash matching.

        Returns:
            Path to state.vscdb or None if not found
        """
        # Check cache first
        if workspace_hash in self.mapping_cache:
            cached_path = self.mapping_cache[workspace_hash]
            if cached_path.exists():
                return cached_path
            else:
                # Cache invalid, remove it
                del self.mapping_cache[workspace_hash]

        # Workspace path hash matching
        if workspace_path:
            db_path = await self._match_by_path_hash(workspace_path)
            if db_path:
                self.mapping_cache[workspace_hash] = db_path
                self._save_cache()
                return db_path

        logger.debug(f"Could not map workspace {workspace_hash}")
        return None

    async def _match_by_path_hash(self, workspace_path: str) -> Optional[Path]:
        """
        Hash workspace path and match against database directories.

        Cursor stores databases in workspaceStorage/{uuid}/state.vscdb
        We hash the workspace path and try to match it.
        """
        # Hash workspace path (same algorithm as extension)
        workspace_hash_obj = hashlib.sha256(workspace_path.encode())
        workspace_hash_hex = workspace_hash_obj.hexdigest()[:16]

        # Search all database directories
        for db_path in self._discover_all_databases():
            # Check if directory name or parent matches hash pattern
            parent_dir = db_path.parent.name

            # Try exact match first (directory name contains the hash)
            if workspace_hash_hex.lower() in parent_dir.lower():
                logger.info(f"Matched database by directory hash: {db_path}")
                return db_path

            # Try checking database contents for workspace path
            if await self._db_contains_path(db_path, workspace_path):
                logger.info(f"Matched database by content search: {db_path}")
                return db_path

        # Fallback: If we can't match by hash, try to find the database
        # with the most recent activity in aiService.generations
        logger.debug(f"Hash matching failed, trying fallback for {workspace_path}")
        return await self._find_most_recent_database()

    async def _db_contains_path(self, db_path: Path, workspace_path: str) -> bool:
        """Check if database contains workspace path reference."""
        try:
            async with aiosqlite.connect(str(db_path), timeout=1.0) as conn:
                await conn.execute("PRAGMA read_uncommitted=1")

                # Check various tables for workspace path
                cursor = await conn.execute('''
                    SELECT name FROM sqlite_master
                    WHERE type='table'
                ''')
                tables = [row[0] for row in await cursor.fetchall()]

                # Search in common tables
                for table in tables:
                    try:
                        cursor = await conn.execute(f'''
                            SELECT * FROM "{table}"
                            WHERE value LIKE ? OR text LIKE ?
                            LIMIT 1
                        ''', (f'%{workspace_path}%', f'%{workspace_path}%'))
                        if await cursor.fetchone():
                            return True
                    except Exception:
                        continue
        except Exception:
            pass

        return False

    def _discover_all_databases(self) -> List[Path]:
        """Discover all Cursor database files."""
        databases = []

        for base_path in get_cursor_database_paths():
            if not base_path.exists():
                continue

            for workspace_dir in base_path.iterdir():
                if not workspace_dir.is_dir():
                    continue

                db_file = workspace_dir / "state.vscdb"
                if db_file.exists():
                    databases.append(db_file)

        return databases

    async def _find_most_recent_database(self) -> Optional[Path]:
        """
        Fallback: Find database with most recent activity in aiService.generations.
        
        This is a last resort when hash matching fails.
        Checks ItemTable for generations key instead of table.
        """
        databases = self._discover_all_databases()
        most_recent_db = None
        most_recent_timestamp = 0

        logger.debug(f"Fallback: checking {len(databases)} databases for aiService.generations")

        for db_path in databases:
            try:
                async with aiosqlite.connect(str(db_path), timeout=2.0) as conn:
                    await conn.execute("PRAGMA read_uncommitted=1")

                    # Check if ItemTable has generations key
                    cursor = await conn.execute('''
                        SELECT value FROM ItemTable WHERE key = 'aiService.generations'
                    ''')
                    row = await cursor.fetchone()
                    if not row or not row[0]:
                        continue

                    # Parse JSON array and find max timestamp
                    try:
                        value_str = row[0]
                        if isinstance(value_str, bytes):
                            value_str = value_str.decode('utf-8')
                        generations = json.loads(value_str)
                        
                        if isinstance(generations, list) and len(generations) > 0:
                            # Find max unixMs timestamp
                            max_ts = max(
                                (gen.get('unixMs', 0) for gen in generations if isinstance(gen, dict)),
                                default=0
                            )
                            if max_ts > most_recent_timestamp:
                                most_recent_timestamp = max_ts
                                most_recent_db = db_path
                                logger.debug(f"Found candidate database: {db_path} (timestamp: {max_ts})")
                    except (json.JSONDecodeError, Exception) as e:
                        logger.debug(f"Error parsing generations from {db_path}: {e}")
                        continue
            except Exception as e:
                logger.debug(f"Error checking database {db_path}: {e}")
                continue

        if most_recent_db:
            logger.info(f"Using most recent database as fallback: {most_recent_db} (timestamp: {most_recent_timestamp})")
        else:
            logger.warning("Fallback: No database found with aiService.generations data")
        return most_recent_db



