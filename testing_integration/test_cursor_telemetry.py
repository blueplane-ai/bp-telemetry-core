#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Real Integration Tests for Cursor Telemetry

Invokes the Cursor Agent CLI using the orchestration framework's CLI profile
and verifies telemetry events are captured in the database.

EXPECTED TO FAIL: cursor-agent CLI vs Cursor IDE Storage
=========================================================
This test is expected to fail because cursor-agent CLI and Cursor IDE
use different storage locations:

- Cursor IDE writes to:
    ~/Library/Application Support/Cursor/User/.../state.vscdb
    (This is what our database monitor watches - WORKS)

- cursor-agent CLI writes to:
    ~/.cursor/chats/{hash}/{uuid}/store.db
    (This is NOT monitored - test will fail)

To make this test pass, we would need to add a monitor for:
    ~/.cursor/chats/*/store.db

The Cursor IDE telemetry capture works correctly. Only the CLI is not captured.

Usage:
    python testing_integration/test_cursor_telemetry.py
"""

import sys
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from testing_integration.test_harness_utils import BaseTelemetryTest


@pytest.mark.xfail(reason="cursor-agent CLI uses different storage than Cursor IDE - see docstring")
class CursorTelemetryTest(BaseTelemetryTest):
    """Test harness for Cursor telemetry integration tests."""

    CLI_NAME = "cursor"  # Key in orchestration CLI_PROFILES
    TABLE = "cursor_raw_traces"
    SUITE_NAME = "cursor_telemetry_integration"
    FILE_PREFIX = "cursor_integration"


if __name__ == "__main__":
    sys.exit(CursorTelemetryTest().run_all_tests())
