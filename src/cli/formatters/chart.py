# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Chart formatter using Plotext for ASCII charts in terminal.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

try:
    import plotext as plt
except ImportError:
    plt = None

from rich.console import Console
from rich.panel import Panel

from .base import BaseFormatter

console = Console()


class ChartFormatter(BaseFormatter):
    """Format output as ASCII charts using Plotext."""

    def __init__(self):
        """Initialize chart formatter."""
        if plt is None:
            console.print("[yellow]Warning: Plotext not installed. Install with: pip install plotext[/yellow]")

    def format_metrics(self, data: Dict[str, Any], include_trends: bool = True):
        """Format metrics data as charts."""
        if plt is None:
            console.print("[red]Plotext is required for chart output[/red]")
            return

        metrics = data.get("metrics", {})
        history = data.get("history", [])

        if history:
            self._plot_metrics_history(history)
        else:
            self._plot_metrics_bar(metrics)

    def format_sessions(self, sessions: List[Dict[str, Any]]):
        """Format sessions as a timeline chart."""
        if plt is None:
            console.print("[red]Plotext is required for chart output[/red]")
            return

        if not sessions:
            console.print("[yellow]No sessions to chart[/yellow]")
            return

        # Extract data for plotting
        dates = []
        acceptance_rates = []
        productivity_scores = []

        for session in sessions:
            if started := session.get("started_at"):
                try:
                    dt = datetime.fromisoformat(started)
                    dates.append(dt)
                    acceptance_rates.append(session.get("acceptance_rate", 0) * 100)
                    productivity_scores.append(session.get("productivity_score", 0))
                except:
                    continue

        if not dates:
            console.print("[yellow]No valid session data for charting[/yellow]")
            return

        # Create dual-axis plot
        plt.clear_data()
        plt.title("Session Performance Over Time")

        # Plot acceptance rate
        plt.plot(dates, acceptance_rates, label="Acceptance Rate (%)", color="green")

        # Normalize productivity scores for dual axis
        if max(productivity_scores) > 0:
            normalized_productivity = [
                p / max(productivity_scores) * 100 for p in productivity_scores
            ]
            plt.plot(dates, normalized_productivity, label="Productivity (normalized)", color="blue")

        plt.xlabel("Date")
        plt.ylabel("Value")
        plt.show()

    def format_analysis(self, analysis: Dict[str, Any]):
        """Format session analysis as charts."""
        if plt is None:
            console.print("[red]Plotext is required for chart output[/red]")
            return

        tools = analysis.get("tools", {})
        files = analysis.get("files", [])

        # Tool usage chart
        if tools:
            self._plot_tool_usage(tools)

        # File modifications chart
        if files:
            self._plot_file_modifications(files)

    def format_insights(self, insights: List[Dict[str, Any]]):
        """Format insights as a priority distribution chart."""
        if plt is None:
            console.print("[red]Plotext is required for chart output[/red]")
            return

        if not insights:
            console.print("[yellow]No insights to chart[/yellow]")
            return

        # Count by priority
        priority_counts = {"high": 0, "medium": 0, "low": 0}
        for insight in insights:
            priority = insight.get("priority", "medium")
            if priority in priority_counts:
                priority_counts[priority] += 1

        # Create bar chart
        plt.clear_data()
        plt.title("Insights by Priority")
        plt.bar(
            list(priority_counts.keys()),
            list(priority_counts.values()),
            color=["red", "yellow", "green"]
        )
        plt.xlabel("Priority")
        plt.ylabel("Count")
        plt.show()

    def format_error(self, error: str):
        """Format error message."""
        console.print(f"[bold red]Error:[/bold red] {error}")

    def _plot_metrics_bar(self, metrics: Dict[str, Any]):
        """Plot metrics as a bar chart."""
        # Filter numeric metrics
        numeric_metrics = {}
        for key, value in metrics.items():
            if isinstance(value, (int, float)) and key != "acceptance_rate" and key != "error_rate":
                numeric_metrics[key] = value

        if not numeric_metrics:
            console.print("[yellow]No numeric metrics to chart[/yellow]")
            return

        plt.clear_data()
        plt.title("Current Metrics")

        labels = []
        values = []
        for key, value in numeric_metrics.items():
            labels.append(key.replace("_", " ").title())
            values.append(value)

        plt.bar(labels, values, color="cyan")
        plt.xlabel("Metric")
        plt.ylabel("Value")
        plt.show()

    def _plot_metrics_history(self, history: List[Dict[str, Any]]):
        """Plot metrics history over time."""
        if not history:
            return

        # Extract time series data
        timestamps = []
        acceptance_rates = []
        error_rates = []

        for point in history:
            if timestamp := point.get("timestamp"):
                try:
                    dt = datetime.fromisoformat(timestamp)
                    timestamps.append(dt)
                    acceptance_rates.append(point.get("acceptance_rate", 0) * 100)
                    error_rates.append(point.get("error_rate", 0) * 100)
                except:
                    continue

        if not timestamps:
            return

        plt.clear_data()
        plt.title("Metrics Over Time")
        plt.plot(timestamps, acceptance_rates, label="Acceptance Rate (%)", color="green")
        plt.plot(timestamps, error_rates, label="Error Rate (%)", color="red")
        plt.xlabel("Time")
        plt.ylabel("Percentage")
        plt.show()

    def _plot_tool_usage(self, tools: Dict[str, Any]):
        """Plot tool usage statistics."""
        if not tools:
            return

        tool_names = []
        tool_counts = []

        for tool, stats in tools.items():
            tool_names.append(tool[:15])  # Truncate long names
            tool_counts.append(stats.get("count", 0))

        plt.clear_data()
        plt.title("Tool Usage")
        plt.bar(tool_names, tool_counts, color="blue")
        plt.xlabel("Tool")
        plt.ylabel("Usage Count")
        plt.show()

    def _plot_file_modifications(self, files: List[Dict[str, Any]]):
        """Plot file modification statistics."""
        if not files:
            return

        # Aggregate statistics
        total_added = sum(f.get("lines_added", 0) for f in files)
        total_modified = sum(f.get("lines_modified", 0) for f in files)
        total_deleted = sum(f.get("lines_deleted", 0) for f in files)

        plt.clear_data()
        plt.title("Code Changes")
        plt.bar(
            ["Added", "Modified", "Deleted"],
            [total_added, total_modified, total_deleted],
            color=["green", "yellow", "red"]
        )
        plt.xlabel("Change Type")
        plt.ylabel("Lines")
        plt.show()