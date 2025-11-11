#!/usr/bin/env python3
"""Test that the installation script properly merges hooks."""

import json
import tempfile
from pathlib import Path
import sys

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from scripts.install_claude_code import update_settings_json


def test_merge_with_existing_hooks():
    """Test that hooks are properly merged with existing settings."""
    print("\n" + "=" * 60)
    print("Testing Hook Merge Logic")
    print("=" * 60)

    # Create temporary directory structure
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create fake hooks directory with scripts
        hooks_dir = tmpdir_path / "hooks" / "telemetry"
        hooks_dir.mkdir(parents=True)

        # Create fake hook files
        hook_files = [
            "session_start.py",
            "user_prompt_submit.py",
            "pre_tool_use.py",
            "post_tool_use.py",
            "pre_compact.py",
            "stop.py",
        ]

        for hook_file in hook_files:
            (hooks_dir / hook_file).write_text("#!/usr/bin/env python3\n# Fake hook\n")

        # Create fake settings.json with existing Stop hook
        settings_file = tmpdir_path / "settings.json"
        existing_settings = {
            "$schema": "https://json.schemastore.org/claude-code-settings.json",
            "hooks": {
                "Stop": [
                    {
                        "matcher": "",
                        "hooks": [
                            {
                                "type": "command",
                                "command": "~/.claude/stop-hook-git-check.sh"
                            }
                        ]
                    }
                ]
            },
            "permissions": {
                "allow": ["Skill"]
            }
        }

        with open(settings_file, 'w') as f:
            json.dump(existing_settings, f, indent=4)

        print("\n📝 Original settings.json:")
        print(json.dumps(existing_settings, indent=2))

        # Mock Path.home() to return our temp directory
        original_home = Path.home

        def mock_home():
            return tmpdir_path  # Return tmpdir, not tmpdir/.claude

        # Create .claude directory
        (tmpdir_path / ".claude").mkdir()

        # Copy settings to mock location
        mock_settings = tmpdir_path / ".claude" / "settings.json"
        with open(mock_settings, 'w') as f:
            json.dump(existing_settings, f, indent=4)

        # Monkey patch Path.home
        Path.home = staticmethod(mock_home)

        try:
            # Run the update function
            print("\n🔧 Running update_settings_json...")
            success = update_settings_json(hooks_dir, backup=False)

            if not success:
                print("\n❌ Update failed!")
                return False

            # Read updated settings
            with open(mock_settings, 'r') as f:
                updated_settings = json.load(f)

            print("\n📝 Updated settings.json:")
            print(json.dumps(updated_settings, indent=2))

            # Verify merge
            print("\n🔍 Verification:")

            # Check that permissions are preserved
            if "permissions" in updated_settings:
                print("   ✅ Existing 'permissions' preserved")
            else:
                print("   ❌ ERROR: 'permissions' was removed!")
                return False

            # Check that $schema is preserved
            if "$schema" in updated_settings:
                print("   ✅ Existing '$schema' preserved")
            else:
                print("   ❌ ERROR: '$schema' was removed!")
                return False

            # Check Stop hook merge
            if "Stop" in updated_settings["hooks"]:
                stop_hooks = updated_settings["hooks"]["Stop"]
                if len(stop_hooks) > 0:
                    empty_matcher = None
                    for matcher in stop_hooks:
                        if matcher.get("matcher") == "":
                            empty_matcher = matcher
                            break

                    if empty_matcher:
                        hooks_list = empty_matcher.get("hooks", [])
                        commands = [h.get("command") for h in hooks_list]

                        # Should have both the original and our new hook
                        has_original = any("git-check" in cmd for cmd in commands)
                        has_telemetry = any("stop.py" in cmd for cmd in commands)

                        if has_original and has_telemetry:
                            print(f"   ✅ Stop hook properly merged (found {len(hooks_list)} hooks)")
                            print(f"      - Original git-check hook preserved")
                            print(f"      - Telemetry stop.py hook added")
                        elif has_original and not has_telemetry:
                            print("   ❌ ERROR: Telemetry hook not added!")
                            return False
                        elif has_telemetry and not has_original:
                            print("   ❌ ERROR: Original git-check hook was removed!")
                            return False
                    else:
                        print("   ❌ ERROR: No empty matcher found in Stop hooks!")
                        return False
            else:
                print("   ❌ ERROR: Stop hooks missing!")
                return False

            # Check that all new hooks were added
            expected_hooks = ["SessionStart", "UserPromptSubmit", "PreToolUse",
                              "PostToolUse", "PreCompact", "Stop"]
            for hook_name in expected_hooks:
                if hook_name in updated_settings["hooks"]:
                    print(f"   ✅ {hook_name} hook registered")
                else:
                    print(f"   ❌ ERROR: {hook_name} hook missing!")
                    return False

            print("\n" + "=" * 60)
            print("✅ All tests passed!")
            print("=" * 60)
            return True

        finally:
            # Restore original Path.home
            Path.home = staticmethod(original_home)


if __name__ == '__main__':
    success = test_merge_with_existing_hooks()
    sys.exit(0 if success else 1)
