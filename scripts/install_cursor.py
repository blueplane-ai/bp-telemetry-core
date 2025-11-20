#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
DEPRECATED: This script is deprecated and no longer maintained.

Cursor hooks have been removed from the telemetry lifecycle. Cursor now uses
extension-based capture only. See README.md for current installation instructions.

Installation script for Cursor telemetry capture.

Installs hooks globally to ~/.cursor/hooks/ for all Cursor workspaces.
"""

import sys
import os
import shutil
import subprocess
import argparse
from pathlib import Path


def find_project_root() -> Path:
    """Find the project root directory."""
    current = Path(__file__).parent.parent
    return current


def install_hooks(source_path: Path) -> bool:
    """
    Install hooks globally to ~/.cursor/hooks/.

    Args:
        source_path: Source directory containing hooks

    Returns:
        True if successful, False otherwise
    """
    try:
        # Use the bash script for installation
        install_script = source_path / "src" / "capture" / "cursor" / "install_global_hooks.sh"
        
        if not install_script.exists():
            print(f"❌ Installation script not found: {install_script}")
            return False

        print(f"📦 Installing global hooks using {install_script.name}")
        
        # Make script executable and run it
        os.chmod(install_script, 0o755)
        result = subprocess.run(
            [str(install_script)],
            cwd=install_script.parent,
            capture_output=False
        )

        if result.returncode == 0:
            print(f"   ✅ Global hooks installed successfully")
            return True
        else:
            print(f"   ❌ Installation script failed with exit code {result.returncode}")
            return False

    except Exception as e:
        print(f"❌ Failed to install hooks: {e}")
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
        description='Install Cursor telemetry capture (global hooks)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without doing it'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Blueplane Telemetry - Cursor Global Hooks Installation")
    print("=" * 60)

    if args.dry_run:
        print("🔍 DRY RUN MODE - No changes will be made\n")

    # Find source directory
    source_path = find_project_root()
    print(f"\n📂 Source: {source_path}")

    if args.dry_run:
        print("\nWould install:")
        print("  - Global hooks to ~/.cursor/hooks/")
        print("  - Configuration to ~/.blueplane/")
        print("\nRun without --dry-run to proceed")
        return 0

    # Install hooks
    print("\n📦 Installing global hooks...")
    if not install_hooks(source_path):
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
    print("     pip install redis pyyaml")
    print("  2. Start Redis server:")
    print("     redis-server")
    print("  3. Initialize Redis streams:")
    print("     python scripts/init_redis.py")
    print("  4. (Optional) Install Cursor extension for database monitoring")
    print("\n💡 Verify installation:")
    print("     # verify_installation.py is deprecated - use manual checks:")
    print("     # - Check extension status in Cursor")
    print("     # - Check processing server: ps aux | grep start_server.py")
    print("     # - Monitor Redis: redis-cli PING && redis-cli XLEN telemetry:events")
    print("\n📝 Note: This script is DEPRECATED - hooks have been removed")

    return 0


if __name__ == '__main__':
    sys.exit(main())
