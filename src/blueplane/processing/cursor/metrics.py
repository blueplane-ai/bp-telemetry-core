# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Metrics tracking for Cursor session operations.
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)


class SessionMetrics:
    """Track metrics for session operations."""
    
    def __init__(self):
        self.counts: Dict[str, int] = defaultdict(int)
        self.errors: Dict[str, int] = defaultdict(int)
        self.durations: Dict[str, list] = defaultdict(list)
        self.last_reset = datetime.now()
    
    def record_operation(self, operation: str, duration: float, success: bool = True):
        """Record an operation metric."""
        self.counts[operation] += 1
        self.durations[operation].append(duration)
        
        if not success:
            self.errors[operation] += 1
    
    def get_stats(self) -> Dict:
        """Get current statistics."""
        stats = {}
        for op in self.counts:
            durations = self.durations[op]
            stats[op] = {
                'count': self.counts[op],
                'errors': self.errors[op],
                'avg_duration_ms': sum(durations) / len(durations) * 1000 if durations else 0,
                'min_duration_ms': min(durations) * 1000 if durations else 0,
                'max_duration_ms': max(durations) * 1000 if durations else 0,
            }
        return stats
    
    def reset(self):
        """Reset metrics."""
        self.counts.clear()
        self.errors.clear()
        self.durations.clear()
        self.last_reset = datetime.now()


# Global metrics instance
_metrics = SessionMetrics()


def get_metrics() -> SessionMetrics:
    """Get global metrics instance."""
    return _metrics

