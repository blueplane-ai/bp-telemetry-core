"""
Blueplane CLI - Main entry point

Provides commands for managing and querying telemetry data.
"""

# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only

import click
from rich.console import Console

from blueplane import __version__

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="bp")
@click.option("--debug", is_flag=True, help="Enable debug mode")
def cli(debug: bool) -> None:
    """
    Blueplane Telemetry CLI

    Privacy-first telemetry for AI-assisted coding.
    """
    if debug:
        console.print("[yellow]Debug mode enabled[/yellow]")


@cli.command()
def status() -> None:
    """Show system status and health"""
    console.print("[bold green]Blueplane Status[/bold green]")
    console.print("System: [yellow]Not yet implemented[/yellow]")
    # TODO: Implement status checking
    # - Check Docker containers (Redis, Processing Server)
    # - Check database connectivity
    # - Check recent activity


@cli.command()
def stats() -> None:
    """Display telemetry statistics"""
    console.print("[bold green]Telemetry Statistics[/bold green]")
    console.print("Stats: [yellow]Not yet implemented[/yellow]")
    # TODO: Implement statistics display
    # - Event counts
    # - Session counts
    # - Platform breakdowns


@cli.command()
def sessions() -> None:
    """List recent sessions"""
    console.print("[bold green]Recent Sessions[/bold green]")
    console.print("Sessions: [yellow]Not yet implemented[/yellow]")
    # TODO: Implement session listing
    # - Show recent sessions
    # - Filter by platform, date range
    # - Display session details


@cli.command()
@click.argument("output_path", type=click.Path())
@click.option("--format", type=click.Choice(["json", "csv"]), default="json")
def export(output_path: str, format: str) -> None:
    """Export telemetry data"""
    console.print(f"[bold green]Exporting data to {output_path}[/bold green]")
    console.print(f"Format: {format}")
    console.print("Export: [yellow]Not yet implemented[/yellow]")
    # TODO: Implement data export
    # - Export events, sessions, metrics
    # - Support JSON and CSV formats


if __name__ == "__main__":
    cli()
