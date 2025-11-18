# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Table formatter using Rich for beautiful terminal output.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text
from rich.console import Console

from .base import BaseFormatter

console = Console()


class TableFormatter(BaseFormatter):
    """Format output as beautiful tables using Rich."""

    def format_metrics(self, data: Dict[str, Any], include_trends: bool = True):
        """Format metrics data as a table."""
        metrics = data.get("metrics", {})
        trends = data.get("trends", {}) if include_trends else {}

        # Create table
        table = Table(title="Performance Metrics", show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", justify="right")

        if include_trends and trends:
            table.add_column("Change", justify="right")
            table.add_column("Trend", justify="center")

        # Add rows
        metric_configs = {
            "acceptance_rate": ("Acceptance Rate", True, True),  # name, is_percentage, higher_is_better
            "productivity_score": ("Productivity", False, True),
            "error_rate": ("Error Rate", True, False),
            "lines_added": ("Lines Added", False, True),
            "lines_modified": ("Lines Modified", False, True),
            "lines_deleted": ("Lines Deleted", False, None),
            "tools_used": ("Tools Used", False, True),
            "active_time": ("Active Time", False, True),
        }

        for key, (name, is_percentage, higher_is_better) in metric_configs.items():
            if key not in metrics:
                continue

            value = metrics[key]

            # Format value
            if is_percentage:
                value_str = self._format_percentage(value)
            elif key == "active_time":
                value_str = self._format_duration(value)
            else:
                value_str = self._format_number(value)

            # Build row
            row = [name, value_str]

            # Add trend if available
            if include_trends and key in trends:
                trend = trends[key]
                change = trend.get("change", 0)
                direction = trend.get("direction", "unchanged")

                # Format change
                if is_percentage:
                    change_str = self._format_percentage(change, show_sign=True)
                else:
                    change_str = f"{change:+.1f}" if isinstance(change, float) else f"{change:+d}"

                # Get trend indicator
                if direction == "up":
                    indicator = "↑"
                    color = "green" if higher_is_better else "red"
                elif direction == "down":
                    indicator = "↓"
                    color = "red" if higher_is_better else "green"
                else:
                    indicator = "→"
                    color = "yellow"

                row.append(f"[{color}]{change_str}[/{color}]")
                row.append(f"[{color}]{indicator}[/{color}]")

            table.add_row(*row)

        console.print(table)

    def format_sessions(self, sessions: List[Dict[str, Any]]):
        """Format sessions list as a table."""
        if not sessions:
            console.print("[yellow]No sessions found[/yellow]")
            return

        # Create table
        table = Table(title="Coding Sessions", show_header=True, header_style="bold magenta")
        table.add_column("Session ID", style="cyan", no_wrap=True)
        table.add_column("Platform", style="blue")
        table.add_column("Started", style="dim")
        table.add_column("Duration", justify="right")
        table.add_column("Acceptance", justify="right")
        table.add_column("Productivity", justify="right")
        table.add_column("Status", justify="center")

        # Add rows
        for session in sessions:
            session_id = session.get("id", "unknown")[:12]  # Truncate long IDs
            platform = session.get("platform", "unknown")
            started = session.get("started_at", "")
            duration = session.get("duration", 0)
            acceptance = session.get("acceptance_rate", 0)
            productivity = session.get("productivity_score", 0)
            status = session.get("status", "unknown")

            # Format values
            if started:
                try:
                    dt = datetime.fromisoformat(started)
                    started_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    started_str = started[:16]
            else:
                started_str = "-"

            duration_str = self._format_duration(duration)
            acceptance_str = self._format_percentage(acceptance)
            productivity_str = str(productivity)

            # Status coloring
            status_colors = {
                "active": "green",
                "completed": "blue",
                "error": "red",
                "timeout": "yellow"
            }
            status_color = status_colors.get(status, "white")
            status_str = f"[{status_color}]{status}[/{status_color}]"

            table.add_row(
                session_id,
                platform,
                started_str,
                duration_str,
                acceptance_str,
                productivity_str,
                status_str
            )

        console.print(table)

    def format_analysis(self, analysis: Dict[str, Any]):
        """Format session analysis with detailed breakdown."""
        session_id = analysis.get("session_id", "Unknown")
        metrics = analysis.get("metrics", {})
        timeline = analysis.get("timeline", [])
        tools = analysis.get("tools", {})
        files = analysis.get("files", [])
        insights = analysis.get("insights", [])

        # Session header
        header = Panel(
            f"[bold cyan]Session Analysis[/bold cyan]\n"
            f"ID: {session_id}\n"
            f"Platform: {analysis.get('platform', 'Unknown')}\n"
            f"Duration: {self._format_duration(analysis.get('duration', 0))}",
            title="Session Details",
            border_style="blue"
        )
        console.print(header)

        # Metrics summary
        if metrics:
            metrics_table = Table(title="Metrics Summary", show_header=True)
            metrics_table.add_column("Metric", style="cyan")
            metrics_table.add_column("Value", justify="right")

            for key, value in metrics.items():
                if isinstance(value, float) and 0 <= value <= 1:
                    value_str = self._format_percentage(value)
                else:
                    value_str = str(value)
                metrics_table.add_row(key.replace("_", " ").title(), value_str)

            console.print(metrics_table)

        # Tool usage breakdown
        if tools:
            tools_table = Table(title="Tool Usage", show_header=True)
            tools_table.add_column("Tool", style="cyan")
            tools_table.add_column("Count", justify="right")
            tools_table.add_column("Success Rate", justify="right")

            for tool, stats in tools.items():
                count = stats.get("count", 0)
                success = stats.get("success_rate", 0)
                tools_table.add_row(
                    tool,
                    str(count),
                    self._format_percentage(success)
                )

            console.print(tools_table)

        # File modifications
        if files:
            files_table = Table(title="File Modifications", show_header=True)
            files_table.add_column("File", style="cyan", no_wrap=False)
            files_table.add_column("Added", justify="right", style="green")
            files_table.add_column("Modified", justify="right", style="yellow")
            files_table.add_column("Deleted", justify="right", style="red")

            for file in files:
                files_table.add_row(
                    file.get("path", "unknown"),
                    str(file.get("lines_added", 0)),
                    str(file.get("lines_modified", 0)),
                    str(file.get("lines_deleted", 0))
                )

            console.print(files_table)

        # Insights
        if insights:
            insights_panel = Panel(
                "\n".join([f"• {insight}" for insight in insights]),
                title="Key Insights",
                border_style="green"
            )
            console.print(insights_panel)

    def format_insights(self, insights: List[Dict[str, Any]]):
        """Format AI insights as cards."""
        if not insights:
            console.print("[yellow]No insights available[/yellow]")
            return

        panels = []

        for insight in insights:
            insight_type = insight.get("type", "general")
            priority = insight.get("priority", "medium")
            title = insight.get("title", "Insight")
            description = insight.get("description", "")
            actions = insight.get("actions", [])

            # Priority coloring
            priority_colors = {
                "high": "red",
                "medium": "yellow",
                "low": "green"
            }
            border_color = priority_colors.get(priority, "white")

            # Build content
            content = f"[bold]{title}[/bold]\n\n{description}"

            if actions:
                content += "\n\n[bold]Recommended Actions:[/bold]"
                for action in actions:
                    content += f"\n• {action}"

            # Create panel
            panel = Panel(
                content,
                title=f"{insight_type.title()} - {priority.title()} Priority",
                border_style=border_color
            )
            panels.append(panel)

        # Display panels
        for panel in panels:
            console.print(panel)
            console.print()  # Add spacing

    def format_error(self, error: str):
        """Format error message."""
        console.print(f"[bold red]Error:[/bold red] {error}")

    def format_export_summary(self, format: str, file_path: str, records: int):
        """Format export summary."""
        summary = Panel(
            f"[green]Export completed successfully![/green]\n\n"
            f"Format: {format.upper()}\n"
            f"File: {file_path}\n"
            f"Records: {records:,}",
            title="Export Summary",
            border_style="green"
        )
        console.print(summary)