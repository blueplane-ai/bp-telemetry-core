# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Sessions command implementation.
"""

import click
from rich.console import Console

from ..utils.config import Config
from ..utils.client import APIClient
from ..formatters import get_formatter

console = Console()


@click.command()
@click.option(
    "--limit", "-n",
    type=int,
    default=10,
    help="Number of sessions to show"
)
@click.option(
    "--offset",
    type=int,
    default=0,
    help="Offset for pagination"
)
@click.option(
    "--platform", "-p",
    type=click.Choice(["all", "claude", "cursor"]),
    default="all",
    help="Filter by platform"
)
@click.option(
    "--project",
    help="Filter by project hash"
)
@click.option(
    "--min-acceptance",
    type=float,
    help="Minimum acceptance rate (0-1)"
)
@click.option(
    "--min-productivity",
    type=int,
    help="Minimum productivity score"
)
@click.option(
    "--since",
    help="Start date filter (YYYY-MM-DD)"
)
@click.option(
    "--until",
    help="End date filter (YYYY-MM-DD)"
)
@click.option(
    "--format", "-f",
    type=click.Choice(["table", "json", "chart"]),
    help="Output format"
)
@click.pass_obj
def sessions(
    config: Config,
    limit: int,
    offset: int,
    platform: str,
    project: str,
    min_acceptance: float,
    min_productivity: int,
    since: str,
    until: str,
    format: str
):
    """
    List and filter coding sessions.

    Examples:
        blueplane sessions                        # List recent sessions
        blueplane sessions -n 20                  # Show 20 sessions
        blueplane sessions --platform claude      # Claude sessions only
        blueplane sessions --min-acceptance 0.7   # High acceptance sessions
        blueplane sessions --since 2025-11-01     # Sessions since date
    """
    # Use config default format if not specified
    output_format = format or config.default_format

    # Get formatter
    formatter = get_formatter(output_format)

    try:
        # Create API client
        client = APIClient(config)

        # Validate parameters
        if min_acceptance is not None and (min_acceptance < 0 or min_acceptance > 1):
            formatter.format_error("min-acceptance must be between 0 and 1")
            raise click.Abort()

        # Fetch sessions
        with console.status("Fetching sessions..."):
            result = client.get_sessions(
                limit=limit,
                offset=offset,
                platform=None if platform == "all" else platform,
                project=project,
                min_acceptance=min_acceptance,
                min_productivity=min_productivity,
                since=since,
                until=until
            )

        # Extract sessions list
        sessions = result.get("sessions", [])

        # Format and display
        formatter.format_sessions(sessions)

        # Show pagination info
        total = result.get("total", len(sessions))
        if total > limit and output_format == "table":
            console.print(
                f"\n[dim]Showing {offset + 1}-{min(offset + limit, total)} of {total} sessions. "
                f"Use --offset to see more.[/dim]"
            )

    except Exception as e:
        formatter.format_error(str(e))
        raise click.Abort()