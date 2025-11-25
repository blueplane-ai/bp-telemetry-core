#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Test script for DuckDB Analytics Pipeline.

Tests the DuckDB writer with sample data to verify:
- Data extraction from ItemTable format
- Insertion into analytics tables
- Query functions
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.processing.cursor.duckdb_writer import (
    CursorDuckDBWriter,
    query_workspace_activity,
    query_ai_generations,
    query_composer_sessions,
    DUCKDB_AVAILABLE
)


def create_sample_data():
    """Create sample ItemTable data for testing."""
    return {
        'aiService.generations': [
            {
                'generationUUID': 'gen-001',
                'unixMs': int(datetime.now().timestamp() * 1000) - 3600000,  # 1 hour ago
                'type': 'code_completion',
                'textDescription': 'Added function to process user input'
            },
            {
                'generationUUID': 'gen-002',
                'unixMs': int(datetime.now().timestamp() * 1000) - 1800000,  # 30 min ago
                'type': 'refactor',
                'textDescription': 'Refactored database queries'
            }
        ],
        'composer.composerData': {
            'allComposers': [
                {
                    'composerId': 'composer-001',
                    'createdAt': int(datetime.now().timestamp() * 1000) - 7200000,  # 2 hours ago
                    'unifiedMode': 'chat',
                    'forceMode': 'none',
                    'totalLinesAdded': 45,
                    'totalLinesRemoved': 12,
                    'isArchived': False
                },
                {
                    'composerId': 'composer-002',
                    'createdAt': int(datetime.now().timestamp() * 1000) - 5400000,  # 1.5 hours ago
                    'unifiedMode': 'edit',
                    'forceMode': 'accept',
                    'totalLinesAdded': 23,
                    'totalLinesRemoved': 8,
                    'isArchived': True
                }
            ]
        },
        'history.entries': [
            {
                'uri': '/path/to/file1.py',
                'timestamp': int(datetime.now().timestamp() * 1000) - 900000  # 15 min ago
            },
            {
                'uri': '/path/to/file2.ts',
                'timestamp': int(datetime.now().timestamp() * 1000) - 600000  # 10 min ago
            }
        ]
    }


def main():
    """Run DuckDB analytics tests."""
    if not DUCKDB_AVAILABLE:
        print("❌ DuckDB not available - install with: pip install duckdb>=0.9.0")
        return 1
    
    print("Testing DuckDB Analytics Pipeline")
    print("=" * 50)
    
    # Create test database
    test_db = Path("/tmp/test_cursor_history.duckdb")
    if test_db.exists():
        test_db.unlink()  # Remove existing test database
    
    try:
        # Initialize writer
        print("\n1. Initializing DuckDB writer...")
        writer = CursorDuckDBWriter(database_path=test_db)
        writer.connect()
        print("   ✓ Connected to DuckDB")
        
        # Create sample data
        print("\n2. Creating sample workspace data...")
        workspace_hash = "test-workspace-123"
        workspace_path = "/test/workspace"
        sample_data = create_sample_data()
        data_hash = "test-hash-123"
        timestamp = datetime.now()
        
        # Write workspace history
        print("\n3. Writing workspace history to DuckDB...")
        snapshot_id = writer.write_workspace_history(
            workspace_hash=workspace_hash,
            workspace_path=workspace_path,
            data=sample_data,
            data_hash=data_hash,
            timestamp=timestamp
        )
        print(f"   ✓ Created snapshot: {snapshot_id}")
        
        # Test queries
        print("\n4. Testing analytics queries...")
        
        # Query workspace activity
        activity = query_workspace_activity(test_db, workspace_hash)
        print(f"   ✓ Workspace activity query: {len(activity)} snapshot(s)")
        if activity:
            print(f"      - Snapshot: {activity[0]['snapshot_id']}")
            print(f"      - Generations: {activity[0]['generation_count']}")
            print(f"      - Composer sessions: {activity[0]['composer_session_count']}")
            print(f"      - Files: {activity[0]['file_count']}")
            print(f"      - Lines added: {activity[0]['total_lines_added']}")
            print(f"      - Lines removed: {activity[0]['total_lines_removed']}")
        
        # Query AI generations
        generations = query_ai_generations(test_db, workspace_hash, limit=10)
        print(f"   ✓ AI generations query: {len(generations)} generation(s)")
        if generations:
            print(f"      - Latest: {generations[0]['generation_type']} at {generations[0]['generation_time']}")
        
        # Query composer sessions
        sessions = query_composer_sessions(test_db, workspace_hash, limit=10)
        print(f"   ✓ Composer sessions query: {len(sessions)} session(s)")
        if sessions:
            print(f"      - Latest: {sessions[0]['composer_id']} ({sessions[0]['unified_mode']})")
        
        # Cleanup
        writer.close()
        print("\n5. All tests passed! ✓")
        print(f"\nTest database: {test_db}")
        print("You can inspect it with: duckdb /tmp/test_cursor_history.duckdb")
        
        return 0
    
    except Exception as e:
        print(f"\n❌ Test failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        # Cleanup test database
        if test_db.exists():
            test_db.unlink()


if __name__ == "__main__":
    sys.exit(main())

