# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Basic tests for AnalyticsProcessor.

Tests initialization, configuration, and basic functionality.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from src.analytics.processor import AnalyticsProcessor
from src.capture.shared.config import Config


class TestAnalyticsProcessorInit:
    """Test AnalyticsProcessor initialization."""

    def test_init_with_default_config(self):
        """Test initialization with default config."""
        processor = AnalyticsProcessor()
        assert processor.enabled is False  # Default is disabled
        assert processor.processing_interval == 300
        assert processor.batch_size == 1000
        assert processor.duckdb_writer is None
        assert processor.sqlite_reader is None

    def test_init_with_enabled_config(self):
        """Test initialization when analytics is enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("""
paths:
  database:
    telemetry_db: "{tmpdir}/telemetry.db"
    analytics_db: "{tmpdir}/analytics.duckdb"

analytics:
  enabled: true
  processing_interval: 60
  batch_size: 500
""".format(tmpdir=tmpdir))

            config = Config(config_dir=tmpdir)
            processor = AnalyticsProcessor(config=config)
            
            assert processor.enabled is True
            assert processor.processing_interval == 60
            assert processor.batch_size == 500
            assert processor.duckdb_writer is not None
            assert processor.sqlite_reader is not None

    def test_init_uses_unified_database_paths(self):
        """Test that processor uses paths.database section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("""
paths:
  database:
    telemetry_db: "{tmpdir}/telemetry.db"
    analytics_db: "{tmpdir}/analytics.duckdb"

analytics:
  enabled: true
""".format(tmpdir=tmpdir))

            config = Config(config_dir=tmpdir)
            processor = AnalyticsProcessor(config=config)
            
            # Verify paths are from unified database section
            # Both readers/writers are initialized when enabled
            assert processor.sqlite_reader is not None
            assert processor.duckdb_writer is not None
            # Verify SQLiteReader uses the correct path (stored as db_path)
            assert processor.sqlite_reader.db_path == Path(tmpdir) / "telemetry.db"

    def test_init_disabled_attributes_initialized(self):
        """Test that attributes are initialized even when disabled."""
        processor = AnalyticsProcessor()
        
        # Attributes should exist even when disabled
        assert processor.duckdb_writer is None
        assert processor.sqlite_reader is None
        assert processor.running is False
        assert processor._task is None
        
        # stop() should not raise AttributeError
        import asyncio
        async def test_stop():
            await processor.stop()  # Should not raise
        
        asyncio.run(test_stop())


class TestAnalyticsProcessorConfig:
    """Test configuration handling."""

    def test_config_fallback_to_defaults(self):
        """Test that missing config values use defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("""
paths:
  database:
    telemetry_db: "{tmpdir}/telemetry.db"
    analytics_db: "{tmpdir}/analytics.duckdb"
""".format(tmpdir=tmpdir))

            config = Config(config_dir=tmpdir)
            processor = AnalyticsProcessor(config=config)
            
            # Should use defaults when analytics section missing
            assert processor.enabled is False
            assert processor.processing_interval == 300
            assert processor.batch_size == 1000

    def test_config_invalid_analytics_section(self):
        """Test handling of invalid analytics config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("""
paths:
  database:
    telemetry_db: "{tmpdir}/telemetry.db"
    analytics_db: "{tmpdir}/analytics.duckdb"

analytics: "invalid"  # Not a dict
""".format(tmpdir=tmpdir))

            config = Config(config_dir=tmpdir)
            processor = AnalyticsProcessor(config=config)
            
            # Should fall back to defaults
            assert processor.enabled is False
            assert processor.processing_interval == 300
            assert processor.batch_size == 1000

