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
    markdown_config = config.get_cursor_config("markdown_monitor")
    print("Markdown Monitor Config:")
    for key, value in markdown_config.items():
        print(f"  {key}: {value}")
    print()
    
    # Test cursor database monitor config
    db_config = config.get_cursor_config("database_monitor")
    print("Database Monitor Config:")
    for key, value in db_config.items():
        print(f"  {key}: {value}")
    print()
    
    # Test DuckDB config
    duckdb_config = config.get_cursor_config("duckdb_sink")
    print("DuckDB Sink Config:")
    for key, value in duckdb_config.items():
        print(f"  {key}: {value}")
    print()
    
    # Test get method
    enabled = config.get("cursor.markdown_monitor.enabled", True)
    print(f"Markdown monitoring enabled (via get): {enabled}")
    
    debounce = config.get("cursor.markdown_monitor.debounce_delay_seconds", 10)
    print(f"Debounce delay (via get): {debounce}s")
    
    print()
    print("✓ Configuration loading successful!")

if __name__ == "__main__":
    test_config()
