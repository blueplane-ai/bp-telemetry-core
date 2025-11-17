# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Configuration management for capture layer.
Loads and validates configuration from YAML files.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class RedisConfig:
    """Redis connection configuration."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    socket_timeout: float = 1.0
    socket_connect_timeout: float = 1.0
    max_connections: int = 10


@dataclass
class StreamConfig:
    """Redis Stream configuration."""
    name: str
    consumer_group: str
    max_length: int = 10000
    trim_approximate: bool = True
    block_ms: int = 1000
    count: int = 100


@dataclass
class PrivacyConfig:
    """Privacy settings configuration."""
    mode: str = "strict"
    hash_file_paths: bool = True
    hash_workspace: bool = True
    hash_algorithm: str = "sha256"
    hash_truncate_length: int = 16
    opt_out: list = field(default_factory=list)


class Config:
    """
    Configuration manager for Blueplane Telemetry Core.

    Loads configuration from YAML files in config/ directory.
    Provides convenient access to all settings.
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize configuration.

        Args:
            config_dir: Path to configuration directory.
                       Defaults to checking multiple locations
        """
        if config_dir is None:
            # Try multiple locations for config directory
            possible_locations = [
                # 1. User's home directory (where installer puts it)
                Path.home() / ".blueplane",
                # 2. Relative to current file (development/source)
                Path(__file__).parent.parent.parent.parent / "config",
                # 3. System-wide config
                Path("/etc/blueplane"),
            ]

            # Also walk up from current file looking for config/
            current = Path(__file__).parent
            while current != current.parent:
                config_candidate = current / "config"
                if config_candidate.exists():
                    possible_locations.insert(0, config_candidate)
                    break
                current = current.parent

            # Find first existing location
            for location in possible_locations:
                if location.exists() and location.is_dir():
                    # Check if it has any YAML files
                    if list(location.glob("*.yaml")) or list(location.glob("*.yml")):
                        config_dir = location
                        break

            if config_dir is None:
                # Use default location even if it doesn't exist
                # (will use default values)
                config_dir = Path.home() / ".blueplane"

        self.config_dir = Path(config_dir)
        self._redis_config: Optional[Dict[str, Any]] = None
        self._privacy_config: Optional[Dict[str, Any]] = None
        self._cursor_config: Optional[Dict[str, Any]] = None

        # Load configurations
        self._load_configs()

    def _load_configs(self) -> None:
        """Load all configuration files."""
        # Load Redis config
        redis_file = self.config_dir / "redis.yaml"
        if redis_file.exists():
            with open(redis_file, 'r') as f:
                self._redis_config = yaml.safe_load(f)
        else:
            self._redis_config = {}

        # Load Privacy config
        privacy_file = self.config_dir / "privacy.yaml"
        if privacy_file.exists():
            with open(privacy_file, 'r') as f:
                self._privacy_config = yaml.safe_load(f)
        else:
            self._privacy_config = {}

        # Load Cursor config
        cursor_file = self.config_dir / "cursor.yaml"
        if cursor_file.exists():
            with open(cursor_file, 'r') as f:
                self._cursor_config = yaml.safe_load(f)
        else:
            self._cursor_config = {}

    @property
    def redis(self) -> RedisConfig:
        """Get Redis configuration."""
        redis_data = self._redis_config.get("redis", {})
        pool_data = redis_data.get("connection_pool", {})

        return RedisConfig(
            host=redis_data.get("host", "localhost"),
            port=redis_data.get("port", 6379),
            db=redis_data.get("db", 0),
            socket_timeout=pool_data.get("socket_timeout", 1.0),
            socket_connect_timeout=pool_data.get("socket_connect_timeout", 1.0),
            max_connections=pool_data.get("max_connections", 10),
        )

    def get_stream_config(self, stream_type: str) -> StreamConfig:
        """
        Get stream configuration.

        Args:
            stream_type: Type of stream (message_queue, dlq, cdc)

        Returns:
            StreamConfig for the requested stream
        """
        streams = self._redis_config.get("streams", {})
        stream_data = streams.get(stream_type, {})

        return StreamConfig(
            name=stream_data.get("name", f"telemetry:{stream_type}"),
            consumer_group=stream_data.get("consumer_group", "processors"),
            max_length=stream_data.get("max_length", 10000),
            trim_approximate=stream_data.get("trim_approximate", True),
            block_ms=stream_data.get("block_ms", 1000),
            count=stream_data.get("count", 100),
        )

    @property
    def privacy(self) -> PrivacyConfig:
        """Get privacy configuration."""
        privacy_data = self._privacy_config.get("privacy", {})
        sanitization = privacy_data.get("sanitization", {})

        return PrivacyConfig(
            mode=privacy_data.get("mode", "strict"),
            hash_file_paths=sanitization.get("hash_file_paths", True),
            hash_workspace=sanitization.get("hash_workspace", True),
            hash_algorithm=sanitization.get("hash_algorithm", "sha256"),
            hash_truncate_length=sanitization.get("hash_truncate_length", 16),
            opt_out=privacy_data.get("opt_out", []),
        )

    def get_cursor_config(self, section: str) -> Dict[str, Any]:
        """
        Get Cursor-specific configuration.

        Args:
            section: Configuration section (e.g., 'database_monitor', 'markdown_monitor')

        Returns:
            Dictionary of configuration values with defaults
        """
        cursor_data = self._cursor_config.get("cursor", {})
        section_data = cursor_data.get(section, {})
        
        # Provide defaults for common sections
        if section == "markdown_monitor":
            return {
                "enabled": section_data.get("enabled", True),
                "output_dir": section_data.get("output_dir"),
                "poll_interval_seconds": section_data.get("poll_interval_seconds", 120),
                "debounce_delay_seconds": section_data.get("debounce_delay_seconds", 10),
                "query_timeout_seconds": section_data.get("query_timeout_seconds", 1.5),
                "trace_keys": section_data.get("trace_keys", [
                    'aiService.generations',
                    'aiService.prompts',
                    'composer.composerData',
                    'workbench.backgroundComposer.workspacePersistentData',
                    'workbench.agentMode.exitInfo',
                    'interactive.sessions',
                    'history.entries',
                    'cursorAuth/workspaceOpenedDate',
                ]),
            }
        elif section == "database_monitor":
            return {
                "enabled": section_data.get("enabled", True),
                "poll_interval_seconds": section_data.get("poll_interval_seconds", 30),
                "sync_window_hours": section_data.get("sync_window_hours", 24),
                "query_timeout_seconds": section_data.get("query_timeout_seconds", 1.5),
                "max_retries": section_data.get("max_retries", 3),
            }
        elif section == "duckdb_sink":
            return {
                "enabled": section_data.get("enabled", False),
                "database_path": section_data.get("database_path"),
            }
        else:
            return section_data

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get arbitrary configuration value.

        Args:
            key: Dot-separated key path (e.g., "redis.host")
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        parts = key.split(".")

        # Determine which config to search
        if parts[0] == "redis":
            config = self._redis_config
        elif parts[0] == "privacy":
            config = self._privacy_config
        elif parts[0] == "cursor":
            config = self._cursor_config
        else:
            return default

        # Navigate the config dict
        for part in parts:
            if isinstance(config, dict):
                config = config.get(part, default)
            else:
                return default

        return config if config is not None else default
