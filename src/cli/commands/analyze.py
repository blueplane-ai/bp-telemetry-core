# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Analyze command implementation for deep session analysis.
"""

import click
from rich.console import Console

from ..utils.config import Config
from ..utils.client import APIClient
from ..formatters import get_formatter

console = Console()


@click.command()
@click.argument("session_id")
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Include detailed timeline"
)
@click.option(
    "--tools",
    is_flag=True,
    help="Show tool usage breakdown"
)
@click.option(
    "--files",
    is_flag=True,
    help="Show file modification details"
)
@click.option(
    "--insights",
    is_flag=True,
    help="Include AI insights"
)
@click.option(
    "--export",
    type=click.Path(),
    help="Export analysis to file"
)
@click.option(
    "--format", "-f",
    type=click.Choice(["table", "json", "chart"]),
    help="Output format"
)
@click.pass_obj
def analyze(
    config: Config,
    session_id: str,
    verbose: bool,
    tools: bool,
    files: bool,
    insights: bool,
    export: str,
    format: str
):
    """
    Deep analysis of a specific coding session.

    Provides detailed breakdown of metrics, tool usage, file changes,
    and AI-powered insights for the specified session.

    Examples:
        blueplane analyze sess_abc123              # Basic analysis
        blueplane analyze sess_abc123 --verbose    # Include timeline
        blueplane analyze sess_abc123 --tools      # Tool breakdown
        blueplane analyze sess_abc123 --files      # File changes
        blueplane analyze sess_abc123 --insights   # AI insights
    """
    # Use config default format if not specified
    output_format = format or config.default_format

    # Get formatter
    formatter = get_formatter(output_format)

    try:
        # Create API client
        client = APIClient(config)

        # Fetch analysis
        with console.status(f"Analyzing session {session_id}..."):
            analysis = client.get_session_analysis(
                session_id=session_id,
                include_tools=tools or verbose,
                include_files=files or verbose,
                include_insights=insights or verbose
            )

        # Export if requested
        if export:
            import json
            with open(export, "w") as f:
                json.dump(analysis, f, indent=2, default=str)
            formatter.format_success(f"Analysis exported to {export}")

        # Format and display
        formatter.format_analysis(analysis)

    except Exception as e:
        formatter.format_error(str(e))
        raise click.Abort()