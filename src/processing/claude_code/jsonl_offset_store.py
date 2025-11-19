# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""SQLite-backed persistence for Claude JSONL file offsets."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..database.sqlite_client import SQLiteClient


class JSONLOffsetStore:
    """Read/write JSONL tail offsets via SQLite."""

    def __init__(self, sqlite_client: SQLiteClient):
        self.client = sqlite_client

    def load_state(self, file_path: Path) -> Optional[dict]:
        """
        Load persisted state for a JSONL file.

        Args:
            file_path: Path to the JSONL file

        Returns:
            Dict with persisted fields or None if not tracked
        """
        with self.client.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT session_id, agent_id, line_offset, last_size, last_mtime, last_read_time
                FROM claude_jsonl_offsets
                WHERE file_path = ?
                """,
                (str(file_path),),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def upsert_state(
        self,
        *,
        file_path: Path,
        session_id: str,
        agent_id: Optional[str],
        line_offset: int,
        last_size: int,
        last_mtime: float,
        last_read_time: float,
    ) -> None:
        """Insert or update the persisted offset for a JSONL file."""
        with self.client.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO claude_jsonl_offsets (
                    file_path, session_id, agent_id,
                    line_offset, last_size, last_mtime, last_read_time, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(file_path) DO UPDATE SET
                    session_id = excluded.session_id,
                    agent_id = excluded.agent_id,
                    line_offset = excluded.line_offset,
                    last_size = excluded.last_size,
                    last_mtime = excluded.last_mtime,
                    last_read_time = excluded.last_read_time,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    str(file_path),
                    session_id,
                    agent_id,
                    line_offset,
                    last_size,
                    last_mtime,
                    last_read_time,
                ),
            )
            conn.commit()

    def delete_for_session(self, session_id: str) -> None:
        """Remove all offsets associated with a session."""
        with self.client.get_connection() as conn:
            conn.execute(
                "DELETE FROM claude_jsonl_offsets WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()

    def delete(self, file_path: Path) -> None:
        """Remove the offset row for a specific file."""
        with self.client.get_connection() as conn:
            conn.execute(
                "DELETE FROM claude_jsonl_offsets WHERE file_path = ?",
                (str(file_path),),
            )
            conn.commit()


