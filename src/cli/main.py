# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Main CLI entry point for Blueplane telemetry system.
"""

import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console

from . import __version__
from .commands import (
    metrics,
    sessions,
    analyze,
    insights,
    export,
    config,
    watch
)
from .utils.config import Config
from .utils.client import APIClient

# Create console for rich output
console = Console()

# Pass context through Click
pass_config = click.make_pass_decorator(Config, ensure=True)


@click.group(invoke_without_command=True)
@click.option(
    "--version",
    is_flag=True,
    help="Show version and exit"
)
@click.option(
    "--server",
    envvar="BLUEPLANE_SERVER",
    default="http://localhost:7531",
    help="Server URL"
)
@click.option(
    "--format",
    envvar="BLUEPLANE_FORMAT",
    type=click.Choice(["table", "json", "chart"]),
    default="table",
    help="Default output format"
)
@click.option(
    "--debug",
    envvar="BLUEPLANE_DEBUG",
    is_flag=True,
    help="Enable debug mode"
)
@click.option(
    "--no-color",
    envvar="NO_COLOR",
    is_flag=True,
    help="Disable colored output"
)
@click.pass_context
def cli(ctx, version: bool, server: str, format: str, debug: bool, no_color: bool):
    """
    Blueplane Telemetry CLI - Privacy-first telemetry for AI-assisted coding.

    Get insights into your coding productivity, acceptance rates, and tool usage
    patterns while keeping all data local.

    Examples:
        blueplane metrics --period 24h
        blueplane sessions --limit 10
        blueplane analyze sess_abc123
        blueplane watch --metrics
    """
    if version:
        click.echo(f"Blueplane CLI version {__version__}")
        ctx.exit()

    # Initialize configuration
    config = Config(
        server_url=server,
        default_format=format,
        debug=debug,
        no_color=no_color
    )

    # Store in context
    ctx.obj = config

    # If no subcommand, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# Add command groups
cli.add_command(metrics.metrics)
cli.add_command(sessions.sessions)
cli.add_command(analyze.analyze)
cli.add_command(insights.insights)
cli.add_command(export.export)
cli.add_command(config.config)
cli.add_command(watch.watch)


# Additional utility commands
@cli.command()
@pass_config
def doctor(config: Config):
    """Check system status and diagnose issues."""
    from .utils.doctor import run_diagnostics
    run_diagnostics(config)


@cli.command()
@pass_config
def ping(config: Config):
    """Test server connection."""
    client = APIClient(config)
    if client.test_connection():
        console.print("[green]✓[/green] Server is reachable")
    else:
        console.print("[red]✗[/red] Cannot reach server", style="bold red")
        sys.exit(1)


@cli.command()
@click.argument(
    "shell",
    type=click.Choice(["bash", "zsh", "fish"])
)
@click.option(
    "--install",
    is_flag=True,
    help="Install the completion script"
)
@click.option(
    "--show",
    is_flag=True,
    help="Show the completion script without installing"
)
def completion(shell: str, install: bool, show: bool):
    """
    Generate and install shell completion scripts.

    Examples:
        blueplane completion bash --install   # Install bash completion
        blueplane completion zsh --show       # Show zsh script
        blueplane completion fish --install  # Install fish completion
    """
    from .utils.completion import install_completion, show_completion_script

    if not install and not show:
        install = True  # Default to install if no flag specified

    if show:
        show_completion_script(shell)
    else:
        if install_completion(shell):
            console.print(f"[green]Shell completion for {shell} installed successfully[/green]")
        else:
            console.print(f"[red]Failed to install shell completion for {shell}[/red]")
            console.print(f"[yellow]Try running with --show to see the script[/yellow]")


def main():
    """Main entry point for the CLI."""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        if os.environ.get("BLUEPLANE_DEBUG"):
            console.print_exception()
        else:
            console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()