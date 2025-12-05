#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Installation script for Blueplane git commit tracking.

Sets up:
1. Global git template directory with post-commit hook
2. Installs hook to existing git repositories (optional)

Features:
- Dry-run support
- Backup existing hooks before modifying
- 0o755 permissions on hook scripts
- Configuration deployed to ~/.blueplane/
"""

import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import List, Optional


def find_project_root() -> Path:
    """Find the project root directory."""
    return Path(__file__).parent.parent


def get_hook_source_path() -> Path:
    """Get path to hook source file."""
    return find_project_root() / "src" / "capture" / "git" / "hooks" / "post-commit"


def get_template_dir() -> Path:
    """Get git template directory path."""
    return Path.home() / ".blueplane" / "git-templates" / "hooks"


def setup_global_template(dry_run: bool = False) -> bool:
    """
    Set up global git template with post-commit hook.

    This ensures all new `git init` and `git clone` operations
    automatically get the hook installed.

    Args:
        dry_run: If True, only show what would be done

    Returns:
        True if successful
    """
    template_dir = get_template_dir()
    hook_source = get_hook_source_path()
    hook_dest = template_dir / "post-commit"

    print(f"Setting up global git template...")
    print(f"   Template directory: {template_dir}")

    if not hook_source.exists():
        print(f"   ERROR: Hook source not found: {hook_source}")
        return False

    if dry_run:
        print(f"   [DRY RUN] Would create: {template_dir}")
        print(f"   [DRY RUN] Would copy: {hook_source} -> {hook_dest}")
        print(f"   [DRY RUN] Would run: git config --global init.templatedir ...")
        return True

    # Create template directory
    template_dir.mkdir(parents=True, exist_ok=True)

    # Copy hook and make executable
    shutil.copy2(hook_source, hook_dest)
    os.chmod(hook_dest, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 0o755
    print(f"   Installed hook: {hook_dest}")

    # Set global git config
    try:
        subprocess.run([
            "git", "config", "--global",
            "init.templatedir", str(template_dir.parent)
        ], check=True, capture_output=True)
        print(f"   Configured git template directory")
    except subprocess.CalledProcessError as e:
        print(f"   ERROR: Failed to configure git: {e.stderr.decode()}")
        return False

    return True


def discover_git_repos(search_paths: Optional[List[str]] = None) -> List[Path]:
    """
    Discover git repositories in common locations.

    Default search paths:
    - ~/Dev
    - ~/dev
    - ~/Development
    - ~/Projects
    - ~/projects
    - ~/src
    - ~/code
    - ~/Code

    Args:
        search_paths: List of paths to search, or None for defaults

    Returns:
        List of git repository root paths
    """
    if search_paths is None:
        home = Path.home()
        search_paths = [
            home / "Dev",
            home / "dev",
            home / "Development",
            home / "Projects",
            home / "projects",
            home / "src",
            home / "code",
            home / "Code",
        ]
    else:
        search_paths = [Path(p) for p in search_paths]

    repos = []
    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Find .git directories (max depth 3)
        for git_dir in search_path.glob("**/.git"):
            if git_dir.is_dir():
                # Limit depth to avoid scanning too deep
                relative = git_dir.relative_to(search_path)
                if len(relative.parts) <= 4:  # .git counts as 1
                    repos.append(git_dir.parent)

    return repos


def install_to_repo(repo_path: Path, dry_run: bool = False, force: bool = False) -> bool:
    """
    Install post-commit hook to an existing repository.

    Args:
        repo_path: Path to git repository root
        dry_run: If True, only show what would be done
        force: If True, overwrite existing hooks

    Returns:
        True if successful
    """
    hooks_dir = repo_path / ".git" / "hooks"
    hook_dest = hooks_dir / "post-commit"
    hook_source = get_hook_source_path()

    if not hooks_dir.exists():
        print(f"   Skipping {repo_path}: No .git/hooks directory")
        return False

    # Check for existing hook
    if hook_dest.exists() and not force:
        # Check if it's our hook
        try:
            with open(hook_dest, 'r') as f:
                content = f.read()
            if "Blueplane Telemetry" in content:
                print(f"   Skipping {repo_path}: Hook already installed")
                return True
            else:
                print(f"   Skipping {repo_path}: Existing hook (use --force to overwrite)")
                return False
        except Exception as e:
            print(f"   Skipping {repo_path}: Could not read existing hook: {e}")
            return False

    if dry_run:
        print(f"   [DRY RUN] Would install hook to: {hook_dest}")
        return True

    # Backup existing hook if present
    if hook_dest.exists():
        backup = hook_dest.with_suffix(".backup")
        shutil.copy2(hook_dest, backup)
        print(f"   Backed up existing hook: {backup}")

    # Install hook
    try:
        shutil.copy2(hook_source, hook_dest)
        os.chmod(hook_dest, 0o755)
        print(f"   Installed hook: {hook_dest}")
        return True
    except Exception as e:
        print(f"   ERROR: Failed to install hook: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Install Blueplane git commit tracking hooks'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--skip-global',
        action='store_true',
        help='Skip global template setup'
    )
    parser.add_argument(
        '--install-existing',
        action='store_true',
        help='Install hooks to existing repositories'
    )
    parser.add_argument(
        '--search-paths',
        nargs='+',
        help='Paths to search for existing repos (default: ~/Dev, ~/dev, etc.)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite existing hooks'
    )
    parser.add_argument(
        '--repos',
        nargs='+',
        help='Specific repositories to install hooks to'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Blueplane Telemetry - Git Commit Tracking Installation")
    print("=" * 60)

    if args.dry_run:
        print("\n[DRY RUN MODE] No changes will be made\n")

    success = True

    # Setup global template
    if not args.skip_global:
        print("\n[1] Setting up global git template...")
        if not setup_global_template(args.dry_run):
            print("   Failed to setup global template")
            success = False
        else:
            print("   Done!\n")

    # Install to existing repos
    if args.install_existing or args.repos:
        print("[2] Installing to existing repositories...")

        if args.repos:
            repos = [Path(r) for r in args.repos]
        else:
            repos = discover_git_repos(args.search_paths)

        print(f"   Found {len(repos)} repositories\n")

        for repo in repos:
            install_to_repo(repo, args.dry_run, args.force)

        print("\n   Done!\n")

    print("=" * 60)
    print("Installation completed!" if success else "Installation completed with errors!")
    print("=" * 60)
    print("\nNext steps:")
    print("  1. Ensure telemetry server is running:")
    print("     python scripts/server_ctl.py start")
    print("")
    print("  2. New repositories will automatically get the hook")
    print("     via git template on `git init` or `git clone`")
    print("")
    print("  3. (Optional) Set custom server URL:")
    print("     export BLUEPLANE_SERVER_URL=http://127.0.0.1:8787")

    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
