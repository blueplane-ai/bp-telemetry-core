# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Config command implementation for managing CLI configuration.
"""

import click
import yaml
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax

from ..utils.config import Config as AppConfig
from ..utils.client import APIClient
from ..formatters import get_formatter

console = Console()


@click.command()
@click.option(
    "--list", "list_config",
    is_flag=True,
    help="Show all configuration values"
)
@click.option(
    "--get",
    help="Get specific configuration key"
)
@click.option(
    "--set",
    nargs=2,
    help="Set key-value pair (key value)"
)
@click.option(
    "--reset",
    is_flag=True,
    help="Reset to default values"
)
@click.option(
    "--export",
    type=click.Path(),
    help="Export configuration to file"
)
@click.option(
    "--import", "import_file",
    type=click.Path(exists=True),
    help="Import configuration from file"
)
@click.option(
    "--validate",
    is_flag=True,
    help="Validate configuration"
)
@click.pass_obj
def config(
    config: AppConfig,
    list_config: bool,
    get: str,
    set: tuple,
    reset: bool,
    export: str,
    import_file: str,
    validate: bool
):
    """
    Manage telemetry configuration.

    Configure CLI settings, server endpoints, display preferences,
    and telemetry thresholds.

    Examples:
        blueplane config --list                           # Show all settings
        blueplane config --get server.url                 # Get specific value
        blueplane config --set server.timeout 60          # Set value
        blueplane config --reset                          # Reset to defaults
        blueplane config --export config.yaml             # Export config
        blueplane config --import config.yaml             # Import config
    """
    formatter = get_formatter(config.default_format)

    try:
        # List configuration
        if list_config:
            _list_configuration(config)
            return

        # Get specific value
        if get:
            value = config.get(get)
            if value is None:
                formatter.format_error(f"Configuration key not found: {get}")
                raise click.Abort()

            if config.default_format == "json":
                import json
                console.print(json.dumps({get: value}, indent=2))
            else:
                console.print(f"{get}: {value}")
            return

        # Set configuration value
        if set:
            key, value = set

            # Try to parse value as appropriate type
            try:
                # Try as boolean
                if value.lower() in ["true", "false"]:
                    value = value.lower() == "true"
                # Try as integer
                elif value.isdigit():
                    value = int(value)
                # Try as float
                elif "." in value:
                    try:
                        value = float(value)
                    except ValueError:
                        pass  # Keep as string
            except AttributeError:
                pass  # Value is already non-string

            # Set the value
            config.set(key, value)
            config.save_to_file()

            formatter.format_success(f"Set {key} = {value}")
            return

        # Reset configuration
        if reset:
            if click.confirm("Reset all configuration to defaults?"):
                # Create new default config
                new_config = AppConfig()
                new_config.save_to_file()
                formatter.format_success("Configuration reset to defaults")
            else:
                formatter.format_warning("Reset cancelled")
            return

        # Export configuration
        if export:
            export_path = Path(export)
            config_dict = config.to_dict()

            if export_path.suffix == ".json":
                import json
                with open(export_path, "w") as f:
                    json.dump(config_dict, f, indent=2)
            else:
                with open(export_path, "w") as f:
                    yaml.dump(config_dict, f, default_flow_style=False)

            formatter.format_success(f"Configuration exported to {export_path}")
            return

        # Import configuration
        if import_file:
            import_path = Path(import_file)

            if import_path.suffix == ".json":
                import json
                with open(import_path) as f:
                    data = json.load(f)
            else:
                with open(import_path) as f:
                    data = yaml.safe_load(f)

            # Update configuration
            for key, value in data.items():
                if hasattr(config, key):
                    setattr(config, key, value)

            config.save_to_file()
            formatter.format_success(f"Configuration imported from {import_path}")
            return

        # Validate configuration
        if validate:
            if config.validate():
                formatter.format_success("Configuration is valid")
            else:
                formatter.format_error("Configuration validation failed")
                raise click.Abort()
            return

        # No options specified, show help
        ctx = click.get_current_context()
        click.echo(ctx.get_help())

    except Exception as e:
        formatter.format_error(str(e))
        raise click.Abort()


def _list_configuration(config: AppConfig):
    """Display configuration in a formatted table."""
    table = Table(title="Current Configuration", show_header=True, header_style="bold magenta")
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Setting", style="blue")
    table.add_column("Value", style="green")

    # Server settings
    table.add_row("Server", "URL", config.server_url)
    table.add_row("Server", "Timeout", f"{config.timeout}s")
    table.add_row("Server", "Retry Count", str(config.retry))
    table.add_row("", "", "")  # Blank row for spacing

    # Display settings
    table.add_row("Display", "Default Format", config.default_format)
    table.add_row("Display", "Color Output", str(not config.no_color))
    table.add_row("Display", "Pager Mode", config.pager)
    table.add_row("Display", "Max Width", str(config.max_width))
    table.add_row("", "", "")

    # Cache settings
    table.add_row("Cache", "Enabled", str(config.cache_enabled))
    table.add_row("Cache", "TTL", f"{config.cache_ttl}s")
    table.add_row("Cache", "Size", f"{config.cache_size} entries")
    table.add_row("", "", "")

    # Telemetry settings
    table.add_row("Telemetry", "Acceptance Threshold", f"{config.acceptance_threshold:.1%}")
    table.add_row("Telemetry", "Productivity Baseline", str(config.productivity_baseline))
    table.add_row("", "", "")

    # Export settings
    table.add_row("Export", "Default Format", config.export_format)
    table.add_row("Export", "Anonymize", str(config.anonymize))
    table.add_row("", "", "")

    # Watch settings
    table.add_row("Watch", "Refresh Interval", f"{config.refresh_interval}s")
    table.add_row("Watch", "Metrics Dashboard", str(config.metrics_dashboard))
    table.add_row("Watch", "Event Stream", str(config.event_stream))

    console.print(table)

    # Show config file location
    console.print(f"\n[dim]Config file: {config.config_path}[/dim]")