# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Watch command implementation for real-time monitoring.
"""

import asyncio
import json
import signal
import sys
from datetime import datetime
from typing import Optional, Dict, Any

import click
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text

try:
    import websockets
except ImportError:
    websockets = None

from ..utils.config import Config
from ..utils.client import APIClient

console = Console()


class MetricsDashboard:
    """Live metrics dashboard display."""

    def __init__(self):
        self.metrics = {}
        self.events = []
        self.last_update = datetime.now()
        self.connection_status = "Connecting..."

    def update_metrics(self, data: Dict[str, Any]):
        """Update metrics data."""
        self.metrics = data
        self.last_update = datetime.now()

    def add_event(self, event: Dict[str, Any]):
        """Add new event to the list."""
        self.events.insert(0, event)
        # Keep only last 10 events
        self.events = self.events[:10]

    def set_status(self, status: str):
        """Set connection status."""
        self.connection_status = status

    def generate_layout(self) -> Layout:
        """Generate the dashboard layout."""
        layout = Layout()

        # Create header
        header = Panel(
            f"[bold cyan]Blueplane Telemetry Dashboard[/bold cyan]\n"
            f"Status: {self.connection_status} | "
            f"Updated: {self.last_update.strftime('%H:%M:%S')}",
            height=3
        )

        # Create metrics table
        metrics_table = Table(show_header=True, header_style="bold magenta")
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Value", justify="right")
        metrics_table.add_column("Trend", justify="center")

        if self.metrics:
            metrics_data = self.metrics.get("metrics", {})
            trends = self.metrics.get("trends", {})

            for key, value in metrics_data.items():
                # Format value
                if isinstance(value, float) and 0 <= value <= 1:
                    value_str = f"{value:.1%}"
                else:
                    value_str = str(value)

                # Get trend
                trend = ""
                if key in trends:
                    direction = trends[key].get("direction", "unchanged")
                    if direction == "up":
                        trend = "[green]↑[/green]"
                    elif direction == "down":
                        trend = "[red]↓[/red]"
                    else:
                        trend = "[yellow]→[/yellow]"

                metrics_table.add_row(
                    key.replace("_", " ").title(),
                    value_str,
                    trend
                )

        metrics_panel = Panel(metrics_table, title="Metrics", border_style="blue")

        # Create events list
        events_text = Text()
        for event in self.events:
            timestamp = event.get("timestamp", "")
            event_type = event.get("type", "unknown")
            description = event.get("description", "")

            events_text.append(f"{timestamp[:8]} ", style="dim")
            events_text.append(f"[{event_type}] ", style="cyan")
            events_text.append(f"{description}\n")

        events_panel = Panel(events_text or "No events yet", title="Recent Events", border_style="green")

        # Arrange layout
        layout.split_column(
            header,
            Layout(name="main", ratio=2),
            Layout(name="events", ratio=1)
        )
        layout["main"].update(metrics_panel)
        layout["events"].update(events_panel)

        return layout


@click.command()
@click.option(
    "--metrics",
    is_flag=True,
    help="Watch metrics dashboard"
)
@click.option(
    "--events",
    is_flag=True,
    help="Watch event stream"
)
@click.option(
    "--session",
    help="Specific session to watch"
)
@click.option(
    "--interval",
    type=int,
    default=5,
    help="Refresh interval in seconds"
)
@click.option(
    "--format", "-f",
    type=click.Choice(["dashboard", "stream"]),
    default="dashboard",
    help="Display format"
)
@click.pass_obj
def watch(
    config: Config,
    metrics: bool,
    events: bool,
    session: str,
    interval: int,
    format: str
):
    """
    Real-time monitoring dashboard.

    Provides live updates of metrics and events using WebSocket
    connections for real-time telemetry monitoring.

    Examples:
        blueplane watch --metrics              # Watch metrics dashboard
        blueplane watch --events               # Watch event stream
        blueplane watch --session sess_abc123  # Watch specific session
        blueplane watch --interval 10          # Update every 10 seconds
    """
    if not metrics and not events:
        metrics = True  # Default to metrics if nothing specified

    if websockets is None:
        console.print("[red]WebSocket support required. Install with: pip install websockets[/red]")
        raise click.Abort()

    # Use async event loop
    try:
        if format == "dashboard":
            asyncio.run(watch_dashboard(config, metrics, events, session, interval))
        else:
            asyncio.run(watch_stream(config, metrics, events, session, interval))
    except KeyboardInterrupt:
        console.print("\n[yellow]Watch mode stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise click.Abort()


async def watch_dashboard(
    config: Config,
    show_metrics: bool,
    show_events: bool,
    session: Optional[str],
    interval: int
):
    """Run the dashboard display mode."""
    dashboard = MetricsDashboard()

    # WebSocket URL
    ws_url = config.server_url.replace("http://", "ws://").replace("https://", "wss://")

    if show_metrics:
        endpoint = f"{ws_url}/ws/metrics"
    else:
        endpoint = f"{ws_url}/ws/events"

    if session:
        endpoint += f"?session={session}"

    try:
        async with websockets.connect(endpoint) as websocket:
            dashboard.set_status("[green]Connected[/green]")

            with Live(
                dashboard.generate_layout(),
                console=console,
                refresh_per_second=2,
                screen=True
            ) as live:
                # Send initial request
                await websocket.send(json.dumps({"action": "subscribe"}))

                # Handle messages
                while True:
                    try:
                        # Wait for message with timeout
                        message = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=interval
                        )

                        data = json.loads(message)

                        # Update dashboard based on message type
                        if data.get("type") == "metrics":
                            dashboard.update_metrics(data)
                        elif data.get("type") == "event":
                            dashboard.add_event(data)

                        # Update display
                        live.update(dashboard.generate_layout())

                    except asyncio.TimeoutError:
                        # Send heartbeat
                        await websocket.send(json.dumps({"action": "ping"}))

                    except websockets.exceptions.ConnectionClosed:
                        dashboard.set_status("[red]Disconnected[/red]")
                        break

    except Exception as e:
        dashboard.set_status(f"[red]Error: {e}[/red]")
        raise


async def watch_stream(
    config: Config,
    show_metrics: bool,
    show_events: bool,
    session: Optional[str],
    interval: int
):
    """Run the stream display mode."""
    # WebSocket URL
    ws_url = config.server_url.replace("http://", "ws://").replace("https://", "wss://")

    if show_metrics:
        endpoint = f"{ws_url}/ws/metrics"
    else:
        endpoint = f"{ws_url}/ws/events"

    if session:
        endpoint += f"?session={session}"

    try:
        async with websockets.connect(endpoint) as websocket:
            console.print("[green]Connected to stream[/green]")

            # Send initial request
            await websocket.send(json.dumps({"action": "subscribe"}))

            # Handle messages
            while True:
                try:
                    # Wait for message
                    message = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=interval * 2
                    )

                    data = json.loads(message)

                    # Print based on type
                    if data.get("type") == "metrics":
                        console.print(f"[cyan]Metrics Update:[/cyan]")
                        for key, value in data.get("metrics", {}).items():
                            console.print(f"  {key}: {value}")
                    elif data.get("type") == "event":
                        timestamp = data.get("timestamp", "")
                        event_type = data.get("event_type", "unknown")
                        description = data.get("description", "")
                        console.print(f"[{timestamp}] [{event_type}] {description}")

                except asyncio.TimeoutError:
                    # Send heartbeat
                    await websocket.send(json.dumps({"action": "ping"}))

                except websockets.exceptions.ConnectionClosed:
                    console.print("[red]Stream disconnected[/red]")
                    break

    except Exception as e:
        console.print(f"[red]Stream error: {e}[/red]")
        raise