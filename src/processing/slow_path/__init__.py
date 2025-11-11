# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Slow path processing for async enrichment and metrics calculation.

The slow path processes CDC events from the fast path to:
- Calculate metrics
- Build conversation structure
- Generate insights

Workers consume from Redis Streams CDC queue and process events asynchronously.
"""

from .worker_base import WorkerBase
from .worker_pool import WorkerPoolManager
from .metrics_worker import MetricsWorker

__all__ = [
    'WorkerBase',
    'WorkerPoolManager',
    'MetricsWorker',
]
