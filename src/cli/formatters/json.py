# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
JSON formatter for structured output.
"""

import json
from typing import Any, Dict, List
from rich.console import Console
from rich.syntax import Syntax

from .base import BaseFormatter

console = Console()


class JSONFormatter(BaseFormatter):
    """Format output as JSON for scripting and automation."""

    def __init__(self, pretty: bool = True, colored: bool = True):
        """Initialize JSON formatter.

        Args:
            pretty: Whether to pretty-print JSON
            colored: Whether to use syntax highlighting
        """
        self.pretty = pretty
        self.colored = colored

    def format_metrics(self, data: Dict[str, Any], include_trends: bool = True):
        """Format metrics data as JSON."""
        output = {
            "metrics": data.get("metrics", {})
        }

        if include_trends:
            output["trends"] = data.get("trends", {})

        self._print_json(output)

    def format_sessions(self, sessions: List[Dict[str, Any]]):
        """Format sessions list as JSON."""
        output = {
            "sessions": sessions,
            "count": len(sessions)
        }
        self._print_json(output)

    def format_analysis(self, analysis: Dict[str, Any]):
        """Format session analysis as JSON."""
        self._print_json(analysis)

    def format_insights(self, insights: List[Dict[str, Any]]):
        """Format insights as JSON."""
        output = {
            "insights": insights,
            "count": len(insights)
        }
        self._print_json(output)

    def format_error(self, error: str):
        """Format error message as JSON."""
        output = {
            "error": error,
            "success": False
        }
        self._print_json(output)

    def _print_json(self, data: Any):
        """Print JSON with optional formatting and coloring."""
        if self.pretty:
            json_str = json.dumps(data, indent=2, sort_keys=False, default=str)
        else:
            json_str = json.dumps(data, default=str)

        if self.colored:
            syntax = Syntax(json_str, "json", theme="monokai")
            console.print(syntax)
        else:
            print(json_str)