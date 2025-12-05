#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Uninstall script for Blueplane git commit tracking hooks.

Removes:
1. Global git template configuration
2. Hooks from specified repositories
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def get_template_dir() -> Path:
    """Get git template directory path."""
    return Path.home() / ".blueplane" / "git-templates"


def remove_global_template(dry_run: bool = False) -> bool:
    """
    Remove global git template configuration.

    Args:
        dry_run: If True, only show what would be done

    Returns:
        True if successful
    """
    template_dir = get_template_dir()

    print("Removing global git template...")

    # Unset git config
    if dry_run:
        print("   [DRY RUN] Would unset git config init.templatedir")
    else:
        try:
            subprocess.run([
                "git", "config", "--global",
                "--unset", "init.templatedir"
            ], check=False, capture_output=True)  # May fail if not set
            print("   Unset git config init.templatedir")
        except Exception as e:
            print(f"   Warning: Could not unset git config: {e}")

    # Remove template directory
    if template_dir.exists():
        if dry_run:
            print(f"   [DRY RUN] Would remove: {template_dir}")
        else:
            try:
                shutil.rmtree(template_dir)
                print(f"   Removed: {template_dir}")
            except Exception as e:
                print(f"   ERROR: Could not remove {template_dir}: {e}")
                return False

    return True


def remove_from_repo(repo_path: Path, dry_run: bool = False) -> bool:
    """
    Remove post-commit hook from a repository.

    Args:
        repo_path: Path to git repository root
        dry_run: If True, only show what would be done

    Returns:
        True if successful
    """
    hook_path = repo_path / ".git" / "hooks" / "post-commit"
    backup_path = hook_path.with_suffix(".backup")

    if not hook_path.exists():
        return True

    # Check if it's our hook
    try:
        with open(hook_path, 'r') as f:
            content = f.read()
    except Exception as e:
        print(f"   Warning: Could not read {hook_path}: {e}")
        return False

    if "Blueplane Telemetry" not in content:
        print(f"   Skipping {repo_path}: Not a Blueplane hook")
        return True

    if dry_run:
        print(f"   [DRY RUN] Would remove: {hook_path}")
        if backup_path.exists():
            print(f"   [DRY RUN] Would restore backup: {backup_path}")
        return True

    # Remove hook
    try:
        os.unlink(hook_path)
        print(f"   Removed: {hook_path}")
    except Exception as e:
        print(f"   ERROR: Could not remove {hook_path}: {e}")
        return False

    # Restore backup if exists
    if backup_path.exists():
        try:
            shutil.move(backup_path, hook_path)
            print(f"   Restored backup: {hook_path}")
        except Exception as e:
            print(f"   Warning: Could not restore backup: {e}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description='Uninstall Blueplane git commit tracking hooks'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--repos',
        nargs='+',
        help='Specific repositories to remove hooks from'
    )
    parser.add_argument(
        '--keep-global',
        action='store_true',
        help='Keep global template (only remove from specified repos)'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Blueplane Telemetry - Git Hook Uninstall")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN MODE] No changes will be made\n")

    success = True

    # Remove global template
    if not args.keep_global:
        if not remove_global_template(args.dry_run):
            success = False

    # Remove from specific repos
    if args.repos:
        print("\nRemoving hooks from repositories...")
        for repo in args.repos:
            if not remove_from_repo(Path(repo), args.dry_run):
                success = False

    print("\n" + "=" * 60)
    print("Uninstall completed!" if success else "Uninstall completed with errors!")
    print("=" * 60)

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
