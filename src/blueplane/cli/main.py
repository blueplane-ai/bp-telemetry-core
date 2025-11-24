#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Blueplane CLI - Main entry point

Command-line interface for managing and querying blueplane telemetry data.
"""

import sys
import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="bp")
def main():
    """
    Blueplane Telemetry CLI

    Privacy-first local telemetry and analytics for AI-assisted coding.
    """
    pass


@main.command()
def status():
    """Check the status of blueplane services"""
    console.print("[yellow]Blueplane CLI - Status command (to be implemented)[/yellow]")
    console.print("✓ CLI entry point working")
    console.print("⚠ Full CLI implementation pending (Track 5)")


@main.command()
def version():
    """Display version information"""
    console.print("[bold]Blueplane Telemetry Core[/bold] v0.1.0")
    console.print("License: AGPL-3.0-only")
    console.print("Copyright © 2025 Sierra Labs LLC")


if __name__ == "__main__":
    sys.exit(main())
