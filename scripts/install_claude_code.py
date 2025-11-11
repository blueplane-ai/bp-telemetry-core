#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Installation script for Claude Code telemetry capture.

Copies hooks to ~/.claude/hooks/telemetry/ and updates settings.json.
"""

import sys
import os
import shutil
import json
import argparse
from pathlib import Path


def find_project_root() -> Path:
    """Find the project root directory."""
    current = Path(__file__).parent.parent
    return current


def install_hooks(source_path: Path) -> bool:
    """
    Install hooks to ~/.claude/hooks/telemetry/ directory.

    Args:
        source_path: Source directory containing hooks

    Returns:
        True if successful, False otherwise
    """
    try:
        # Create ~/.claude/hooks/telemetry directory
        claude_dir = Path.home() / ".claude"
        hooks_dir = claude_dir / "hooks" / "telemetry"
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # Copy hook scripts
        source_hooks = source_path / "src" / "capture" / "claude_code" / "hooks"
        if not source_hooks.exists():
            print(f"❌ Source hooks directory not found: {source_hooks}")
            return False

        print(f"📦 Copying hooks from {source_hooks} to {hooks_dir}")

        # Copy all Python hook files
        hook_files = [
            "session_start.py",
            "session_end.py",
            "user_prompt_submit.py",
            "pre_tool_use.py",
            "post_tool_use.py",
            "pre_compact.py",
            "stop.py",
        ]

        for hook_file in hook_files:
            source_file = source_hooks / hook_file
            if source_file.exists():
                dest = hooks_dir / hook_file
                shutil.copy2(source_file, dest)
                # Make executable
                os.chmod(dest, 0o755)
                print(f"   ✅ {hook_file}")
            else:
                print(f"   ⚠️  {hook_file} not found")

        # Copy hook_base.py to parent directory
        hook_base = source_hooks.parent / "hook_base.py"
        if hook_base.exists():
            shutil.copy2(hook_base, hooks_dir.parent / "hook_base.py")
            print(f"   ✅ hook_base.py")

        # Copy __init__.py files
        init_file = source_hooks / "__init__.py"
        if init_file.exists():
            shutil.copy2(init_file, hooks_dir / "__init__.py")

        parent_init = source_hooks.parent / "__init__.py"
        if parent_init.exists():
            shutil.copy2(parent_init, hooks_dir.parent / "__init__.py")

        # Copy capture package (for imports)
        capture_init = source_path / "src" / "capture" / "__init__.py"
        if capture_init.exists():
            capture_dir = hooks_dir.parent.parent / "capture"
            capture_dir.mkdir(exist_ok=True)
            shutil.copy2(capture_init, capture_dir / "__init__.py")

        # Copy shared modules
        shared_dir = source_path / "src" / "capture" / "shared"
        if shared_dir.exists():
            target_shared = hooks_dir.parent / "shared"
            if target_shared.exists():
                shutil.rmtree(target_shared)
            shutil.copytree(shared_dir, target_shared)
            print(f"   ✅ shared/ (modules)")

        return True

    except Exception as e:
        print(f"❌ Failed to install hooks: {e}")
        import traceback
        traceback.print_exc()
        return False


def update_settings_json(hooks_dir: Path, backup: bool = True) -> bool:
    """
    Update ~/.claude/settings.json with hook configuration.

    Properly merges with existing hooks instead of overwriting them.

    Args:
        hooks_dir: Path to hooks directory
        backup: Whether to backup existing settings.json

    Returns:
        True if successful, False otherwise
    """
    try:
        settings_file = Path.home() / ".claude" / "settings.json"

        # Load existing settings or create new
        if settings_file.exists():
            if backup:
                backup_file = settings_file.parent / "settings.json.backup"
                shutil.copy2(settings_file, backup_file)
                print(f"   💾 Backed up to {backup_file}")

            with open(settings_file, 'r') as f:
                settings = json.load(f)
        else:
            settings = {}

        # Ensure hooks section exists
        if "hooks" not in settings:
            settings["hooks"] = {}

        # Define hook configuration
        hook_configs = {
            "SessionStart": "session_start.py",
            "SessionEnd": "session_end.py",  # Session end (when Claude Code closes)
            "UserPromptSubmit": "user_prompt_submit.py",
            "PreToolUse": "pre_tool_use.py",
            "PostToolUse": "post_tool_use.py",
            "PreCompact": "pre_compact.py",
            "Stop": "stop.py",  # End of turn (when assistant stops responding)
        }

        # Merge each hook (don't overwrite existing hooks)
        for hook_name, script_name in hook_configs.items():
            hook_path = hooks_dir / script_name
            if not hook_path.exists():
                continue

            new_hook = {
                "type": "command",
                "command": str(hook_path)
            }

            # Check if this hook type already exists
            if hook_name in settings["hooks"]:
                # Hook type exists - merge with existing matchers
                existing_matchers = settings["hooks"][hook_name]

                # Find matcher with empty string ""
                empty_matcher_found = False
                for matcher_entry in existing_matchers:
                    if matcher_entry.get("matcher") == "":
                        # Found empty matcher - check if our hook is already present
                        hooks_list = matcher_entry.get("hooks", [])

                        # Check for duplicate
                        is_duplicate = any(
                            h.get("command") == new_hook["command"]
                            for h in hooks_list
                        )

                        if not is_duplicate:
                            # Append our hook to existing hooks
                            hooks_list.append(new_hook)
                            matcher_entry["hooks"] = hooks_list
                            print(f"   ✅ Merged {hook_name} (added to existing hooks)")
                        else:
                            print(f"   ⏭️  {hook_name} (already configured)")

                        empty_matcher_found = True
                        break

                if not empty_matcher_found:
                    # No empty matcher found - add new matcher entry
                    existing_matchers.append({
                        "matcher": "",
                        "hooks": [new_hook]
                    })
                    print(f"   ✅ Merged {hook_name} (added new matcher)")
            else:
                # Hook type doesn't exist - create it
                settings["hooks"][hook_name] = [
                    {
                        "matcher": "",
                        "hooks": [new_hook]
                    }
                ]
                print(f"   ✅ Registered {hook_name}")

        # Write updated settings
        with open(settings_file, 'w') as f:
            json.dump(settings, f, indent=4)

        print(f"\n✅ Updated {settings_file}")
        return True

    except Exception as e:
        print(f"❌ Failed to update settings.json: {e}")
        import traceback
        traceback.print_exc()
        return False


def install_config(source_path: Path) -> bool:
    """
    Install configuration files.

    Args:
        source_path: Source directory containing config

    Returns:
        True if successful, False otherwise
    """
    try:
        # Create .blueplane directory in home
        blueplane_dir = Path.home() / ".blueplane"
        blueplane_dir.mkdir(exist_ok=True)

        # Copy config files
        config_source = source_path / "config"
        if config_source.exists():
            for config_file in config_source.glob("*.yaml"):
                dest = blueplane_dir / config_file.name
                if not dest.exists():  # Don't overwrite existing config
                    shutil.copy2(config_file, dest)
                    print(f"   ✅ {config_file.name}")
                else:
                    print(f"   ⏭️  {config_file.name} (already exists)")

        return True

    except Exception as e:
        print(f"❌ Failed to install config: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Install Claude Code telemetry capture'
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

    args = parser.parse_args()

    print("=" * 60)
    print("Blueplane Telemetry - Claude Code Installation")
    print("=" * 60)

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")

    # Find source directory
    source_path = find_project_root()
    print(f"\n📂 Source: {source_path}")
    print(f"📂 Target: ~/.claude/hooks/telemetry/\n")

    if args.dry_run:
        print("Would install:")
        print("  - Hooks to ~/.claude/hooks/telemetry/")
        print("  - Update ~/.claude/settings.json")
        print("  - Configuration to ~/.blueplane/")
        print("\nRun without --dry-run to proceed")
        return 0

    # Install hooks
    print("📦 Installing hooks...")
    if not install_hooks(source_path):
        return 1

    # Update settings.json
    print("\n⚙️  Updating settings.json...")
    hooks_dir = Path.home() / ".claude" / "hooks" / "telemetry"
    if not update_settings_json(hooks_dir, backup=not args.no_backup):
        return 1

    # Install configuration
    print("\n⚙️  Installing configuration...")
    if not install_config(source_path):
        return 1

    print("\n" + "=" * 60)
    print("✅ Installation completed successfully!")
    print("=" * 60)

    print("\n📋 Next steps:")
    print("  1. Install Python dependencies:")
    print("     pip install redis pyyaml aiosqlite")
    print("  2. Start Redis server:")
    print("     redis-server")
    print("  3. Initialize Redis streams:")
    print("     python scripts/init_redis.py")
    print("  4. Start processing server:")
    print("     python scripts/start_server.py")
    print("\n💡 Check your hooks configuration:")
    print("     cat ~/.claude/settings.json")
    print("\n💡 Hooks will fire automatically in your next Claude Code session!")

    return 0


if __name__ == '__main__':
    sys.exit(main())
