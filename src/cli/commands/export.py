# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Export command implementation for data extraction.
"""

import click
from pathlib import Path
from rich.console import Console

from ..utils.config import Config
from ..utils.client import APIClient
from ..formatters import get_formatter

console = Console()


@click.command()
@click.option(
    "--format", "-f",
    type=click.Choice(["csv", "json", "parquet"]),
    required=True,
    help="Export format"
)
@click.option(
    "--output", "-o",
    type=click.Path(),
    required=True,
    help="Output file path"
)
@click.option(
    "--start",
    help="Start date (YYYY-MM-DD)"
)
@click.option(
    "--end",
    help="End date (YYYY-MM-DD)"
)
@click.option(
    "--filter",
    multiple=True,
    help="Filter expressions (e.g., platform=claude)"
)
@click.option(
    "--anonymize",
    is_flag=True,
    help="Remove identifying information"
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite existing file"
)
@click.pass_obj
def export(
    config: Config,
    format: str,
    output: str,
    start: str,
    end: str,
    filter: tuple,
    anonymize: bool,
    overwrite: bool
):
    """
    Export telemetry data for external analysis.

    Exports session data and metrics in various formats for use in
    data science tools, spreadsheets, or custom analysis scripts.

    Examples:
        blueplane export -f csv -o metrics.csv
        blueplane export -f json -o data.json --start 2025-11-01
        blueplane export -f parquet -o telemetry.parquet --anonymize
        blueplane export -f csv -o claude.csv --filter platform=claude
    """
    output_path = Path(output)
    formatter = get_formatter(config.default_format)

    try:
        # Check if file exists
        if output_path.exists() and not overwrite:
            if not click.confirm(f"File {output} already exists. Overwrite?"):
                formatter.format_warning("Export cancelled")
                return

        # Parse filters
        filters = {}
        for f in filter:
            if "=" in f:
                key, value = f.split("=", 1)
                filters[key] = value
            else:
                formatter.format_error(f"Invalid filter format: {f}")
                formatter.format_info("Use format: key=value")
                raise click.Abort()

        # Create API client
        client = APIClient(config)

        # Fetch data
        with console.status(f"Exporting data to {format.upper()}..."):
            data = client.export_data(
                format=format,
                start_date=start,
                end_date=end,
                filters=filters if filters else None,
                anonymize=anonymize or config.anonymize
            )

        # Write to file
        with open(output_path, "wb") as f:
            f.write(data)

        # Get file size
        file_size = output_path.stat().st_size

        # Format file size
        def format_size(bytes):
            for unit in ["B", "KB", "MB", "GB"]:
                if bytes < 1024.0:
                    return f"{bytes:.1f} {unit}"
                bytes /= 1024.0
            return f"{bytes:.1f} TB"

        # Show summary
        if config.default_format == "table":
            from ..formatters.table import TableFormatter
            table_formatter = TableFormatter()
            table_formatter.format_export_summary(
                format=format,
                file_path=str(output_path.absolute()),
                records=-1  # We don't know the count from binary data
            )
        else:
            formatter.format_success(
                f"Export completed: {output_path.absolute()} ({format_size(file_size)})"
            )

    except Exception as e:
        formatter.format_error(str(e))
        raise click.Abort()