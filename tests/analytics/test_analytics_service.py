# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""Unit tests for AnalyticsService."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock

from src.analytics.service import AnalyticsService
from src.capture.shared.config import Config
from tests.fixtures.sqlite_fixtures import (
    temp_sqlite_db,
    sqlite_db_with_cursor_traces,
    sqlite_db_with_claude_traces
)
from tests.fixtures.duckdb_fixtures import temp_duckdb


class TestAnalyticsService:
    """Test AnalyticsService class."""
    
    def test_init_disabled(self):
        """Test initialization with analytics disabled."""
        # Create a mock config with analytics disabled
        config = Config()
        # Override the config dict to disable analytics
        if not hasattr(config, '_config') or config._config is None:
            config._load_config()
        config._config['analytics'] = {'enabled': False}
        
        service = AnalyticsService(config=config)
        assert not service.enabled
        # When disabled, readers/writers are None
        assert not hasattr(service, 'sqlite_reader') or service.sqlite_reader is None
        assert not hasattr(service, 'duckdb_writer') or service.duckdb_writer is None
    
    def test_init_enabled(self, temp_sqlite_db, temp_duckdb):
        """Test initialization with analytics enabled."""
        sqlite_path, _ = temp_sqlite_db
        duckdb_path, _ = temp_duckdb
        
        config = Config()
        config._config = config._config or {}
        config._config['analytics'] = {
            'enabled': True,
            'processing_interval': 60,
            'batch_size': 100,
            'duckdb': {'db_path': str(duckdb_path)}
        }
        # Override SQLite path
        config._config['paths'] = {
            'database': {'telemetry_db': str(sqlite_path)}
        }
        
        service = AnalyticsService(config=config)
        assert service.enabled
        assert service.sqlite_reader is not None
        assert service.duckdb_writer is not None
        assert service.processing_interval == 60
        assert service.batch_size == 100
    
    @pytest.mark.asyncio
    async def test_start_disabled(self):
        """Test start() when service is disabled."""
        config = Config()
        config._config = config._config or {}
        config._config['analytics'] = {'enabled': False}
        
        service = AnalyticsService(config=config)
        await service.start()
        
        # Should not raise error and should not start
        assert not service.running
    
    @pytest.mark.asyncio
    async def test_start_enabled(self, temp_sqlite_db, temp_duckdb):
        """Test start() when service is enabled."""
        sqlite_path, _ = temp_sqlite_db
        duckdb_path, _ = temp_duckdb
        
        config = Config()
        config._config = config._config or {}
        config._config['analytics'] = {
            'enabled': True,
            'processing_interval': 60,
            'batch_size': 100,
            'duckdb': {'db_path': str(duckdb_path)}
        }
        config._config['paths'] = {
            'database': {'telemetry_db': str(sqlite_path)}
        }
        
        service = AnalyticsService(config=config)
        await service.start()
        
        assert service.running
        assert service._task is not None
        
        # Cleanup
        await service.stop()
    
    @pytest.mark.asyncio
    async def test_stop(self, temp_sqlite_db, temp_duckdb):
        """Test stop() gracefully shuts down."""
        sqlite_path, _ = temp_sqlite_db
        duckdb_path, _ = temp_duckdb
        
        config = Config()
        config._config = config._config or {}
        config._config['analytics'] = {
            'enabled': True,
            'processing_interval': 60,
            'batch_size': 100,
            'duckdb': {'db_path': str(duckdb_path)}
        }
        config._config['paths'] = {
            'database': {'telemetry_db': str(sqlite_path)}
        }
        
        service = AnalyticsService(config=config)
        await service.start()
        assert service.running
        
        await service.stop()
        assert not service.running
    
    @pytest.mark.asyncio
    async def test_process_once_cursor(self, sqlite_db_with_cursor_traces, temp_duckdb):
        """Test process_once() processes Cursor traces."""
        sqlite_path, _ = sqlite_db_with_cursor_traces
        duckdb_path, _ = temp_duckdb
        
        config = Config()
        config._config = config._config or {}
        config._config['analytics'] = {
            'enabled': True,
            'processing_interval': 60,
            'batch_size': 100,
            'duckdb': {'db_path': str(duckdb_path)}
        }
        config._config['paths'] = {
            'database': {'telemetry_db': str(sqlite_path)}
        }
        
        service = AnalyticsService(config=config)
        await service.process_once()
        
        # Verify traces were processed
        # Check that processing state was updated
        last_seq = service.sqlite_reader.get_last_processed_sequence("cursor")
        assert last_seq > 0
        
        # Verify DuckDB has data
        result = service.duckdb_writer._connection.execute("""
            SELECT COUNT(*) FROM raw_traces WHERE platform = 'cursor'
        """).fetchone()
        assert result[0] > 0
    
    @pytest.mark.asyncio
    async def test_process_once_claude_code(self, sqlite_db_with_claude_traces, temp_duckdb):
        """Test process_once() processes Claude Code traces."""
        sqlite_path, _ = sqlite_db_with_claude_traces
        duckdb_path, _ = temp_duckdb
        
        config = Config()
        config._config = config._config or {}
        config._config['analytics'] = {
            'enabled': True,
            'processing_interval': 60,
            'batch_size': 100,
            'duckdb': {'db_path': str(duckdb_path)}
        }
        config._config['paths'] = {
            'database': {'telemetry_db': str(sqlite_path)}
        }
        
        service = AnalyticsService(config=config)
        await service.process_once()
        
        # Verify traces were processed
        last_seq = service.sqlite_reader.get_last_processed_sequence("claude_code")
        assert last_seq > 0
    
    @pytest.mark.asyncio
    async def test_process_once_handles_errors(self, temp_sqlite_db, temp_duckdb):
        """Test that process_once() handles errors gracefully."""
        sqlite_path, _ = temp_sqlite_db
        duckdb_path, _ = temp_duckdb
        
        config = Config()
        config._config = config._config or {}
        config._config['analytics'] = {
            'enabled': True,
            'processing_interval': 60,
            'batch_size': 100,
            'duckdb': {'db_path': str(duckdb_path)}
        }
        config._config['paths'] = {
            'database': {'telemetry_db': str(sqlite_path)}
        }
        
        service = AnalyticsService(config=config)
        
        # Mock an error in processing
        with patch.object(service, '_process_platform_sync', side_effect=Exception("Test error")):
            # Should not raise error
            await service.process_once()

