# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Redis storage for real-time metrics.

IMPLEMENTATION NOTE: This currently uses basic Redis data structures (Hashes + Sorted Sets)
for compatibility with standard Redis installations. For production at scale, consider
using Redis TimeSeries module for:
- Built-in downsampling and aggregations
- Better compression
- Optimized queries

To enable Redis TimeSeries:
  docker run -p 6379:6379 redis/redis-stack-server:latest

The API is designed to support easy migration to TimeSeries without code changes.

Provides sub-millisecond metric recording and retrieval with automatic expiry.
"""

import logging
import time
from typing import Dict, Any, List, Tuple, Optional
import redis

logger = logging.getLogger(__name__)


class RedisMetricsStorage:
    """
    Redis storage for real-time metrics.

    Uses:
    - Redis Hashes for latest metric snapshots (fast read)
    - Sorted Sets for time-series data (fallback if TimeSeries unavailable)
    - Automatic expiry policies
    """

    def __init__(self, redis_client: redis.Redis):
        """
        Initialize Redis metrics storage.

        Args:
            redis_client: Redis client instance
        """
        self.redis_client = redis_client
        self._initialized = False

    def initialize(self) -> None:
        """
        Initialize metrics storage.

        Creates necessary data structures and retention policies.
        """
        if self._initialized:
            return

        logger.info("Initializing Redis metrics storage")

        # Note: RedisTimeSeries is an optional module, not available in all Redis installations
        # We'll use basic Redis data structures (hashes and sorted sets) for now
        # This is sufficient for MVP and works with standard Redis

        self._initialized = True
        logger.info("Redis metrics storage initialized")

    def record_metric(
        self,
        category: str,
        name: str,
        value: float,
        timestamp: Optional[float] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Record a single metric value.

        Args:
            category: Metric category (e.g., 'realtime', 'session', 'tools')
            name: Metric name
            value: Metric value
            timestamp: Unix timestamp (uses current time if not provided)
            labels: Additional labels for the metric
        """
        if timestamp is None:
            timestamp = time.time()

        try:
            # Build key: metric:{category}:{name}
            key = f"metric:{category}:{name}"

            # Store latest value in hash for fast access
            latest_key = f"metric:latest:{category}"
            self.redis_client.hset(latest_key, name, str(value))
            self.redis_client.expire(latest_key, 86400)  # 1 day expiry

            # Store time-series data in sorted set (score = timestamp)
            ts_key = f"{key}:ts"
            self.redis_client.zadd(ts_key, {str(value): timestamp})

            # Set retention based on category
            retention_seconds = self._get_retention_seconds(category)
            self.redis_client.expire(ts_key, retention_seconds)

            # Trim old data from sorted set
            cutoff = timestamp - retention_seconds
            self.redis_client.zremrangebyscore(ts_key, '-inf', cutoff)

            logger.debug(f"Recorded metric: {category}/{name} = {value}")

        except Exception as e:
            logger.warning(f"Failed to record metric {category}/{name}: {e}")

    def get_latest_metrics(self, category: Optional[str] = None) -> Dict[str, float]:
        """
        Get latest values for all metrics in a category.

        Args:
            category: Metric category (returns all if None)

        Returns:
            Dictionary of metric_name -> latest_value
        """
        try:
            if category:
                # Get all metrics from specific category
                key = f"metric:latest:{category}"
                data = self.redis_client.hgetall(key)
                return {
                    k.decode('utf-8'): float(v.decode('utf-8'))
                    for k, v in data.items()
                }
            else:
                # Get all categories
                pattern = "metric:latest:*"
                result = {}
                for key in self.redis_client.scan_iter(match=pattern):
                    category_name = key.decode('utf-8').split(':')[-1]
                    data = self.redis_client.hgetall(key)
                    for metric_name, value in data.items():
                        full_name = f"{category_name}:{metric_name.decode('utf-8')}"
                        result[full_name] = float(value.decode('utf-8'))
                return result

        except Exception as e:
            logger.error(f"Failed to get latest metrics: {e}")
            return {}

    def get_metric_range(
        self,
        category: str,
        name: str,
        start_time: float,
        end_time: float,
        aggregation: Optional[str] = None
    ) -> List[Tuple[float, float]]:
        """
        Get metric values for a time range.

        Args:
            category: Metric category
            name: Metric name
            start_time: Start timestamp (Unix)
            end_time: End timestamp (Unix)
            aggregation: Aggregation type (not used in basic implementation)

        Returns:
            List of (timestamp, value) tuples
        """
        try:
            key = f"metric:{category}:{name}:ts"

            # Get all values in time range from sorted set
            data = self.redis_client.zrangebyscore(
                key,
                start_time,
                end_time,
                withscores=True
            )

            # Convert to list of (timestamp, value) tuples
            result = []
            for value_bytes, timestamp in data:
                try:
                    value = float(value_bytes.decode('utf-8'))
                    result.append((timestamp, value))
                except (ValueError, AttributeError):
                    continue

            return sorted(result, key=lambda x: x[0])

        except Exception as e:
            logger.error(f"Failed to get metric range for {category}/{name}: {e}")
            return []

    def increment_counter(self, category: str, name: str, amount: float = 1.0) -> None:
        """
        Increment a counter metric.

        Args:
            category: Metric category
            name: Counter name
            amount: Amount to increment by
        """
        try:
            key = f"metric:latest:{category}"
            self.redis_client.hincrbyfloat(key, name, amount)
            self.redis_client.expire(key, self._get_retention_seconds(category))

            # Also record as time-series
            self.record_metric(category, name, amount)

        except Exception as e:
            logger.warning(f"Failed to increment counter {category}/{name}: {e}")

    def record_gauge(self, category: str, name: str, value: float) -> None:
        """
        Record a gauge metric (overwrites previous value).

        Args:
            category: Metric category
            name: Gauge name
            value: New value
        """
        self.record_metric(category, name, value)

    def get_metric_stats(self, category: str, name: str, window_seconds: int = 3600) -> Dict[str, float]:
        """
        Get statistics for a metric over a time window.

        Args:
            category: Metric category
            name: Metric name
            window_seconds: Time window in seconds

        Returns:
            Dictionary with min, max, avg, count
        """
        try:
            end_time = time.time()
            start_time = end_time - window_seconds

            values = self.get_metric_range(category, name, start_time, end_time)

            if not values:
                return {'min': 0.0, 'max': 0.0, 'avg': 0.0, 'count': 0}

            value_list = [v for _, v in values]
            return {
                'min': min(value_list),
                'max': max(value_list),
                'avg': sum(value_list) / len(value_list),
                'count': len(value_list)
            }

        except Exception as e:
            logger.error(f"Failed to get metric stats for {category}/{name}: {e}")
            return {'min': 0.0, 'max': 0.0, 'avg': 0.0, 'count': 0}

    def _get_retention_seconds(self, category: str) -> int:
        """
        Get retention period in seconds for a category.

        Args:
            category: Metric category

        Returns:
            Retention period in seconds
        """
        retention_map = {
            'realtime': 3600,        # 1 hour
            'session': 604800,       # 7 days
            'tools': 86400,          # 1 day
            'daily': 2592000,        # 30 days
            'weekly': 7776000,       # 90 days
        }
        return retention_map.get(category, 86400)  # Default: 1 day

    def clear_metrics(self, category: Optional[str] = None) -> None:
        """
        Clear all metrics or metrics in a category.

        Args:
            category: Category to clear (clears all if None)
        """
        try:
            if category:
                pattern = f"metric:*:{category}:*"
            else:
                pattern = "metric:*"

            for key in self.redis_client.scan_iter(match=pattern):
                self.redis_client.delete(key)

            logger.info(f"Cleared metrics: {pattern}")

        except Exception as e:
            logger.error(f"Failed to clear metrics: {e}")
