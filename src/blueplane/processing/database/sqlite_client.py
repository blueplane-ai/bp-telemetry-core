# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
SQLite client for Blueplane Telemetry Core.

Provides connection management, initialization, and optimized settings
for high-throughput writes with WAL mode.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, ContextManager
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class SQLiteClient:
    """
    SQLite client with optimized settings for telemetry ingestion.
    
    Features:
    - WAL mode for concurrent reads/writes
    - Optimized PRAGMA settings for performance
    - Connection pooling via context managers
    - Automatic database initialization
    """

    def __init__(self, db_path: str):
        """
        Initialize SQLite client.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path).expanduser()
        self._connection: Optional[sqlite3.Connection] = None

    def initialize_database(self) -> None:
        """
        Initialize database with optimal settings and create directory if needed.
        """
        # Create parent directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Open connection and configure
        conn = sqlite3.connect(str(self.db_path))
        try:
            # Enable WAL mode for concurrent access
            conn.execute("PRAGMA journal_mode=WAL")
            
            # Balance durability vs speed (NORMAL is good for WAL)
            conn.execute("PRAGMA synchronous=NORMAL")
            
            # Set cache size to 64MB (negative value means KB)
            conn.execute("PRAGMA cache_size=-64000")
            
            # Use memory for temporary tables
            conn.execute("PRAGMA temp_store=MEMORY")
            
            # Enable mmap for faster reads (256MB)
            conn.execute("PRAGMA mmap_size=268435456")
            
            # Set foreign keys (for future conversation tables)
            conn.execute("PRAGMA foreign_keys=ON")
            
            conn.commit()
            logger.info(f"Initialized SQLite database at {self.db_path}")
        except Exception as e:
            conn.close()
            raise RuntimeError(f"Failed to initialize database: {e}") from e
        finally:
            conn.close()

    @contextmanager
    def get_connection(self) -> ContextManager[sqlite3.Connection]:
        """
        Get a database connection with context manager.

        Yields:
            sqlite3.Connection configured with optimal settings
        """
        conn = sqlite3.connect(str(self.db_path))
        try:
            # Ensure WAL mode is enabled
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-64000")
            conn.row_factory = sqlite3.Row
            yield conn
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def execute(self, query: str, params: tuple = ()) -> None:
        """
        Execute a single query.

        Args:
            query: SQL query string
            params: Query parameters
        """
        with self.get_connection() as conn:
            conn.execute(query, params)
            conn.commit()

    def executemany(self, query: str, params: list[tuple]) -> None:
        """
        Execute a query multiple times with different parameters.

        Args:
            query: SQL query string
            params: List of parameter tuples
        """
        with self.get_connection() as conn:
            conn.executemany(query, params)
            conn.commit()

    def execute_script(self, script: str) -> None:
        """
        Execute a SQL script (multiple statements).

        Args:
            script: SQL script string
        """
        with self.get_connection() as conn:
            conn.executescript(script)
            conn.commit()

    def exists(self) -> bool:
        """
        Check if database file exists.

        Returns:
            True if database file exists
        """
        return self.db_path.exists()

