# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Shared metrics state backed by Redis.

Solves the critical state management issue where multiple workers
maintain separate in-memory state, leading to inaccurate metrics.

Uses Redis data structures for shared state:
- Sorted Sets for sliding windows (latency, acceptance)
- Hashes for counters (tool counts, session tracking)
- Strings for simple values
"""

import logging
import time
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class SharedMetricsState:
    """
    Redis-backed shared state for metrics calculation across workers.

    All workers share the same state via Redis, ensuring accurate metrics
    regardless of which worker processes which events.
    """

    def __init__(self, redis_client):
        """
        Initialize shared metrics state.

        Args:
            redis_client: Redis client instance (can be sync or async)
        """
        self.redis = redis_client
        self.key_prefix = "metrics:state:"

        # Key names
        self.latency_window_key = f"{self.key_prefix}latency_window"
        self.acceptance_window_key = f"{self.key_prefix}acceptance_window"
        self.tool_counts_key = f"{self.key_prefix}tool_counts"
        self.tool_success_key = f"{self.key_prefix}tool_success"
        self.tool_failures_key = f"{self.key_prefix}tool_failures"
        self.session_starts_key = f"{self.key_prefix}session_starts"
        self.session_tools_key = f"{self.key_prefix}session_tools"
        self.session_prompts_key = f"{self.key_prefix}session_prompts"
        self.events_per_second_key = f"{self.key_prefix}events_per_second"

        # Window limits
        self.latency_window_size = 100
        self.acceptance_window_size = 100
        self.eps_window_size = 60  # seconds

    def add_latency(self, duration_ms: float, tool_name: str) -> None:
        """
        Add a latency measurement to the sliding window.

        Args:
            duration_ms: Latency in milliseconds
            tool_name: Name of the tool
        """
        try:
            timestamp = time.time()
            score = timestamp

            # Add to sorted set (score = timestamp, value = duration_ms)
            self.redis.zadd(self.latency_window_key, {str(duration_ms): score})

            # Trim to keep only last N entries
            count = self.redis.zcard(self.latency_window_key)
            if count > self.latency_window_size:
                # Remove oldest entries
                remove_count = count - self.latency_window_size
                self.redis.zpopmin(self.latency_window_key, remove_count)

            # Set expiry on the key (1 hour)
            self.redis.expire(self.latency_window_key, 3600)

        except Exception as e:
            logger.warning(f"Failed to add latency to shared state: {e}")

    def get_latency_percentiles(self) -> Dict[str, float]:
        """
        Calculate latency percentiles from sliding window.

        Returns:
            Dictionary with p50, p95, p99, avg
        """
        try:
            # Get all values from sorted set
            values = self.redis.zrange(self.latency_window_key, 0, -1)

            if not values:
                return {'p50': 0.0, 'p95': 0.0, 'p99': 0.0, 'avg': 0.0}

            # Convert to floats and sort
            latencies = sorted([float(v.decode('utf-8') if isinstance(v, bytes) else v) for v in values])
            count = len(latencies)

            if count == 0:
                return {'p50': 0.0, 'p95': 0.0, 'p99': 0.0, 'avg': 0.0}

            # Calculate percentiles
            p50_idx = int(count * 0.50)
            p95_idx = int(count * 0.95)
            p99_idx = int(count * 0.99)

            return {
                'p50': latencies[min(p50_idx, count - 1)],
                'p95': latencies[min(p95_idx, count - 1)],
                'p99': latencies[min(p99_idx, count - 1)],
                'avg': sum(latencies) / count
            }

        except Exception as e:
            logger.error(f"Failed to calculate latency percentiles: {e}")
            return {'p50': 0.0, 'p95': 0.0, 'p99': 0.0, 'avg': 0.0}

    def add_acceptance(self, accepted: bool) -> None:
        """
        Add an acceptance decision to the sliding window.

        Args:
            accepted: Whether the change was accepted
        """
        try:
            timestamp = time.time()
            value = 1 if accepted else 0

            # Add to sorted set
            self.redis.zadd(self.acceptance_window_key, {str(value): timestamp})

            # Trim to keep only last N entries
            count = self.redis.zcard(self.acceptance_window_key)
            if count > self.acceptance_window_size:
                remove_count = count - self.acceptance_window_size
                self.redis.zpopmin(self.acceptance_window_key, remove_count)

            # Set expiry
            self.redis.expire(self.acceptance_window_key, 3600)

        except Exception as e:
            logger.warning(f"Failed to add acceptance to shared state: {e}")

    def get_acceptance_rate(self) -> float:
        """
        Calculate acceptance rate from sliding window.

        Returns:
            Acceptance rate as percentage (0-100)
        """
        try:
            values = self.redis.zrange(self.acceptance_window_key, 0, -1)

            if not values:
                return 0.0

            # Convert to ints and calculate rate
            decisions = [int(float(v.decode('utf-8') if isinstance(v, bytes) else v)) for v in values]
            if not decisions:
                return 0.0

            rate = sum(decisions) / len(decisions)
            return rate * 100  # Convert to percentage

        except Exception as e:
            logger.error(f"Failed to calculate acceptance rate: {e}")
            return 0.0

    def increment_tool_count(self, tool_name: str, success: bool) -> None:
        """
        Increment tool usage counters.

        Args:
            tool_name: Name of the tool
            success: Whether the tool execution succeeded
        """
        try:
            # Increment total count
            self.redis.hincrby(self.tool_counts_key, tool_name, 1)

            # Increment success or failure
            if success:
                self.redis.hincrby(self.tool_success_key, tool_name, 1)
            else:
                self.redis.hincrby(self.tool_failures_key, tool_name, 1)

            # Set expiry
            self.redis.expire(self.tool_counts_key, 86400)  # 1 day
            self.redis.expire(self.tool_success_key, 86400)
            self.redis.expire(self.tool_failures_key, 86400)

        except Exception as e:
            logger.warning(f"Failed to increment tool count: {e}")

    def get_tool_success_rate(self, tool_name: Optional[str] = None) -> float:
        """
        Get tool success rate.

        Args:
            tool_name: Specific tool name, or None for overall rate

        Returns:
            Success rate as percentage (0-100)
        """
        try:
            if tool_name:
                success = int(self.redis.hget(self.tool_success_key, tool_name) or 0)
                failures = int(self.redis.hget(self.tool_failures_key, tool_name) or 0)
            else:
                # Overall rate
                success_dict = self.redis.hgetall(self.tool_success_key)
                failures_dict = self.redis.hgetall(self.tool_failures_key)

                success = sum(int(v) for v in success_dict.values())
                failures = sum(int(v) for v in failures_dict.values())

            total = success + failures
            if total == 0:
                return 0.0

            return (success / total) * 100

        except Exception as e:
            logger.error(f"Failed to get tool success rate: {e}")
            return 0.0

    def increment_session_tool_count(self, session_id: str) -> None:
        """
        Increment tool count for a session.

        Args:
            session_id: Session ID
        """
        try:
            self.redis.hincrby(self.session_tools_key, session_id, 1)
            self.redis.expire(self.session_tools_key, 86400)
        except Exception as e:
            logger.warning(f"Failed to increment session tool count: {e}")

    def increment_session_prompt_count(self, session_id: str) -> None:
        """
        Increment prompt count for a session.

        Args:
            session_id: Session ID
        """
        try:
            self.redis.hincrby(self.session_prompts_key, session_id, 1)
            self.redis.expire(self.session_prompts_key, 86400)
        except Exception as e:
            logger.warning(f"Failed to increment session prompt count: {e}")

    def set_session_start(self, session_id: str, timestamp: str) -> None:
        """
        Record session start time.

        Args:
            session_id: Session ID
            timestamp: ISO timestamp
        """
        try:
            self.redis.hset(self.session_starts_key, session_id, timestamp)
            self.redis.expire(self.session_starts_key, 86400)
        except Exception as e:
            logger.warning(f"Failed to set session start: {e}")

    def get_session_start(self, session_id: str) -> Optional[str]:
        """
        Get session start time.

        Args:
            session_id: Session ID

        Returns:
            ISO timestamp or None
        """
        try:
            value = self.redis.hget(self.session_starts_key, session_id)
            if value:
                return value.decode('utf-8') if isinstance(value, bytes) else value
            return None
        except Exception as e:
            logger.error(f"Failed to get session start: {e}")
            return None

    def get_session_tool_count(self, session_id: str) -> int:
        """
        Get tool count for a session.

        Args:
            session_id: Session ID

        Returns:
            Tool count
        """
        try:
            value = self.redis.hget(self.session_tools_key, session_id)
            return int(value) if value else 0
        except Exception as e:
            logger.error(f"Failed to get session tool count: {e}")
            return 0

    def get_session_prompt_count(self, session_id: str) -> int:
        """
        Get prompt count for a session.

        Args:
            session_id: Session ID

        Returns:
            Prompt count
        """
        try:
            value = self.redis.hget(self.session_prompts_key, session_id)
            return int(value) if value else 0
        except Exception as e:
            logger.error(f"Failed to get session prompt count: {e}")
            return 0

    def clear_session_data(self, session_id: str) -> None:
        """
        Clear all data for a session (called at session end).

        Args:
            session_id: Session ID
        """
        try:
            self.redis.hdel(self.session_starts_key, session_id)
            self.redis.hdel(self.session_tools_key, session_id)
            self.redis.hdel(self.session_prompts_key, session_id)
        except Exception as e:
            logger.warning(f"Failed to clear session data: {e}")

    def record_event_timestamp(self) -> None:
        """Record an event timestamp for EPS calculation."""
        try:
            current_time = time.time()
            # Add to sorted set with timestamp as both score and value
            self.redis.zadd(self.events_per_second_key, {str(current_time): current_time})

            # Remove events older than window
            cutoff = current_time - self.eps_window_size
            self.redis.zremrangebyscore(self.events_per_second_key, '-inf', cutoff)

            # Set expiry
            self.redis.expire(self.events_per_second_key, 300)  # 5 minutes

        except Exception as e:
            logger.warning(f"Failed to record event timestamp: {e}")

    def get_events_per_second(self) -> float:
        """
        Calculate events per second over the window.

        Returns:
            Events per second
        """
        try:
            current_time = time.time()
            cutoff = current_time - self.eps_window_size

            # Get count of events in window
            count = self.redis.zcount(self.events_per_second_key, cutoff, current_time)

            if count < 2:
                return 0.0

            # Get timestamps of first and last event
            first = self.redis.zrange(self.events_per_second_key, 0, 0, withscores=True)
            last = self.redis.zrange(self.events_per_second_key, -1, -1, withscores=True)

            if not first or not last:
                return 0.0

            first_time = first[0][1]
            last_time = last[0][1]

            time_span = last_time - first_time
            if time_span <= 0:
                return 0.0

            return count / time_span

        except Exception as e:
            logger.error(f"Failed to calculate EPS: {e}")
            return 0.0

    def get_tool_frequency(self, tool_name: str) -> float:
        """
        Get frequency of a specific tool.

        Args:
            tool_name: Tool name

        Returns:
            Frequency as percentage (0-100)
        """
        try:
            tool_count = int(self.redis.hget(self.tool_counts_key, tool_name) or 0)
            total_dict = self.redis.hgetall(self.tool_counts_key)
            total = sum(int(v) for v in total_dict.values())

            if total == 0:
                return 0.0

            return (tool_count / total) * 100

        except Exception as e:
            logger.error(f"Failed to get tool frequency: {e}")
            return 0.0

    def clear_all(self) -> None:
        """Clear all shared state (for testing)."""
        try:
            keys = [
                self.latency_window_key,
                self.acceptance_window_key,
                self.tool_counts_key,
                self.tool_success_key,
                self.tool_failures_key,
                self.session_starts_key,
                self.session_tools_key,
                self.session_prompts_key,
                self.events_per_second_key,
            ]
            for key in keys:
                self.redis.delete(key)
        except Exception as e:
            logger.error(f"Failed to clear shared state: {e}")
