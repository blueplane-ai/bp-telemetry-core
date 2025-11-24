# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Unified configuration models for Blueplane Telemetry Core.
Provides strongly-typed dataclasses for all configuration sections.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path


# =============================================================================
# PATH CONFIGURATION
# =============================================================================

@dataclass
class DatabasePathsConfig:
    """Database file paths."""
    telemetry_db: Path
    cursor_history_db: Path
    event_buffer_db: Path
    workspace_cache: Path


@dataclass
class ClaudePathsConfig:
    """Claude Code paths."""
    projects_base: Path
    hooks_dir: Path
    settings_file: Path


@dataclass
class CursorPathsConfig:
    """Cursor IDE paths."""
    workspace_storage: Path
    user_db: Path


@dataclass
class PathsConfig:
    """All file and directory paths."""
    blueplane_home: Path
    database: DatabasePathsConfig
    cursor_sessions_dir: Path
    claude: ClaudePathsConfig
    cursor: CursorPathsConfig
    cursor_markdown_output: Optional[Path]


# =============================================================================
# REDIS CONFIGURATION
# =============================================================================

@dataclass
class RedisConnectionConfig:
    """Redis connection settings."""
    host: str = "localhost"
    port: int = 6379


@dataclass
class RedisConnectionPoolConfig:
    """Redis connection pool settings."""
    max_connections: int = 10
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 2.0
    retry_on_timeout: bool = True
    health_check_interval: int = 30


@dataclass
class RedisSocketKeepaliveConfig:
    """Redis socket keepalive options."""
    TCP_KEEPIDLE: int = 60
    TCP_KEEPINTVL: int = 10
    TCP_KEEPCNT: int = 3


@dataclass
class RedisConfig:
    """Complete Redis configuration."""
    connection: RedisConnectionConfig
    connection_pool: RedisConnectionPoolConfig
    decode_responses: bool = False
    socket_keepalive: bool = True
    socket_keepalive_options: RedisSocketKeepaliveConfig = field(
        default_factory=RedisSocketKeepaliveConfig
    )


# =============================================================================
# STREAM CONFIGURATION
# =============================================================================

@dataclass
class MessageQueueStreamConfig:
    """Main message queue stream configuration."""
    max_length: int = 10000
    block_ms: int = 1000
    count: int = 100
    retry_timeout_ms: int = 300000


@dataclass
class DLQStreamConfig:
    """Dead letter queue stream configuration."""
    retention_days: int = 7
    max_length: int = 1000


@dataclass
class CDCStreamConfig:
    """Change data capture stream configuration."""
    max_length: int = 100000
    block_ms: int = 1000
    count: int = 10
    retry_timeout_ms: int = 600000


@dataclass
class StreamsConfig:
    """All stream configurations."""
    message_queue: MessageQueueStreamConfig
    dlq: DLQStreamConfig
    cdc: CDCStreamConfig


# =============================================================================
# TIMEOUT CONFIGURATION
# =============================================================================

@dataclass
class DatabaseTimeoutsConfig:
    """Database operation timeouts."""
    query_timeout: float = 1.5
    connection_timeout: float = 2.0


@dataclass
class RedisTimeoutsConfig:
    """Redis operation timeouts."""
    command_timeout: float = 1.0


@dataclass
class SessionTimeoutsConfig:
    """Session timeout settings."""
    inactive_timeout_hours: int = 24
    cleanup_interval: int = 3600


@dataclass
class ExtensionTimeoutsConfig:
    """Extension connection timeouts."""
    connect_timeout: int = 5000
    max_reconnect_attempts: int = 3
    reconnect_backoff_base: int = 100
    reconnect_backoff_max: int = 3000


@dataclass
class TimeoutsConfig:
    """All timeout values."""
    database: DatabaseTimeoutsConfig
    redis: RedisTimeoutsConfig
    session: SessionTimeoutsConfig
    extension: ExtensionTimeoutsConfig


