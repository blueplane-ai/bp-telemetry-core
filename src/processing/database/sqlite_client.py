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


def _split_sql_statements(script: str) -> list[str]:
    """
    Split SQL script into individual statements, handling embedded semicolons.

    Correctly handles:
    - Semicolons inside single-quoted strings ('foo;bar')
    - Semicolons inside double-quoted identifiers ("col;name")
    - Semicolons inside single-line comments (-- comment;)
    - Semicolons inside block comments (/* comment; */)
    - Escaped quotes in SQLite style ('O''Brien' -> O'Brien)

    Note: SQLite string escaping rules:
    - Backslash is NOT an escape character in SQLite strings
    - Literal '\\n' in a string is two characters (backslash + n), not a newline
    - Single quotes are escaped by doubling them: '' represents one quote
    - This parser follows SQLite's escaping conventions, not C-style escaping

    Args:
        script: SQL script with multiple statements

    Returns:
        List of individual SQL statements (stripped, non-empty)
    """
    statements = []
    current = []
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    chars = script

    while i < len(chars):
        c = chars[i]
        next_c = chars[i + 1] if i + 1 < len(chars) else ''

        # Handle line comments
        if not in_single_quote and not in_double_quote and not in_block_comment:
            if c == '-' and next_c == '-':
                in_line_comment = True
                current.append(c)
                i += 1
                continue

        # Handle end of line comment
        if in_line_comment and c == '\n':
            in_line_comment = False
            current.append(c)
            i += 1
            continue

        # Handle block comments
        if not in_single_quote and not in_double_quote and not in_line_comment:
            if c == '/' and next_c == '*':
                in_block_comment = True
                current.append(c)
                i += 1
                continue
            if in_block_comment and c == '*' and next_c == '/':
                in_block_comment = False
                current.append(c)
                current.append(next_c)
                i += 2
                continue

        # Handle quotes (only outside comments)
        if not in_line_comment and not in_block_comment:
            if c == "'" and not in_double_quote:
                # Check for escaped quote ('')
                if in_single_quote and next_c == "'":
                    current.append(c)
                    current.append(next_c)
                    i += 2
                    continue
                in_single_quote = not in_single_quote
            elif c == '"' and not in_single_quote:
                in_double_quote = not in_double_quote

        # Handle statement terminator
        if c == ';' and not in_single_quote and not in_double_quote and not in_line_comment and not in_block_comment:
            stmt = ''.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue

        current.append(c)
        i += 1

    # Handle final statement without trailing semicolon
    stmt = ''.join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements


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

    def execute_script(self, script: str, use_transaction: bool = True) -> None:
        """
        Execute a SQL script (multiple statements) safely.

        By default, executes statements within an explicit transaction to ensure
        atomicity. If any statement fails, all changes are rolled back.

        Args:
            script: SQL script string (semicolon-separated statements)
            use_transaction: If True (default), wrap in BEGIN/COMMIT with rollback
                           on failure. If False, use Python's executescript()
                           which issues implicit COMMITs (unsafe for data ops).

        Note:
            DDL statements (CREATE, ALTER, DROP) may not be fully rollback-safe
            in SQLite. For schema migrations, consider use_transaction=False
            with idempotent statements (IF NOT EXISTS, IF EXISTS).
        """
        with self.get_connection() as conn:
            if use_transaction:
                # Safe mode: split and execute in explicit transaction
                # Uses smart parser that handles embedded semicolons in strings/comments
                statements = _split_sql_statements(script)
                try:
                    conn.execute("BEGIN")
                    for stmt in statements:
                        conn.execute(stmt)
                    conn.execute("COMMIT")
                except Exception as e:
                    conn.execute("ROLLBACK")
                    logger.error(f"Script execution failed, rolled back: {e}")
                    raise
            else:
                # Unsafe mode: use executescript (implicit COMMITs)
                # WARNING: executescript() issues implicit COMMIT before script
                conn.executescript(script)
                conn.commit()

    def exists(self) -> bool:
        """
        Check if database file exists.

        Returns:
            True if database file exists
        """
        return self.db_path.exists()
