# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""DuckDB test fixtures for analytics service tests."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import tempfile

import pytest

try:
    import duckdb
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    duckdb = None


@pytest.fixture
def temp_duckdb():
    """Create temporary DuckDB database for testing."""
    if not DUCKDB_AVAILABLE:
        pytest.skip("DuckDB not available")
    
    db_dir = tempfile.mkdtemp()
    db_path = Path(db_dir) / "test_analytics.duckdb"
    
    # Create connection
    conn = duckdb.connect(str(db_path))
    
    yield str(db_path), conn
    
    # Cleanup
    conn.close()
    import shutil
    shutil.rmtree(db_dir)


def verify_duckdb_schema(conn):
    """Verify DuckDB schema exists and return table names."""
    tables = conn.execute("SHOW TABLES").fetchall()
    table_names = [row[0] for row in tables]
    
    expected_tables = [
        'workspaces',
        'ai_generations',
        'composer_sessions',
        'file_history',
        'raw_traces'
    ]
    
    return all(table in table_names for table in expected_tables)

