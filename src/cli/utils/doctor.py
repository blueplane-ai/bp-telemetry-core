# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
System diagnostics and health check utilities.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .config import Config
from .client import APIClient

console = Console()


def run_diagnostics(config: Config) -> bool:
    """
    Run comprehensive system diagnostics.

    Returns:
        True if all checks pass, False otherwise
    """
    console.print(Panel("[bold cyan]Blueplane CLI Diagnostics[/bold cyan]", border_style="blue"))

    checks = []

    # Check 1: Configuration
    checks.append(_check_configuration(config))

    # Check 2: Server connectivity
    checks.append(_check_server(config))

    # Check 3: File permissions
    checks.append(_check_permissions(config))

    # Check 4: Dependencies
    checks.append(_check_dependencies())

    # Check 5: Environment
    checks.append(_check_environment())

    # Display results
    _display_results(checks)

    # Return overall status
    return all(status for _, status, _ in checks)


def _check_configuration(config: Config) -> Tuple[str, bool, str]:
    """Check configuration validity."""
    try:
        if config.validate():
            return ("Configuration", True, "Valid configuration")
        else:
            return ("Configuration", False, "Invalid configuration values")
    except Exception as e:
        return ("Configuration", False, f"Error validating config: {e}")


def _check_server(config: Config) -> Tuple[str, bool, str]:
    """Check server connectivity."""
    try:
        client = APIClient(config)
        if client.test_connection():
            return ("Server Connection", True, f"Connected to {config.server_url}")
        else:
            return ("Server Connection", False, f"Cannot reach {config.server_url}")
    except Exception as e:
        return ("Server Connection", False, f"Connection error: {e}")


def _check_permissions(config: Config) -> Tuple[str, bool, str]:
    """Check file system permissions."""
    try:
        # Check config directory
        config_dir = config.config_path.parent
        if not config_dir.exists():
            config_dir.mkdir(parents=True, exist_ok=True)

        # Test write permission
        test_file = config_dir / ".test_permission"
        test_file.write_text("test")
        test_file.unlink()

        return ("File Permissions", True, "Read/write access verified")
    except Exception as e:
        return ("File Permissions", False, f"Permission error: {e}")


def _check_dependencies() -> Tuple[str, bool, str]:
    """Check required dependencies."""
    missing = []

    # Check required packages
    required_packages = {
        "click": "CLI framework",
        "rich": "Terminal formatting",
        "requests": "HTTP client",
        "yaml": "YAML parsing"
    }

    for package, description in required_packages.items():
        try:
            __import__(package)
        except ImportError:
            missing.append(f"{package} ({description})")

    if missing:
        return ("Dependencies", False, f"Missing: {', '.join(missing)}")
    else:
        return ("Dependencies", True, "All required packages installed")


def _check_environment() -> Tuple[str, bool, str]:
    """Check environment variables and system info."""
    info = []

    # Python version
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    info.append(f"Python {python_version}")

    # OS info
    info.append(f"{sys.platform}")

    # Environment variables
    env_vars = ["BLUEPLANE_SERVER", "BLUEPLANE_FORMAT", "BLUEPLANE_DEBUG", "NO_COLOR"]
    set_vars = [var for var in env_vars if os.environ.get(var)]

    if set_vars:
        info.append(f"Env vars: {', '.join(set_vars)}")

    return ("Environment", True, " | ".join(info))


def _display_results(checks: List[Tuple[str, bool, str]]):
    """Display diagnostic results in a table."""
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Check", style="cyan", no_wrap=True)
    table.add_column("Status", justify="center")
    table.add_column("Details")

    all_passed = True

    for check_name, passed, details in checks:
        if passed:
            status = "[green]✓ PASS[/green]"
        else:
            status = "[red]✗ FAIL[/red]"
            all_passed = False

        table.add_row(check_name, status, details)

    console.print(table)
    console.print()

    if all_passed:
        console.print("[green]All diagnostics passed![/green]")
    else:
        console.print("[yellow]Some diagnostics failed. Please check the details above.[/yellow]")
        console.print("\nTroubleshooting tips:")
        console.print("• Server connection: Ensure the Layer 2 server is running")
        console.print("• Dependencies: Install missing packages with pip")
        console.print("• Permissions: Check directory permissions and ownership")