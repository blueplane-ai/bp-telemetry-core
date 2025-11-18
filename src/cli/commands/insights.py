# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Insights command implementation for AI-powered recommendations.
"""

import click
from rich.console import Console

from ..utils.config import Config
from ..utils.client import APIClient
from ..formatters import get_formatter

console = Console()


@click.command()
@click.option(
    "--type", "-t",
    type=click.Choice(["productivity", "errors", "patterns", "all"]),
    default="all",
    help="Type of insights to show"
)
@click.option(
    "--session", "-s",
    help="Get insights for specific session"
)
@click.option(
    "--priority",
    type=click.Choice(["high", "medium", "low", "all"]),
    default="all",
    help="Filter by priority level"
)
@click.option(
    "--actionable",
    is_flag=True,
    help="Only show actionable insights"
)
@click.option(
    "--format", "-f",
    type=click.Choice(["table", "json", "chart"]),
    help="Output format"
)
@click.pass_obj
def insights(
    config: Config,
    type: str,
    session: str,
    priority: str,
    actionable: bool,
    format: str
):
    """
    Get AI-powered insights and recommendations.

    Analyzes your coding patterns and provides actionable recommendations
    for improving productivity, reducing errors, and optimizing workflow.

    Examples:
        blueplane insights                        # All insights
        blueplane insights --type productivity    # Productivity insights
        blueplane insights --type errors          # Error pattern analysis
        blueplane insights --priority high        # High priority only
        blueplane insights --actionable           # Actionable insights only
    """
    # Use config default format if not specified
    output_format = format or config.default_format

    # Get formatter
    formatter = get_formatter(output_format)

    try:
        # Create API client
        client = APIClient(config)

        # Fetch insights
        with console.status("Generating insights..."):
            result = client.get_insights(
                insight_type=None if type == "all" else type,
                session_id=session,
                priority=None if priority == "all" else priority,
                actionable_only=actionable
            )

        # Extract insights list
        insights_list = result.get("insights", [])

        if not insights_list:
            formatter.format_info("No insights available for the specified criteria")
            return

        # Format and display
        formatter.format_insights(insights_list)

        # Show summary
        if output_format == "table":
            total = len(insights_list)
            high_priority = sum(1 for i in insights_list if i.get("priority") == "high")
            actionable_count = sum(1 for i in insights_list if i.get("actionable", False))

            console.print(
                f"\n[dim]Total: {total} insights | "
                f"High Priority: {high_priority} | "
                f"Actionable: {actionable_count}[/dim]"
            )

    except Exception as e:
        formatter.format_error(str(e))
        raise click.Abort()