# =============================================================================
# MONITORING CONFIGURATION
# =============================================================================

@dataclass
class HealthCheckConfig:
    """Health check monitoring settings."""
    interval: int = 60


@dataclass
class QueueDepthConfig:
    """Queue depth thresholds."""
    warning_threshold: int = 5000
    critical_threshold: int = 8000


@dataclass
class LagConfig:
    """Consumer lag thresholds."""
    warning_ms: int = 10000
    critical_ms: int = 60000


@dataclass
class CursorDatabaseMonitorConfig:
    """Cursor database monitoring settings."""
    poll_interval: float = 30.0
    sync_window_hours: int = 24
    max_retries: int = 3
    retry_backoff: float = 2.0
    dedup_window_hours: int = 24
    max_concurrent_workspaces: int = 10


@dataclass
class CursorMarkdownMonitorConfig:
    """Cursor markdown monitoring settings."""
    poll_interval: float = 120.0
    debounce_delay: float = 10.0


@dataclass
class ClaudeJSONLMonitorConfig:
    """Claude JSONL monitoring settings."""
    poll_interval: float = 30.0


@dataclass
class UnifiedCursorMonitorConfig:
    """Unified Cursor monitor settings."""
    cache_ttl: int = 300


@dataclass
class FileWatcherConfig:
    """File watcher settings."""
    stability_threshold: int = 100
    poll_interval: int = 100


@dataclass
class ExtensionDBMonitorConfig:
    """Extension database monitor settings."""
    poll_interval: int = 30000


@dataclass
class MonitoringConfig:
    """Complete monitoring configuration."""
    health_check: HealthCheckConfig
    queue_depth: QueueDepthConfig
    lag: LagConfig
    cursor_database: CursorDatabaseMonitorConfig
    cursor_markdown: CursorMarkdownMonitorConfig
    claude_jsonl: ClaudeJSONLMonitorConfig
    unified_cursor: UnifiedCursorMonitorConfig
    file_watcher: FileWatcherConfig
    extension_db_monitor: ExtensionDBMonitorConfig


# =============================================================================
# BATCHING CONFIGURATION
# =============================================================================

@dataclass
class DefaultBatchConfig:
    """Default batch processing settings."""
    batch_size: int = 100
    batch_timeout: float = 0.1
    min_batch_size: int = 10
    max_batch_size: int = 100


@dataclass
class EventConsumerBatchConfig:
    """Event consumer batch settings."""
    batch_size: int = 100


@dataclass
class BatchingConfig:
    """Batch processing configuration."""
    default: DefaultBatchConfig
    event_consumer: EventConsumerBatchConfig


# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    include_context: bool = True
    log_workspace_mapping: bool = True
    log_session_lifecycle: bool = True
    log_markdown_writes: bool = True


# =============================================================================
# FEATURES CONFIGURATION
# =============================================================================

@dataclass
class DuckDBSinkFeatureConfig:
    """DuckDB sink feature flag."""
    enabled: bool = False


@dataclass
class FeaturesConfig:
    """Feature flags."""
    duckdb_sink: DuckDBSinkFeatureConfig


# =============================================================================
# ROOT CONFIGURATION
# =============================================================================

@dataclass
class BlueplaneConfig:
    """Root configuration object containing all settings."""
    paths: PathsConfig
    redis: RedisConfig
    streams: StreamsConfig
    timeouts: TimeoutsConfig
    monitoring: MonitoringConfig
    batching: BatchingConfig
    logging: LoggingConfig
    features: FeaturesConfig

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BlueplaneConfig":
        """
        Create BlueplaneConfig from dictionary.

        Args:
            data: Configuration dictionary (typically loaded from YAML)

        Returns:
            BlueplaneConfig instance
        """
        # This is a simplified version - the actual implementation
        # in the config loader will handle nested dictionaries,
        # path expansion, environment variable substitution, etc.
        raise NotImplementedError("Use ConfigLoader.load() instead")
