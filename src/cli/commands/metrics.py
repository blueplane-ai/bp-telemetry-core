# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Metrics command implementation.
"""

import click
from rich.console import Console

from ..utils.config import Config
from ..utils.client import APIClient
from ..formatters import get_formatter

console = Console()


@click.command()
@click.option(
    "--session", "-s",
    help="Specific session ID (default: current)"
)
@click.option(
    "--period", "-p",
    type=click.Choice(["1h", "24h", "7d", "30d"]),
    help="Time period for metrics"
)
@click.option(
    "--format", "-f",
    type=click.Choice(["table", "json", "chart"]),
    help="Output format"
)
@click.option(
    "--group-by",
    type=click.Choice(["platform", "project", "hour", "day"]),
    help="Group metrics by dimension"
)
@click.option(
    "--include-trends",
    is_flag=True,
    default=True,
    help="Include trend indicators"
)
@click.pass_obj
def metrics(
    config: Config,
    session: str,
    period: str,
    format: str,
    group_by: str,
    include_trends: bool
):
    """
    Display performance metrics for coding sessions.

    Examples:
        blueplane metrics                     # Current session metrics
        blueplane metrics --period 7d          # Last 7 days
        blueplane metrics --format chart       # Display as chart
        blueplane metrics --group-by platform  # Group by platform
    """
    # Use config default format if not specified
    output_format = format or config.default_format

    # Get formatter
    formatter = get_formatter(output_format)

    try:
        # Create API client
        client = APIClient(config)

        # Fetch metrics
        with console.status("Fetching metrics..."):
            data = client.get_metrics(
                session_id=session,
                period=period,
                group_by=group_by
            )

        # Format and display
        formatter.format_metrics(data, include_trends=include_trends)

    except Exception as e:
        formatter.format_error(str(e))
        raise click.Abort()