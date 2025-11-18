# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Configuration management for the CLI.
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class Config:
    """CLI configuration container."""

    # Server settings
    server_url: str = "http://localhost:7531"
    timeout: int = 30
    retry: int = 3

    # Display settings
    default_format: str = "table"  # table, json, chart
    no_color: bool = False
    pager: str = "auto"  # auto, always, never
    max_width: int = 120

    # Cache settings
    cache_enabled: bool = True
    cache_ttl: int = 60  # seconds
    cache_size: int = 1000  # entries

    # Telemetry settings
    acceptance_threshold: float = 0.7
    productivity_baseline: int = 100

    # Export settings
    export_format: str = "json"
    anonymize: bool = False

    # Watch settings
    refresh_interval: int = 5  # seconds
    metrics_dashboard: bool = True
    event_stream: bool = False

    # Debug settings
    debug: bool = False

    # Config file path
    config_path: Optional[Path] = None

    def __post_init__(self):
        """Initialize configuration after creation."""
        # Set default config path if not provided
        if self.config_path is None:
            self.config_path = Path.home() / ".blueplane" / "cli" / "config.yaml"

        # Load from file if exists
        if self.config_path.exists():
            self.load_from_file()

        # Override with environment variables
        self.load_from_env()

    def load_from_file(self):
        """Load configuration from YAML file."""
        try:
            with open(self.config_path) as f:
                data = yaml.safe_load(f) or {}

            # Server settings
            server = data.get("server", {})
            self.server_url = server.get("url", self.server_url)
            self.timeout = server.get("timeout", self.timeout)
            self.retry = server.get("retry", self.retry)

            # Display settings
            display = data.get("display", {})
            self.default_format = display.get("format", self.default_format)
            self.no_color = display.get("color", True) == False  # Note: inverted logic
            self.pager = display.get("pager", self.pager)
            self.max_width = display.get("max_width", self.max_width)

            # Cache settings
            cache = data.get("cache", {})
            self.cache_enabled = cache.get("enabled", self.cache_enabled)
            self.cache_ttl = cache.get("ttl", self.cache_ttl)
            self.cache_size = cache.get("size", self.cache_size)

            # Telemetry settings
            telemetry = data.get("telemetry", {})
            self.acceptance_threshold = telemetry.get("acceptance_threshold", self.acceptance_threshold)
            self.productivity_baseline = telemetry.get("productivity_baseline", self.productivity_baseline)

            # Export settings
            export = data.get("export", {})
            self.export_format = export.get("default_format", self.export_format)
            self.anonymize = export.get("anonymize", self.anonymize)

            # Watch settings
            watch = data.get("watch", {})
            self.refresh_interval = watch.get("refresh_interval", self.refresh_interval)
            self.metrics_dashboard = watch.get("metrics_dashboard", self.metrics_dashboard)
            self.event_stream = watch.get("event_stream", self.event_stream)

        except Exception as e:
            # Silently ignore config file errors
            if self.debug:
                print(f"Warning: Could not load config file: {e}")

    def load_from_env(self):
        """Load configuration from environment variables."""
        # Server URL
        if env_server := os.environ.get("BLUEPLANE_SERVER"):
            self.server_url = env_server

        # Format
        if env_format := os.environ.get("BLUEPLANE_FORMAT"):
            self.default_format = env_format

        # Debug
        if os.environ.get("BLUEPLANE_DEBUG"):
            self.debug = True

        # No color
        if os.environ.get("NO_COLOR"):
            self.no_color = True

    def save_to_file(self):
        """Save current configuration to YAML file."""
        # Create directory if needed
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Build configuration dictionary
        data = {
            "server": {
                "url": self.server_url,
                "timeout": self.timeout,
                "retry": self.retry
            },
            "display": {
                "format": self.default_format,
                "color": not self.no_color,
                "pager": self.pager,
                "max_width": self.max_width
            },
            "cache": {
                "enabled": self.cache_enabled,
                "ttl": self.cache_ttl,
                "size": self.cache_size
            },
            "telemetry": {
                "acceptance_threshold": self.acceptance_threshold,
                "productivity_baseline": self.productivity_baseline
            },
            "export": {
                "default_format": self.export_format,
                "anonymize": self.anonymize
            },
            "watch": {
                "refresh_interval": self.refresh_interval,
                "metrics_dashboard": self.metrics_dashboard,
                "event_stream": self.event_stream
            }
        }

        # Write to file
        with open(self.config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot-notation key."""
        parts = key.split(".")
        value = self.__dict__

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = getattr(value, part, None)

            if value is None:
                return default

        return value

    def set(self, key: str, value: Any):
        """Set configuration value by dot-notation key."""
        parts = key.split(".")

        # Handle nested setting
        if len(parts) == 1:
            setattr(self, parts[0], value)
        else:
            # For nested settings, we'd need to handle more complex logic
            # For now, just set the direct attribute if it exists
            if hasattr(self, parts[-1]):
                setattr(self, parts[-1], value)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            k: v for k, v in self.__dict__.items()
            if not k.startswith("_") and k != "config_path"
        }

    def validate(self) -> bool:
        """Validate configuration values."""
        errors = []

        # Check server URL
        if not self.server_url.startswith(("http://", "https://")):
            errors.append("server_url must start with http:// or https://")

        # Check numeric ranges
        if self.timeout <= 0:
            errors.append("timeout must be positive")

        if self.retry < 0:
            errors.append("retry must be non-negative")

        if self.cache_ttl < 0:
            errors.append("cache_ttl must be non-negative")

        if self.acceptance_threshold < 0 or self.acceptance_threshold > 1:
            errors.append("acceptance_threshold must be between 0 and 1")

        if errors:
            for error in errors:
                print(f"Configuration error: {error}")
            return False

        return True


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Get the global configuration instance."""
    return Config()