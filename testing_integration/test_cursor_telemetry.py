#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Real Integration Tests for Cursor Telemetry

These tests verify that Cursor database monitoring is working correctly
by checking for captured events in the telemetry database.

Unlike Claude tests, Cursor tests are passive - they check if telemetry
is being captured from Cursor's SQLite databases rather than invoking
Cursor directly.

Usage:
    python testing_integration/test_cursor_telemetry.py
"""

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add project root to path BEFORE local imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from testing_integration.test_harness_utils import save_test_results


class CursorTelemetryTest:
    """Test harness for Cursor telemetry integration tests."""

    def __init__(self):
        self.telemetry_db = Path.home() / ".blueplane" / "telemetry.db"
        self.cursor_db_locations = [
            Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb",
            Path.home() / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb",
        ]
        self.results = {"passed": [], "failed": [], "skipped": []}

    def record(self, name: str, passed: bool, message: str = "", skip: bool = False):
        """Record test result."""
        if skip:
            self.results["skipped"].append((name, message))
            print(f"  ⏭️  {name}: SKIPPED - {message}")
        elif passed:
            self.results["passed"].append((name, message))
            print(f"  ✅ {name}: {message}")
        else:
            self.results["failed"].append((name, message))
            print(f"  ❌ {name}: {message}")

    def find_cursor_db(self) -> Path | None:
        """Find Cursor's state database."""
        for path in self.cursor_db_locations:
            if path.exists():
                return path
        return None

    def get_cursor_event_count(self, hours: int = 24) -> int:
        """Get count of Cursor events in the last N hours."""
        if not self.telemetry_db.exists():
            return 0

        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        try:
            with sqlite3.connect(str(self.telemetry_db)) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*) FROM cursor_raw_traces
                    WHERE timestamp >= ?
                """, (since,))
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            print(f"  Warning: DB error - {e}")
            return 0

    def get_recent_cursor_events(self, limit: int = 5) -> list:
        """Get recent Cursor events."""
        if not self.telemetry_db.exists():
            return []

        try:
            with sqlite3.connect(str(self.telemetry_db)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT event_id, event_type, timestamp, storage_level, workspace_hash
                    FROM cursor_raw_traces
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"  Warning: DB error - {e}")
            return []


def test_cursor_installed(harness: CursorTelemetryTest):
    """Test that Cursor is installed."""
    print("\n[TEST] Cursor installation...")

    cursor_db = harness.find_cursor_db()
    if cursor_db:
        harness.record("cursor_installed", True, f"Found Cursor DB at {cursor_db}")
        return True
    else:
        harness.record(
            "cursor_installed",
            False,
            "Cursor not found - install from https://cursor.sh",
            skip=True
        )
        return False


def test_telemetry_db_has_cursor_table(harness: CursorTelemetryTest):
    """Test that telemetry database has cursor_raw_traces table."""
    print("\n[TEST] Cursor telemetry table...")

    if not harness.telemetry_db.exists():
        harness.record("cursor_table", False, "Telemetry DB not found", skip=True)
        return False

    try:
        conn = sqlite3.connect(str(harness.telemetry_db))
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='cursor_raw_traces'
        """)
        exists = cursor.fetchone() is not None
        conn.close()

        if exists:
            harness.record("cursor_table", True, "cursor_raw_traces table exists")
        else:
            harness.record("cursor_table", False, "cursor_raw_traces table not found")
        return exists
    except sqlite3.Error as e:
        harness.record("cursor_table", False, f"DB error: {e}")
        return False


def test_cursor_events_captured(harness: CursorTelemetryTest):
    """Test that Cursor events are being captured."""
    print("\n[TEST] Cursor event capture (last 24 hours)...")

    count = harness.get_cursor_event_count(hours=24)
    if count > 0:
        harness.record("cursor_events", True, f"Found {count} events in last 24 hours")
        return True
    else:
        harness.record(
            "cursor_events",
            False,
            "No Cursor events found - use Cursor to generate events, or check telemetry server"
        )
        return False


def test_cursor_event_structure(harness: CursorTelemetryTest):
    """Test that Cursor events have proper structure."""
    print("\n[TEST] Cursor event structure...")

    events = harness.get_recent_cursor_events(limit=3)
    if not events:
        harness.record("cursor_structure", False, "No events to validate", skip=True)
        return False

    event = events[0]
    required_fields = ["event_id", "event_type", "timestamp"]
    missing = [f for f in required_fields if f not in event or event[f] is None]

    if missing:
        harness.record("cursor_structure", False, f"Missing fields: {missing}")
        return False

    harness.record("cursor_structure", True, f"Event fields: {list(event.keys())}")

    # Show sample event
    print(f"  Sample event: {event}")
    return True


def run_all_tests():
    """Run all Cursor integration tests."""
    print("=" * 70)
    print("Cursor Telemetry - Real Integration Tests")
    print("=" * 70)
    print(f"\nTest started at: {datetime.now(timezone.utc).isoformat()}")

    harness = CursorTelemetryTest()

    # Run tests
    test_cursor_installed(harness)
    test_telemetry_db_has_cursor_table(harness)
    test_cursor_events_captured(harness)
    test_cursor_event_structure(harness)

    # Summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"  Passed:  {len(harness.results['passed'])}")
    print(f"  Failed:  {len(harness.results['failed'])}")
    print(f"  Skipped: {len(harness.results['skipped'])}")

    if harness.results['failed']:
        print("\nFailed tests:")
        for name, msg in harness.results['failed']:
            print(f"  - {name}: {msg}")

    # Save results to file
    save_results(harness)

    return 1 if harness.results['failed'] else 0


def save_results(harness: CursorTelemetryTest):
    """Save test results to /tmp/bp-telemetry-core/bug_fix/."""
    save_test_results(
        harness.results,
        "cursor_telemetry_integration",
        "cursor_integration"
    )


if __name__ == "__main__":
    sys.exit(run_all_tests())
