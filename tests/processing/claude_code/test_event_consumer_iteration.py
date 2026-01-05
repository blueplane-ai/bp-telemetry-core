#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Regression test for iteration variable bug in Claude event consumer.

BUG DESCRIPTION:
The consumer loop referenced `iteration` variable without initializing it,
causing a NameError when pending_count >= 200 and the code path tried to
log every 10th iteration: `if iteration % 10 == 0`.

This test verifies the bug is fixed through behavioral testing, not source inspection.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


class TestIterationVariableFix:
    """Regression tests for iteration variable initialization.

    These tests verify behavior, not source code structure.
    """

    @patch('src.processing.claude_code.event_consumer.logger')
    def test_consumer_loop_no_nameerror(self, mock_logger):
        """Consumer loop should not raise NameError for iteration variable.

        This is the critical regression test - before the fix, the consumer
        would crash with NameError when pending_count >= 200.
        """
        from src.processing.claude_code.event_consumer import ClaudeEventConsumer

        # Create mock dependencies
        mock_redis = MagicMock()
        mock_redis.xinfo_groups.return_value = []
        mock_redis.xgroup_create = MagicMock()
        mock_redis.xpending.return_value = {'pending': 0}
        mock_redis.xreadgroup.return_value = []

        mock_writer = MagicMock()
        mock_cdc = MagicMock()

        # Create consumer
        consumer = ClaudeEventConsumer(
            redis_client=mock_redis,
            claude_writer=mock_writer,
            cdc_publisher=mock_cdc,
            stream_name="test:stream",
            consumer_group="test_group",
            consumer_name="test_consumer",
        )

        # Track iterations to stop after a few loops
        iteration_count = [0]

        def stop_after_iterations():
            iteration_count[0] += 1
            if iteration_count[0] >= 5:
                consumer.running = False
            return 250  # High pending count to trigger iteration % 10 path

        # Simulate high pending count to trigger the iteration % 10 path
        # This would have caused NameError before the fix
        consumer._get_pending_count = stop_after_iterations
        consumer._process_pending_messages = MagicMock()
        consumer._should_throttle_reads = MagicMock(return_value=False)
        consumer._read_messages = MagicMock(return_value=[])

        # This should NOT raise NameError - the specific bug we're testing
        try:
            consumer.run()
        except NameError as e:
            pytest.fail(f"NameError raised - iteration variable not initialized: {e}")
        # Let other exceptions propagate - they indicate different bugs

    @patch('src.processing.claude_code.event_consumer.logger')
    def test_consumer_loop_runs_multiple_iterations(self, mock_logger):
        """Consumer should successfully run multiple loop iterations."""
        from src.processing.claude_code.event_consumer import ClaudeEventConsumer

        mock_redis = MagicMock()
        mock_redis.xinfo_groups.return_value = []
        mock_redis.xgroup_create = MagicMock()
        mock_redis.xpending.return_value = {'pending': 0}
        mock_redis.xreadgroup.return_value = []

        mock_writer = MagicMock()
        mock_cdc = MagicMock()

        consumer = ClaudeEventConsumer(
            redis_client=mock_redis,
            claude_writer=mock_writer,
            cdc_publisher=mock_cdc,
            stream_name="test:stream",
            consumer_group="test_group",
            consumer_name="test_consumer",
        )

        iteration_count = [0]

        def count_and_stop():
            iteration_count[0] += 1
            if iteration_count[0] >= 15:  # Run 15 iterations
                consumer.running = False
            return 250

        consumer._get_pending_count = count_and_stop
        consumer._process_pending_messages = MagicMock()
        consumer._should_throttle_reads = MagicMock(return_value=False)
        consumer._read_messages = MagicMock(return_value=[])

        try:
            consumer.run()
        except NameError as e:
            pytest.fail(f"NameError raised during iteration: {e}")

        # Verify we actually ran the expected number of iterations
        assert iteration_count[0] >= 15, \
            f"Expected at least 15 iterations, got {iteration_count[0]}"

    @patch('src.processing.claude_code.event_consumer.logger')
    def test_high_pending_count_triggers_processing(self, mock_logger):
        """High pending count (>=200) should trigger pending message processing."""
        from src.processing.claude_code.event_consumer import ClaudeEventConsumer

        mock_redis = MagicMock()
        mock_redis.xinfo_groups.return_value = []
        mock_redis.xgroup_create = MagicMock()
        mock_redis.xpending.return_value = {'pending': 0}
        mock_redis.xreadgroup.return_value = []

        mock_writer = MagicMock()
        mock_cdc = MagicMock()

        consumer = ClaudeEventConsumer(
            redis_client=mock_redis,
            claude_writer=mock_writer,
            cdc_publisher=mock_cdc,
            stream_name="test:stream",
            consumer_group="test_group",
            consumer_name="test_consumer",
        )

        iteration_count = [0]

        def return_high_pending():
            iteration_count[0] += 1
            if iteration_count[0] >= 3:
                consumer.running = False
            return 250  # >= 200 threshold

        consumer._get_pending_count = return_high_pending
        process_pending_mock = MagicMock()
        consumer._process_pending_messages = process_pending_mock
        consumer._should_throttle_reads = MagicMock(return_value=False)
        consumer._read_messages = MagicMock(return_value=[])

        try:
            consumer.run()
        except NameError as e:
            pytest.fail(f"NameError raised - iteration bug not fixed: {e}")

        # Verify pending message processing was called (indicates high pending path works)
        assert process_pending_mock.called, \
            "High pending count should trigger _process_pending_messages"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
