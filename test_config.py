#!/usr/bin/env python3
# Test script for configuration loading

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from capture.shared.config import Config

def test_config():
    """Test configuration loading."""
    print("Testing configuration loading...")
    
    # Load config
    config = Config()
    
    print(f"Config dir: {config.config_dir}")
    print()
    
    # Test cursor markdown monitor config
    markdown_config = config.get_monitoring_config("cursor_markdown")
    print("Cursor Markdown Monitor Config:")
    for key, value in markdown_config.items():
        print(f"  {key}: {value}")
    print()

    # Test cursor database monitor config
    db_config = config.get_monitoring_config("cursor_database")
    print("Cursor Database Monitor Config:")
    for key, value in db_config.items():
        print(f"  {key}: {value}")
    print()

    # Test DuckDB feature flag
    duckdb_config = config.get("features.duckdb_sink", {})
    print("DuckDB Sink Feature Config:")
    for key, value in duckdb_config.items():
        print(f"  {key}: {value}")
    print()

    # Test get method with correct schema paths
    poll_interval = config.get("monitoring.cursor_markdown.poll_interval", 120.0)
    print(f"Markdown poll interval (via get): {poll_interval}s")

    debounce = config.get("monitoring.cursor_markdown.debounce_delay", 10.0)
    print(f"Debounce delay (via get): {debounce}s")
    
    print()
    print("✓ Configuration loading successful!")

if __name__ == "__main__":
    test_config()
