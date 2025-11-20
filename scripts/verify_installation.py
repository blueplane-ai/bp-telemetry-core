#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
DEPRECATED: This script is deprecated and no longer maintained.

This script was designed to verify Cursor hooks installation, which has been
removed from the telemetry lifecycle. Cursor now uses extension-based capture
only, and verification should be done manually by checking:
- Extension is installed and active in Cursor
- Processing server is running
- Redis is accessible
- Database monitor is functioning

For troubleshooting, see docs/TROUBLESHOOTING.md

Verification script for Blueplane Telemetry installation.

Checks that all components are installed and configured correctly.
"""

import sys
import os
from pathlib import Path
import argparse

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def check_python_dependencies() -> bool:
    """Check Python dependencies are installed."""
    print("\n🐍 Checking Python dependencies...")

    required = {
        'redis': 'Redis client library',
        'yaml': 'YAML parser (pyyaml)',
    }

    all_installed = True
    for module, description in required.items():
        try:
            __import__(module)
            print(f"   ✅ {module} ({description})")
        except ImportError:
            print(f"   ❌ {module} ({description}) - Not installed")
            all_installed = False

    return all_installed


def check_redis_connection() -> bool:
    """Check Redis is running and accessible."""
    print("\n🔴 Checking Redis connection...")

    try:
        import redis
        client = redis.Redis(host='localhost', port=6379, socket_timeout=2)
        client.ping()
        print(f"   ✅ Connected to Redis at localhost:6379")

        # Check streams
        try:
            info = client.xinfo_stream('telemetry:events')
            print(f"   ✅ Stream 'telemetry:events' exists")
        except:
            print(f"   ⚠️  Stream 'telemetry:events' not found (run init_redis.py)")

        try:
            groups = client.xinfo_groups('telemetry:events')
            print(f"   ✅ Consumer groups configured")
        except:
            print(f"   ⚠️  Consumer groups not found (run init_redis.py)")

        return True

    except ImportError:
        print(f"   ❌ Redis library not installed")
        return False
    except Exception as e:
        print(f"   ❌ Cannot connect to Redis: {e}")
        print(f"   💡 Start Redis with: redis-server")
        return False


def check_hooks_installation() -> bool:
    """Check global hooks are installed."""
    print(f"\n🪝 Checking global hooks installation...")

    hooks_dir = Path.home() / ".cursor" / "hooks"
    if not hooks_dir.exists():
        print(f"   ❌ Global hooks directory not found: {hooks_dir}")
        print(f"   💡 Run: python scripts/install_cursor.py")
        return False

    print(f"   ✅ Global hooks directory exists: {hooks_dir}")

    # Check for hook files
    expected_hooks = [
        'before_submit_prompt.py',
        'after_agent_response.py',
        'after_file_edit.py',
        'before_mcp_execution.py',
        'after_mcp_execution.py',
        'before_shell_execution.py',
        'after_shell_execution.py',
        'before_read_file.py',
        'stop.py',
    ]

    all_found = True
    for hook in expected_hooks:
        hook_path = hooks_dir / hook
        if hook_path.exists() and os.access(hook_path, os.X_OK):
            print(f"   ✅ {hook}")
        else:
            print(f"   ❌ {hook} (missing or not executable)")
            all_found = False

    # Check hook_base.py
    hook_base = hooks_dir / "hook_base.py"
    if hook_base.exists():
        print(f"   ✅ hook_base.py")
    else:
        print(f"   ⚠️  hook_base.py not found")
        all_found = False

    # Check shared modules
    shared_dir = hooks_dir / "shared"
    if shared_dir.exists():
        print(f"   ✅ shared/ (modules)")
    else:
        print(f"   ⚠️  shared/ directory not found")
        all_found = False

    # Check hooks.json
    hooks_json = Path.home() / ".cursor" / "hooks.json"
    if hooks_json.exists():
        print(f"   ✅ hooks.json")
    else:
        print(f"   ⚠️  hooks.json not found")

    return all_found


def check_config_files() -> bool:
    """Check configuration files exist."""
    print("\n⚙️  Checking configuration files...")

    blueplane_dir = Path.home() / ".blueplane"
    if not blueplane_dir.exists():
        print(f"   ⚠️  ~/.blueplane directory not found")
        return False

    config_files = ['redis.yaml', 'privacy.yaml']
    all_found = True

    for config_file in config_files:
        config_path = blueplane_dir / config_file
        if config_path.exists():
            print(f"   ✅ {config_file}")
        else:
            print(f"   ⚠️  {config_file} not found")
            all_found = False

    return all_found


def test_hook_execution() -> bool:
    """Test that a hook can execute successfully."""
    print("\n🧪 Testing hook execution...")

    hooks_dir = Path.home() / ".cursor" / "hooks"
    test_hook = hooks_dir / "stop.py"

    if not test_hook.exists():
        print(f"   ⚠️  Cannot test - hook not found: {test_hook}")
        return False

    try:
        # Set test environment variables
        env = os.environ.copy()
        env['CURSOR_SESSION_ID'] = 'test-session-12345'
        env['CURSOR_WORKSPACE_HASH'] = 'abc123'

        # Try to import and run hook
        import subprocess
        result = subprocess.run(
            [sys.executable, str(test_hook)],
            input='{"hook_event_name": "stop"}',
            text=True,
            env=env,
            capture_output=True,
            timeout=5
        )

        if result.returncode == 0:
            print(f"   ✅ Hook executed successfully")
            return True
        else:
            print(f"   ⚠️  Hook exited with code {result.returncode}")
            if result.stderr:
                print(f"      Error: {result.stderr}")
            return False

    except Exception as e:
        print(f"   ❌ Hook execution failed: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Verify Blueplane Telemetry installation'
    )

    print("=" * 60)
    print("Blueplane Telemetry - Installation Verification")
    print("=" * 60)

    checks = [
        ("Python Dependencies", lambda: check_python_dependencies()),
        ("Redis Connection", lambda: check_redis_connection()),
        ("Configuration Files", lambda: check_config_files()),
        ("Global Hooks Installation", lambda: check_hooks_installation()),
        ("Hook Execution", lambda: test_hook_execution()),
    ]

    results = {}
    for name, check_fn in checks:
        results[name] = check_fn()

    # Summary
    print("\n" + "=" * 60)
    print("📊 Verification Summary")
    print("=" * 60)

    all_passed = True
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:12} {name}")
        if not result:
            all_passed = False

    if all_passed:
        print("\n✅ All checks passed! Your installation is ready.")
        print("\n💡 Next: Start using Cursor and events will be captured automatically")
        return 0
    else:
        print("\n⚠️  Some checks failed. Review the output above for details.")
        print("\n📖 See README.md for installation instructions")
        return 1


if __name__ == '__main__':
    sys.exit(main())
