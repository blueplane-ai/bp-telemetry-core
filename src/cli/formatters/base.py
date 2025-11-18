# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Base formatter class for output formatting.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from rich.console import Console

console = Console()


class BaseFormatter(ABC):
    """Abstract base class for output formatters."""

    @abstractmethod
    def format_metrics(self, data: Dict[str, Any], include_trends: bool = True):
        """Format metrics data for output."""
        pass

    @abstractmethod
    def format_sessions(self, sessions: List[Dict[str, Any]]):
        """Format sessions list for output."""
        pass

    @abstractmethod
    def format_analysis(self, analysis: Dict[str, Any]):
        """Format session analysis for output."""
        pass

    @abstractmethod
    def format_insights(self, insights: List[Dict[str, Any]]):
        """Format insights for output."""
        pass

    @abstractmethod
    def format_error(self, error: str):
        """Format error message for output."""
        pass

    def format_success(self, message: str):
        """Format success message for output."""
        console.print(f"[green]✓[/green] {message}")

    def format_warning(self, message: str):
        """Format warning message for output."""
        console.print(f"[yellow]⚠[/yellow] {message}")

    def format_info(self, message: str):
        """Format info message for output."""
        console.print(f"[blue]ℹ[/blue] {message}")

    def _format_percentage(self, value: float, show_sign: bool = False) -> str:
        """Format a percentage value."""
        percent = value * 100
        formatted = f"{percent:.1f}%"

        if show_sign and value > 0:
            formatted = f"+{formatted}"

        return formatted

    def _format_number(self, value: float, decimals: int = 0) -> str:
        """Format a number with optional decimal places."""
        if decimals == 0:
            return f"{int(value):,}"
        else:
            return f"{value:,.{decimals}f}"

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        else:
            hours = seconds / 3600
            return f"{hours:.1f}h"

    def _format_bytes(self, bytes: int) -> str:
        """Format bytes in human-readable format."""
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes < 1024.0:
                return f"{bytes:.1f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.1f} PB"

    def _get_trend_indicator(self, current: float, previous: float) -> str:
        """Get trend indicator based on change."""
        if current > previous:
            return "↑"
        elif current < previous:
            return "↓"
        else:
            return "→"

    def _get_trend_color(self, current: float, previous: float, higher_is_better: bool = True) -> str:
        """Get color for trend based on change."""
        if current > previous:
            return "green" if higher_is_better else "red"
        elif current < previous:
            return "red" if higher_is_better else "green"
        else:
            return "yellow"