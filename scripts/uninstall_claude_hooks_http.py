#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Uninstall script for Claude Code telemetry capture (HTTP-based hooks).

Removes HTTP hooks from ~/.claude/hooks/telemetry/ and updates settings.json.
"""

import sys
import shutil
import json
import argparse
from pathlib import Path


def remove_hook_from_settings(settings: dict, hook_name: str, hook_path: str) -> bool:
    """
    Remove a specific hook from settings.

    Matches both absolute and relative paths to the hook script.

    Args:
        settings: Settings dictionary
        hook_name: Hook name (e.g., "SessionStart")
        hook_path: Path to hook script (absolute)

    Returns:
        True if hook was removed, False if not found
    """
    if "hooks" not in settings:
        return False

    if hook_name not in settings["hooks"]:
        return False

    hook_removed = False
    matchers = settings["hooks"][hook_name]

    # Get the script filename for matching
    script_name = Path(hook_path).name

    # Iterate through matchers and remove matching hooks
    for matcher_entry in matchers:
        if "hooks" not in matcher_entry:
            continue

        hooks_list = matcher_entry["hooks"]
        original_len = len(hooks_list)

        # Filter out hooks matching the path (absolute, relative, or just filename)
        hooks_list[:] = [
            h for h in hooks_list
            if not (
                h.get("command") == hook_path or  # Exact match
                h.get("command", "").endswith(f"telemetry/{script_name}") or  # Path ends with telemetry/script
                h.get("command", "") == f".claude/hooks/telemetry/{script_name}"  # Relative path
            )
        ]

        if len(hooks_list) < original_len:
            hook_removed = True

    # Clean up empty matchers
    settings["hooks"][hook_name] = [
        m for m in matchers
        if m.get("hooks")  # Keep only matchers with hooks
    ]

    # Remove hook type if no matchers left
    if not settings["hooks"][hook_name]:
        del settings["hooks"][hook_name]
        hook_removed = True

    return hook_removed


def uninstall_hooks(force: bool = False) -> bool:
    """
    Uninstall HTTP-based hooks from ~/.claude/hooks/telemetry/ directory.

    Args:
        force: If True, remove directory even if files remain

    Returns:
        True if successful, False otherwise
    """
    try:
        hooks_dir = Path.home() / ".claude" / "hooks" / "telemetry"

        if not hooks_dir.exists():
            print("ℹ️  No hooks directory found")
            return True

        print(f"🗑️  Removing HTTP hooks from {hooks_dir}")

        # List of HTTP hooks to remove
        hook_files = [
            "session_start.py",
            "session_end.py",
            "__init__.py",
        ]

        removed_count = 0
        for hook_file in hook_files:
            hook_path = hooks_dir / hook_file
            if hook_path.exists():
                hook_path.unlink()
                print(f"   ✅ Removed {hook_file}")
                removed_count += 1

        # Remove hook_base_http.py from parent directory
        hook_base_http = hooks_dir.parent / "hook_base_http.py"
        if hook_base_http.exists():
            hook_base_http.unlink()
            print(f"   ✅ Removed hook_base_http.py")
            removed_count += 1

        # Remove __init__.py from parent directory
        parent_init = hooks_dir.parent / "__init__.py"
        if parent_init.exists():
            parent_init.unlink()
            print(f"   ✅ Removed __init__.py")
            removed_count += 1

        # Try to remove telemetry directory if empty
        try:
            if not any(hooks_dir.iterdir()) or force:
                hooks_dir.rmdir()
                print(f"   ✅ Removed {hooks_dir}")
        except OSError:
            if force:
                shutil.rmtree(hooks_dir)
                print(f"   ✅ Force removed {hooks_dir}")
            else:
                print(f"   ⚠️  {hooks_dir} not empty, use --force to remove")

        if removed_count == 0:
            print("   ℹ️  No HTTP hook files found to remove")

        return True

    except Exception as e:
        print(f"❌ Failed to uninstall hooks: {e}")
        import traceback
        traceback.print_exc()
        return False


def update_settings_json(backup: bool = True) -> bool:
    """
    Remove HTTP hook configuration from ~/.claude/settings.json.

    Args:
        backup: Whether to backup existing settings.json

    Returns:
        True if successful, False otherwise
    """
    try:
        settings_file = Path.home() / ".claude" / "settings.json"

        if not settings_file.exists():
            print("   ℹ️  settings.json not found")
            return True

        # Load existing settings
        with open(settings_file, 'r') as f:
            settings = json.load(f)

        # Backup if requested
        if backup:
            backup_file = settings_file.parent / "settings.json.backup"
            shutil.copy2(settings_file, backup_file)
            print(f"   💾 Backed up to {backup_file}")

        # Remove HTTP hooks
        hooks_dir = Path.home() / ".claude" / "hooks" / "telemetry"
        hook_configs = {
            "SessionStart": "session_start.py",
            "SessionEnd": "session_end.py",
        }

        removed_count = 0
        for hook_name, script_name in hook_configs.items():
            hook_path = str(hooks_dir / script_name)
            if remove_hook_from_settings(settings, hook_name, hook_path):
                print(f"   ✅ Removed {hook_name} from settings")
                removed_count += 1

        # Write updated settings
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=4)

        if removed_count == 0:
            print("   ℹ️  No HTTP hooks found in settings.json")
        else:
            print(f"\n✅ Updated {settings_file}")

        return True

    except Exception as e:
        print(f"❌ Failed to update settings.json: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Uninstall Claude Code telemetry capture (HTTP-based hooks)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without doing it'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip backup of existing settings.json'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Force remove directories even if not empty'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Blueplane Telemetry - Claude Code Uninstall (HTTP hooks)")
    print("=" * 60)

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")

    hooks_dir = Path.home() / ".claude" / "hooks" / "telemetry"
    print(f"\n📂 Target: {hooks_dir}\n")

    if args.dry_run:
        print("Would remove:")
        print("  - HTTP hooks from ~/.claude/hooks/telemetry/")
        print("  - Hook entries from ~/.claude/settings.json")
        print("\nRun without --dry-run to proceed")
        return 0

    # Remove hooks
    print("🗑️  Uninstalling HTTP hooks...")
    if not uninstall_hooks(force=args.force):
        return 1

    # Update settings.json
    print("\n⚙️  Updating settings.json...")
    if not update_settings_json(backup=not args.no_backup):
        return 1

    print("\n" + "=" * 60)
    print("✅ Uninstall completed successfully!")
    print("=" * 60)

    print("\n💡 HTTP-based hooks have been removed.")
    print("   To install Redis-based hooks:")
    print("     python scripts/install_claude_hooks.py")

    return 0


if __name__ == '__main__':
    sys.exit(main())
