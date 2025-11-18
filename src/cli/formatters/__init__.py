# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""Output formatters for the CLI."""

from .base import BaseFormatter
from .table import TableFormatter
from .json import JSONFormatter
from .chart import ChartFormatter

__all__ = ["BaseFormatter", "TableFormatter", "JSONFormatter", "ChartFormatter"]


def get_formatter(format_type: str) -> BaseFormatter:
    """Get formatter instance by type."""
    formatters = {
        "table": TableFormatter(),
        "json": JSONFormatter(),
        "chart": ChartFormatter()
    }

    return formatters.get(format_type, TableFormatter())