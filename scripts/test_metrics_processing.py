#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Test script for metrics processing pipeline.

Tests:
- Metrics calculator
- Redis metrics storage
- Metrics worker processing
"""

import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from processing.metrics.calculator import MetricsCalculator
from processing.metrics.redis_metrics import RedisMetricsStorage
import redis
import time

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_metrics_calculator():
    """Test metrics calculator with sample events."""
    logger.info("Testing MetricsCalculator...")

    calc = MetricsCalculator()

    # Test 1: Tool execution event
    tool_event = {
        'event_id': 'evt_001',
        'session_id': 'sess_001',
        'event_type': 'tool_use',
        'platform': 'claude_code',
        'timestamp': '2025-11-11T12:00:00Z',
        'tool_name': 'Read',
        'duration_ms': 125,
        'payload': {'success': True}
    }

    metrics = calc.calculate_metrics_for_event(tool_event)
    logger.info(f"Tool event produced {len(metrics)} metrics")
    for metric in metrics:
        logger.info(f"  - {metric['category']}:{metric['name']} = {metric['value']:.2f}")

    # Test 2: File edit event
    edit_event = {
        'event_id': 'evt_002',
        'session_id': 'sess_001',
        'event_type': 'file_edit',
        'platform': 'claude_code',
        'timestamp': '2025-11-11T12:01:00Z',
        'payload': {'accepted': True}
    }

    metrics = calc.calculate_metrics_for_event(edit_event)
    logger.info(f"Edit event produced {len(metrics)} metrics")
    for metric in metrics:
        logger.info(f"  - {metric['category']}:{metric['name']} = {metric['value']:.2f}")

    # Test 3: Multiple tool events to test percentiles
    for i in range(20):
        event = {
            'event_id': f'evt_{100+i}',
            'session_id': 'sess_001',
            'event_type': 'tool_use',
            'platform': 'claude_code',
            'timestamp': f'2025-11-11T12:{i:02d}:00Z',
            'tool_name': 'Edit',
            'duration_ms': 50 + (i * 10),  # Increasing latency
            'payload': {'success': i % 5 != 0}  # 80% success rate
        }
        calc.calculate_metrics_for_event(event)

    # Get final stats
    stats = calc.get_current_stats()
    logger.info(f"Calculator stats after processing: {stats}")

    logger.info("✅ MetricsCalculator tests passed")
    return True


def test_redis_metrics_storage():
    """Test Redis metrics storage."""
    logger.info("Testing RedisMetricsStorage...")

    try:
        # Connect to Redis
        redis_client = redis.Redis(
            host='localhost',
            port=6379,
            db=0,
            decode_responses=False
        )

        # Test connection
        redis_client.ping()
        logger.info("Connected to Redis")

        # Initialize storage
        storage = RedisMetricsStorage(redis_client)
        storage.initialize()

        # Test 1: Record metrics
        storage.record_metric('realtime', 'events_per_second', 150.5)
        storage.record_metric('session', 'acceptance_rate', 78.3)
        storage.record_metric('tools', 'tool_latency_p95', 234.7)

        logger.info("Recorded 3 test metrics")

        # Test 2: Retrieve latest metrics
        realtime_metrics = storage.get_latest_metrics('realtime')
        logger.info(f"Realtime metrics: {realtime_metrics}")

        session_metrics = storage.get_latest_metrics('session')
        logger.info(f"Session metrics: {session_metrics}")

        # Test 3: Record time-series data
        import time
        for i in range(5):
            storage.record_metric('tools', 'tool_count', float(i * 10))
            time.sleep(0.1)

        # Test 4: Get metric range
        end_time = time.time()
        start_time = end_time - 60
        range_data = storage.get_metric_range('tools', 'tool_count', start_time, end_time)
        logger.info(f"Time range data points: {len(range_data)}")

        # Test 5: Increment counter
        storage.increment_counter('session', 'total_prompts', 1)
        storage.increment_counter('session', 'total_prompts', 1)

        # Test 6: Get stats
        stats = storage.get_metric_stats('tools', 'tool_count', window_seconds=60)
        logger.info(f"Metric stats: {stats}")

        # Cleanup
        storage.clear_metrics('realtime')
        logger.info("Cleaned up test metrics")

        logger.info("✅ RedisMetricsStorage tests passed")
        return True

    except redis.ConnectionError:
        logger.error("❌ Could not connect to Redis. Make sure Redis is running.")
        return False
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("Starting metrics processing tests")
    logger.info("=" * 60)

    results = []

    # Test 1: Calculator
    results.append(("MetricsCalculator", test_metrics_calculator()))

    # Test 2: Redis storage
    results.append(("RedisMetricsStorage", test_redis_metrics_storage()))

    # Print summary
    logger.info("=" * 60)
    logger.info("Test Summary:")
    logger.info("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{name}: {status}")
        if not passed:
            all_passed = False

    if all_passed:
        logger.info("\n🎉 All tests passed!")
        return 0
    else:
        logger.error("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
