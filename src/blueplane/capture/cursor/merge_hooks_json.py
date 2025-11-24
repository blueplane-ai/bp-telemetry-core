#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Utility to merge hooks.json files.

Merges Blueplane hooks configuration with existing hooks.json,
preserving existing hooks and appending Blueplane hooks.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List


def generate_hooks_json(hooks_dir: Path) -> Dict[str, Any]:
    """
    Generate hooks.json configuration from hook files.
    
    Note: This function now returns an empty hooks configuration since we
    only listen for extension session_start and session_end events, which
    are sent directly to Redis and don't require hooks.
    
    Args:
        hooks_dir: Directory containing hook Python files
        
    Returns:
        Dictionary representing hooks.json structure (empty hooks dict)
    """
    # Return empty hooks configuration - we no longer install hooks
    # The extension sends session_start and session_end events directly to Redis
    return {
        "$schema": "https://cursor.sh/hooks-schema.json",
        "version": 1,
        "description": "Blueplane Telemetry Core - Cursor Extension Events Only (no hooks)",
        "hooks": {}
    }


def load_hooks_json(file_path: Path) -> Dict[str, Any]:
    """
    Load hooks.json file, returning empty structure if not found.
    
    Args:
        file_path: Path to hooks.json file
        
    Returns:
        Dictionary representing hooks.json structure
    """
    if not file_path.exists():
        return {
            "$schema": "https://cursor.sh/hooks-schema.json",
            "version": 1,
            "hooks": {}
        }
    
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"⚠️  Warning: Could not read {file_path}: {e}", file=sys.stderr)
        return {
            "$schema": "https://cursor.sh/hooks-schema.json",
            "version": 1,
            "hooks": {}
        }


def merge_hooks(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two hooks.json configurations.
    
    Preserves existing hooks and appends new hooks. If a hook type already exists,
    the new hooks are appended to the existing array.
    
    Args:
        existing: Existing hooks.json configuration
        new: New hooks.json configuration to merge in
        
    Returns:
        Merged hooks.json configuration
    """
    # Start with existing config, preserving metadata
    merged = existing.copy()
    
    # Ensure hooks key exists
    if "hooks" not in merged:
        merged["hooks"] = {}
    
    if "hooks" not in new:
        return merged
    
    # Merge each hook type
    for hook_type, new_hooks in new["hooks"].items():
        if hook_type not in merged["hooks"]:
            # New hook type, just add it
            merged["hooks"][hook_type] = new_hooks.copy()
        else:
            # Existing hook type, append new hooks
            existing_hooks = merged["hooks"][hook_type]
            if not isinstance(existing_hooks, list):
                existing_hooks = [existing_hooks]
            
            # Check for duplicates based on command
            existing_commands = {hook.get("command") for hook in existing_hooks if isinstance(hook, dict)}
            
            for new_hook in new_hooks:
                if isinstance(new_hook, dict):
                    command = new_hook.get("command")
                    if command not in existing_commands:
                        existing_hooks.append(new_hook.copy())
                        existing_commands.add(command)
                else:
                    existing_hooks.append(new_hook)
            
            merged["hooks"][hook_type] = existing_hooks
    
    return merged


def save_hooks_json(file_path: Path, config: Dict[str, Any]) -> None:
    """
    Save hooks.json configuration to file.
    
    Args:
        file_path: Path to save hooks.json
        config: Configuration dictionary
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        json.dump(config, f, indent=2)


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: merge_hooks_json.py <hooks_dir> <target_hooks_json>", file=sys.stderr)
        print("  hooks_dir: Directory containing hook Python files", file=sys.stderr)
        print("  target_hooks_json: Path to hooks.json file to merge into", file=sys.stderr)
        sys.exit(1)
    
    hooks_dir = Path(sys.argv[1])
    target_json = Path(sys.argv[2])
    
    if not hooks_dir.exists():
        print(f"❌ Error: Hooks directory not found: {hooks_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Generate hooks.json from hook files
    new_config = generate_hooks_json(hooks_dir)
    
    # Load existing hooks.json if it exists
    existing_config = load_hooks_json(target_json)
    
    # Merge configurations
    merged_config = merge_hooks(existing_config, new_config)
    
    # Save merged configuration
    save_hooks_json(target_json, merged_config)
    
    print(f"✅ Merged hooks configuration into {target_json}")


if __name__ == '__main__':
    main()

