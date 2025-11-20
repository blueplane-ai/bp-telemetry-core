#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Test script for Cursor Markdown Writer.

Tests the Markdown generation functionality.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path

from src.processing.cursor.markdown_writer import CursorMarkdownWriter, TRACE_RELEVANT_KEYS


def test_markdown_writer():
    """Test basic Markdown writing functionality."""
    
    print("Testing CursorMarkdownWriter...")
    print(f"TRACE_RELEVANT_KEYS: {TRACE_RELEVANT_KEYS}")
    print()
    
    # Create sample data
    sample_data = {
        'aiService.generations': json.dumps([
            {
                'unixMs': 1762046253035,
                'generationUUID': 'dd4317f0-22e0-4153-8f11-9b5aa5fc7946',
                'type': 'composer',
                'textDescription': 'Test generation'
            }
        ]).encode('utf-8'),
        'composer.composerData': json.dumps({
            'allComposers': [
                {
                    'composerId': 'test-composer-123',
                    'createdAt': 1762033584314,
                    'unifiedMode': 'agent',
                    'forceMode': 'edit',
                    'totalLinesAdded': 42,
                    'totalLinesRemoved': 5,
                    'isArchived': False
                }
            ]
        }).encode('utf-8'),
        'history.entries': json.dumps([
            {
                'editor': {
                    'resource': 'file:///home/user/test.py',
                    'forceFile': True
                }
            }
        ]).encode('utf-8')
    }
    
    # Create writer with temp output directory
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        writer = CursorMarkdownWriter(output_dir=output_dir)
        
        # Write markdown
        workspace_path = "/home/user/test-workspace"
        workspace_hash = "abc123def456"
        timestamp = datetime.now()
        
        filepath = writer.write_workspace_history(
            workspace_path,
            workspace_hash,
            sample_data,
            timestamp
        )
        
        print(f"✓ Markdown file written to: {filepath}")
        print()
        
        # Read and display content
        content = filepath.read_text(encoding='utf-8')
        print("Generated Markdown Content:")
        print("=" * 80)
        print(content)
        print("=" * 80)
        print()
        
        # Verify file exists and has content
        assert filepath.exists(), "Markdown file should exist"
        assert len(content) > 100, "Markdown content should be substantial"
        assert workspace_hash in content, "Workspace hash should be in content"
        assert "Composer Sessions" in content, "Should contain composer section"
        
        print("✓ All tests passed!")


if __name__ == "__main__":
    test_markdown_writer()
