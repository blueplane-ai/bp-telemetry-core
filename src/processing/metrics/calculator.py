# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Metrics calculator for deriving actionable metrics from telemetry events.

REFACTORED: Now uses SharedMetricsState backed by Redis to ensure accuracy
across multiple workers. Previous in-memory state caused incorrect metrics
when multiple workers processed events concurrently.

Implements all metric categories from layer2_metrics_derivation.md:
- Core performance metrics (latency, throughput)
- Acceptance and quality metrics
- Usage pattern metrics
- Interaction metrics
- Composite metrics (productivity score)
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from .shared_state import SharedMetricsState

logger = logging.getLogger(__name__)


class MetricsCalculator:
    """
    Calculates metrics from telemetry events using Redis-backed shared state.

    All state is stored in Redis, allowing multiple workers to process events
    concurrently while maintaining accurate global metrics.
    """

    def __init__(self, shared_state: SharedMetricsState):
        """
        Initialize metrics calculator with shared state.

        Args:
            shared_state: SharedMetricsState instance backed by Redis
        """
        self.state = shared_state

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

            # Note: Composite metrics are now calculated by a background task in server.py
            # This avoids performance overhead and worker coordination issues

        except Exception as e:
            logger.error(f"Error calculating metrics for event {event.get('event_id')}: {e}")

        return metrics

    def _calculate_latency_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate latency metrics from tool execution events.

        Metrics:
        - Tool execution latency (p50, p95, p99, avg)
        """
        metrics = []
        duration_ms = event.get('duration_ms')
        tool_name = event.get('tool_name', 'unknown')

        if duration_ms is not None and duration_ms >= 0:
            # Add to shared sliding window
            self.state.add_latency(duration_ms, tool_name)

            # Get percentiles from shared state
            percentiles = self.state.get_latency_percentiles()

            metrics.append({
                'category': 'tools',
                'name': 'tool_latency_p50',
                'value': percentiles['p50']
            })
            metrics.append({
                'category': 'tools',
                'name': 'tool_latency_p95',
                'value': percentiles['p95']
            })
            metrics.append({
                'category': 'tools',
                'name': 'tool_latency_p99',
                'value': percentiles['p99']
            })
            metrics.append({
                'category': 'tools',
                'name': 'tool_latency_avg',
                'value': percentiles['avg']
            })

        return metrics

    def _calculate_tool_usage_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate tool usage distribution and success rates.

        Metrics:
        - Tool frequency
        - Tool success rate
        - Session tool count (FIXED: now increments session tools)
        """
        metrics = []
        tool_name = event.get('tool_name', 'unknown')
        session_id = event.get('session_id', '')

        # Only track success if explicitly provided (conservative approach)
        # Defaults to None to avoid artificially inflating success rates
        payload = event.get('payload', {})
        success = payload.get('success') if 'success' in payload else None

        # Update shared counters (only if success status is explicitly provided)
        if success is not None:
            self.state.increment_tool_count(tool_name, success)

        # CRITICAL FIX: Increment session tool count (Issue #4 from review)
        self.state.increment_session_tool_count(session_id)

        # Calculate success rate for this tool
        tool_success_rate = self.state.get_tool_success_rate(tool_name)
        metrics.append({
            'category': 'tools',
            'name': f'tool_success_rate_{tool_name.lower()}',
            'value': tool_success_rate
        })

        # Overall tool success rate
        overall_success_rate = self.state.get_tool_success_rate()
        metrics.append({
            'category': 'tools',
            'name': 'tool_success_rate',
            'value': overall_success_rate
        })

        # Tool frequency
        frequency = self.state.get_tool_frequency(tool_name)
        metrics.append({
            'category': 'tools',
            'name': f'tool_frequency_{tool_name.lower()}',
            'value': frequency
        })

        return metrics

    def _calculate_acceptance_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate code acceptance metrics.

        Metrics:
        - Acceptance rate
        - Rejection rate
        """
        metrics = []
        payload = event.get('payload', {})

        # Only track acceptance if explicitly provided (conservative approach)
        # Defaults to None to avoid artificially inflating acceptance rates
        accepted = payload.get('accepted') if 'accepted' in payload else None

        # Track acceptance (only if explicitly provided)
        if accepted is not None:
            self.state.add_acceptance(accepted)

        # Calculate acceptance rate from shared state
        acceptance_rate = self.state.get_acceptance_rate()
        metrics.append({
            'category': 'session',
            'name': 'acceptance_rate',
            'value': acceptance_rate
        })

        rejection_rate = 100 - acceptance_rate
        metrics.append({
            'category': 'session',
            'name': 'rejection_rate',
            'value': rejection_rate
        })

        return metrics

    def _calculate_interaction_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate user interaction metrics.

        Metrics:
        - Prompt frequency
        - Prompt length
        - Prompts per session
        """
        metrics = []
        session_id = event.get('session_id', '')
        payload = event.get('payload', {})

        # Track prompts per session
        self.state.increment_session_prompt_count(session_id)

        # Prompt length (if available)
        prompt_length = payload.get('prompt_length', 0)
        if prompt_length > 0:
            metrics.append({
                'category': 'session',
                'name': 'prompt_length_avg',
                'value': prompt_length
            })

        # Prompts per session
        prompt_count = self.state.get_session_prompt_count(session_id)
        metrics.append({
            'category': 'session',
            'name': 'prompts_per_session',
            'value': prompt_count
        })

        return metrics

    def _calculate_throughput_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate throughput metrics.

        Metrics:
        - Events per second
        """
        metrics = []

        # Record event timestamp in shared state
        self.state.record_event_timestamp()

        # Calculate EPS from shared state
        eps = self.state.get_events_per_second()
        if eps > 0:
            metrics.append({
                'category': 'realtime',
                'name': 'events_per_second',
                'value': eps
            })

        return metrics

    def _calculate_session_metrics(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Calculate session-level metrics when session ends.

        Metrics:
        - Session duration
        - Tools per minute
        - Prompts per session
        """
        metrics = []
        session_id = event.get('session_id', '')

        # Get session start from shared state
        start_time = self.state.get_session_start(session_id)
        if not start_time:
            # No start time recorded
            return metrics

        end_time = event.get('timestamp', '')

        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            duration_seconds = (end_dt - start_dt).total_seconds()

            if duration_seconds > 0:
                metrics.append({
                    'category': 'session',
                    'name': 'session_duration',
                    'value': duration_seconds
                })

                # Tools per minute
                tool_count = self.state.get_session_tool_count(session_id)
                tools_per_minute = (tool_count / duration_seconds) * 60
                metrics.append({
                    'category': 'session',
                    'name': 'tools_per_minute',
                    'value': tools_per_minute
                })

                # Prompts per session (already tracked, but get final count)
                prompt_count = self.state.get_session_prompt_count(session_id)
                metrics.append({
                    'category': 'session',
                    'name': 'prompts_per_session',
                    'value': prompt_count
                })

        except Exception as e:
            logger.warning(f"Failed to calculate session metrics: {e}")

        finally:
            # Cleanup session data
            self.state.clear_session_data(session_id)

        return metrics

    def _calculate_composite_metrics(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Calculate composite metrics like productivity score.

        Productivity Score (0-100):
        - Base: 50 points
        - Tool efficiency: up to 25 points (based on success rate)
        - Low errors: up to 15 points (penalty for errors)
        - Code acceptance: up to 10 points
        """
        metrics = []

        try:
            # Base score
            score = 50.0

            # Tool efficiency bonus (based on success rate)
            success_rate = self.state.get_tool_success_rate()
            score += (success_rate / 100) * 25  # Up to 25 points

            # Error penalty (inverse of success rate)
            error_rate = 100 - success_rate
            score -= (error_rate / 100) * 15  # Up to 15 point penalty

            # Code acceptance bonus
            acceptance_rate = self.state.get_acceptance_rate()
            score += (acceptance_rate / 100) * 10  # Up to 10 points

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
        self.state.set_session_start(session_id, timestamp)

    def get_current_stats(self) -> Dict[str, Any]:
        """
        Get current statistics for monitoring.

        Returns:
            Dictionary with current metric statistics
        """
        try:
            percentiles = self.state.get_latency_percentiles()
            acceptance_rate = self.state.get_acceptance_rate()
            success_rate = self.state.get_tool_success_rate()
            eps = self.state.get_events_per_second()

            return {
                'latency_p50': percentiles['p50'],
                'latency_p95': percentiles['p95'],
                'latency_avg': percentiles['avg'],
                'acceptance_rate': acceptance_rate,
                'tool_success_rate': success_rate,
                'events_per_second': eps,
            }
        except Exception as e:
            logger.error(f"Failed to get current stats: {e}")
            return {}
