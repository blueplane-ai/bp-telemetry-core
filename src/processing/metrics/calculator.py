# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Metrics calculator for deriving actionable metrics from telemetry events.

Implements all metric categories from layer2_metrics_derivation.md:
- Core performance metrics (latency, throughput)
- Acceptance and quality metrics
- Usage pattern metrics
- Interaction metrics
- Composite metrics (productivity score)
"""

import logging
import time
from typing import Dict, Any, List, Optional
from collections import defaultdict, deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MetricsCalculator:
    """
    Calculates metrics from telemetry events.

    Maintains sliding windows and running statistics for efficient calculation.
    """

    def __init__(self):
        """Initialize metrics calculator with sliding windows."""
        # Sliding windows for calculations
        self._latency_window = deque(maxlen=100)  # Last 100 tool executions
        self._acceptance_window = deque(maxlen=100)  # Last 100 changes
        self._tool_counts = defaultdict(int)
        self._tool_success = defaultdict(int)
        self._tool_failures = defaultdict(int)

        # Session-level tracking
        self._session_starts = {}
        self._session_tool_counts = defaultdict(int)
        self._session_prompt_counts = defaultdict(int)
        self._session_file_changes = defaultdict(set)

        # Time-based tracking
        self._events_per_second = deque(maxlen=60)  # Last 60 seconds
        self._last_event_time = time.time()

    def calculate_metrics_for_event(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate all applicable metrics for a single event.

        Args:
            event: Event dictionary from raw traces

        Returns:
            List of metric dictionaries to record
        """
        metrics = []
        event_type = event.get('event_type', '')
        session_id = event.get('session_id', '')

        try:
            # Core performance metrics
            if event_type in ('tool_use', 'mcp_execution'):
                metrics.extend(self._calculate_latency_metrics(event))
                metrics.extend(self._calculate_tool_usage_metrics(event))

            # Acceptance metrics
            elif event_type in ('file_edit', 'code_change'):
                metrics.extend(self._calculate_acceptance_metrics(event))

            # Interaction metrics
            elif event_type == 'user_prompt':
                metrics.extend(self._calculate_interaction_metrics(event))

            # Session metrics
            elif event_type == 'session_start':
                self._track_session_start(event)
            elif event_type == 'session_end':
                metrics.extend(self._calculate_session_metrics(event))

            # Throughput metrics (for all events)
            metrics.extend(self._calculate_throughput_metrics(event))

            # Update composite metrics periodically
            if len(self._latency_window) > 0 and len(self._latency_window) % 10 == 0:
                metrics.extend(self._calculate_composite_metrics(session_id))

        except Exception as e:
            logger.error(f"Error calculating metrics for event {event.get('event_id')}: {e}")

        return metrics

    def _calculate_latency_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate latency metrics from tool execution events.

        Metrics:
        - Tool execution latency (p50, p95, p99)
        - Response time
        """
        metrics = []
        duration_ms = event.get('duration_ms')

        if duration_ms is not None and duration_ms >= 0:
            # Add to sliding window
            self._latency_window.append(duration_ms)

            # Calculate percentiles
            if len(self._latency_window) >= 10:
                sorted_latencies = sorted(self._latency_window)
                p50_idx = int(len(sorted_latencies) * 0.50)
                p95_idx = int(len(sorted_latencies) * 0.95)
                p99_idx = int(len(sorted_latencies) * 0.99)

                metrics.append({
                    'category': 'tools',
                    'name': 'tool_latency_p50',
                    'value': sorted_latencies[p50_idx]
                })
                metrics.append({
                    'category': 'tools',
                    'name': 'tool_latency_p95',
                    'value': sorted_latencies[p95_idx]
                })
                metrics.append({
                    'category': 'tools',
                    'name': 'tool_latency_p99',
                    'value': sorted_latencies[p99_idx]
                })

            # Average latency
            avg_latency = sum(self._latency_window) / len(self._latency_window)
            metrics.append({
                'category': 'tools',
                'name': 'tool_latency_avg',
                'value': avg_latency
            })

        return metrics

    def _calculate_tool_usage_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate tool usage distribution and success rates.

        Metrics:
        - Tool frequency
        - Tool success rate
        - Tool diversity score
        """
        metrics = []
        tool_name = event.get('tool_name', 'unknown')
        success = event.get('payload', {}).get('success', True)

        # Update counts
        self._tool_counts[tool_name] += 1
        if success:
            self._tool_success[tool_name] += 1
        else:
            self._tool_failures[tool_name] += 1

        # Calculate success rate for this tool
        total_attempts = self._tool_success[tool_name] + self._tool_failures[tool_name]
        if total_attempts > 0:
            success_rate = self._tool_success[tool_name] / total_attempts
            metrics.append({
                'category': 'tools',
                'name': f'tool_success_rate_{tool_name.lower()}',
                'value': success_rate * 100  # Percentage
            })

        # Overall tool success rate
        total_success = sum(self._tool_success.values())
        total_failures = sum(self._tool_failures.values())
        if (total_success + total_failures) > 0:
            overall_success_rate = total_success / (total_success + total_failures)
            metrics.append({
                'category': 'tools',
                'name': 'tool_success_rate',
                'value': overall_success_rate * 100
            })

        # Tool frequency distribution
        total_tools = sum(self._tool_counts.values())
        if total_tools > 0:
            frequency = self._tool_counts[tool_name] / total_tools
            metrics.append({
                'category': 'tools',
                'name': f'tool_frequency_{tool_name.lower()}',
                'value': frequency * 100
            })

        return metrics

    def _calculate_acceptance_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate code acceptance metrics.

        Metrics:
        - Direct accept rate
        - Rejection rate
        - Partial accept rate
        """
        metrics = []
        payload = event.get('payload', {})

        # Track if code was accepted (heuristic: no immediate undo)
        # In real implementation, would need to correlate with subsequent events
        accepted = payload.get('accepted', True)

        self._acceptance_window.append(1 if accepted else 0)

        # Calculate acceptance rate from sliding window
        if len(self._acceptance_window) >= 10:
            acceptance_rate = sum(self._acceptance_window) / len(self._acceptance_window)
            metrics.append({
                'category': 'session',
                'name': 'acceptance_rate',
                'value': acceptance_rate * 100
            })

            rejection_rate = 1 - acceptance_rate
            metrics.append({
                'category': 'session',
                'name': 'rejection_rate',
                'value': rejection_rate * 100
            })

        return metrics

    def _calculate_interaction_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate user interaction metrics.

        Metrics:
        - Prompt frequency
        - Prompt length
        - Prompt gaps
        """
        metrics = []
        session_id = event.get('session_id', '')
        payload = event.get('payload', {})

        # Track prompts per session
        self._session_prompt_counts[session_id] += 1

        # Prompt length (if available)
        prompt_length = payload.get('prompt_length', 0)
        if prompt_length > 0:
            metrics.append({
                'category': 'session',
                'name': 'prompt_length_avg',
                'value': prompt_length
            })

        # Prompt frequency (prompts per session)
        metrics.append({
            'category': 'session',
            'name': 'prompts_per_session',
            'value': self._session_prompt_counts[session_id]
        })

        return metrics

    def _calculate_throughput_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate throughput metrics.

        Metrics:
        - Events per second
        - Tools per minute
        """
        metrics = []
        current_time = time.time()

        # Track events per second
        self._events_per_second.append(current_time)

        # Calculate EPS for last 60 seconds
        recent_events = [t for t in self._events_per_second if current_time - t <= 60]
        if len(recent_events) >= 2:
            time_span = recent_events[-1] - recent_events[0]
            if time_span > 0:
                eps = len(recent_events) / time_span
                metrics.append({
                    'category': 'realtime',
                    'name': 'events_per_second',
                    'value': eps
                })

        self._last_event_time = current_time

        return metrics

    def _calculate_session_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate session-level metrics when session ends.

        Metrics:
        - Session duration
        - Tools per session
        - Files per session
        """
        metrics = []
        session_id = event.get('session_id', '')

        # Session duration
        if session_id in self._session_starts:
            start_time = self._session_starts[session_id]
            end_time = event.get('timestamp', '')

            try:
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                duration_seconds = (end_dt - start_dt).total_seconds()

                metrics.append({
                    'category': 'session',
                    'name': 'session_duration',
                    'value': duration_seconds
                })

                # Tools per minute
                tool_count = self._session_tool_counts.get(session_id, 0)
                if duration_seconds > 0:
                    tools_per_minute = (tool_count / duration_seconds) * 60
                    metrics.append({
                        'category': 'session',
                        'name': 'tools_per_minute',
                        'value': tools_per_minute
                    })

                # Files per session
                file_count = len(self._session_file_changes.get(session_id, set()))
                metrics.append({
                    'category': 'session',
                    'name': 'files_per_session',
                    'value': file_count
                })

            except Exception as e:
                logger.warning(f"Failed to calculate session metrics: {e}")

            # Cleanup
            del self._session_starts[session_id]
            self._session_tool_counts.pop(session_id, None)
            self._session_file_changes.pop(session_id, None)

        return metrics

    def _calculate_composite_metrics(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Calculate composite metrics like productivity score.

        Productivity Score (0-100):
        - Base: 50 points
        - Tool efficiency: up to 25 points
        - Low errors: up to 15 points (penalty)
        - Code impact: up to 10 points
        """
        metrics = []

        try:
            # Base score
            score = 50.0

            # Tool efficiency bonus (based on success rate)
            total_success = sum(self._tool_success.values())
            total_failures = sum(self._tool_failures.values())
            if (total_success + total_failures) > 0:
                success_rate = total_success / (total_success + total_failures)
                score += success_rate * 25  # Up to 25 points

            # Error penalty
            if total_failures > 0:
                error_rate = total_failures / (total_success + total_failures)
                score -= error_rate * 15  # Up to 15 point penalty

            # Code impact bonus (based on acceptance rate)
            if len(self._acceptance_window) >= 10:
                acceptance_rate = sum(self._acceptance_window) / len(self._acceptance_window)
                score += acceptance_rate * 10  # Up to 10 points

            # Clamp to 0-100
            score = max(0, min(100, score))

            metrics.append({
                'category': 'session',
                'name': 'productivity_score',
                'value': score
            })

        except Exception as e:
            logger.error(f"Failed to calculate composite metrics: {e}")

        return metrics

    def _track_session_start(self, event: Dict[str, Any]) -> None:
        """Track session start for duration calculation."""
        session_id = event.get('session_id', '')
        timestamp = event.get('timestamp', '')
        self._session_starts[session_id] = timestamp

    def get_current_stats(self) -> Dict[str, Any]:
        """
        Get current statistics for monitoring.

        Returns:
            Dictionary with current metric statistics
        """
        total_success = sum(self._tool_success.values())
        total_failures = sum(self._tool_failures.values())

        return {
            'latency_window_size': len(self._latency_window),
            'acceptance_window_size': len(self._acceptance_window),
            'total_tool_executions': total_success + total_failures,
            'tool_success_count': total_success,
            'tool_failure_count': total_failures,
            'active_sessions': len(self._session_starts),
            'tracked_tool_types': len(self._tool_counts),
        }
