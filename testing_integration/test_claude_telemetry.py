#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Real Integration Tests for Claude Code Telemetry

Invokes Claude Code using the orchestration framework's CLI profile
and verifies telemetry events are captured in the database.

Usage:
    python testing_integration/test_claude_telemetry.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from testing_integration.test_harness_utils import BaseTelemetryTest


class ClaudeTelemetryTest(BaseTelemetryTest):
    """Test harness for Claude Code telemetry integration tests."""

    CLI_NAME = "claude"  # Key in orchestration CLI_PROFILES
    TABLE = "claude_raw_traces"
    SUITE_NAME = "claude_telemetry_integration"
    FILE_PREFIX = "claude_integration"


if __name__ == "__main__":
    sys.exit(ClaudeTelemetryTest().run_all_tests())
