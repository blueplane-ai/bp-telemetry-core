#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Test script for DuckDB Writer stub.

Tests that the DuckDB writer can be initialized and schema created.
"""

import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from processing.cursor.duckdb_writer import CursorDuckDBWriter, DUCKDB_AVAILABLE


def test_duckdb_writer():
    """Test DuckDB writer initialization."""
    
    print("Testing CursorDuckDBWriter...")
    
    if not DUCKDB_AVAILABLE:
        print("⚠ DuckDB not available - skipping test")
        print("Install with: pip install duckdb>=0.9.0")
        return
    
    print("✓ DuckDB is available")
    print()
    
    # Create writer with temp database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_history.duckdb"
        
        writer = CursorDuckDBWriter(database_path=db_path)
        print(f"✓ Writer created: {db_path}")
        
        # Connect and create schema
        writer.connect()
        print("✓ Connected to DuckDB")
        print("✓ Schema created")
        
        # Test writing a snapshot
        workspace_hash = "test123"
        workspace_path = "/home/user/test-workspace"
        data = {}
        data_hash = "abc123"
        timestamp = datetime.now()
        
        snapshot_id = writer.write_workspace_history(
            workspace_hash,
            workspace_path,
            data,
            data_hash,
            timestamp
        )
        
        print(f"✓ Wrote snapshot: {snapshot_id}")
        
        # Close connection
        writer.close()
        print("✓ Connection closed")
        
        # Verify database file was created
        assert db_path.exists(), "Database file should exist"
        print(f"✓ Database file created: {db_path.stat().st_size} bytes")
    
    print()
    print("✓ All DuckDB tests passed!")


if __name__ == "__main__":
    test_duckdb_writer()
