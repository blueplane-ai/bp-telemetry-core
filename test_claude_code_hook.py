#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Quick test to verify Claude Code hooks work correctly.
"""

import json
import sys
from io import StringIO

# Test data for SessionStart hook
def test_session_start():
    """Test the SessionStart hook."""
    print("\n=== Testing SessionStart Hook ===")

    # Mock stdin input
    test_input = {
        "session_id": "test_session_123",
        "source": "startup"
    }

    # Redirect stdin
    old_stdin = sys.stdin
    sys.stdin = StringIO(json.dumps(test_input))

    try:
        from src.capture.claude_code.hooks.session_start import SessionStartHook

        hook = SessionStartHook()

        # Verify hook initialized correctly
        assert hook.session_id == "test_session_123", "Session ID not extracted correctly"
        assert hook.hook_type.value == "SessionStart", "Hook type incorrect"

        print("✓ SessionStart hook initialized correctly")
        print(f"  - Session ID: {hook.session_id}")
        print(f"  - Hook Type: {hook.hook_type.value}")

        return True
    finally:
        sys.stdin = old_stdin


def test_user_prompt_submit():
    """Test the UserPromptSubmit hook."""
    print("\n=== Testing UserPromptSubmit Hook ===")

    # Mock stdin input
    test_input = {
        "session_id": "test_session_456",
        "prompt": "Write a function to reverse a string"
    }

    # Redirect stdin
    old_stdin = sys.stdin
    sys.stdin = StringIO(json.dumps(test_input))

    try:
        from src.capture.claude_code.hooks.user_prompt_submit import UserPromptSubmitHook

        hook = UserPromptSubmitHook()

        # Verify hook initialized correctly
        assert hook.session_id == "test_session_456", "Session ID not extracted correctly"
        assert hook.hook_type.value == "UserPromptSubmit", "Hook type incorrect"

        print("✓ UserPromptSubmit hook initialized correctly")
        print(f"  - Session ID: {hook.session_id}")
        print(f"  - Hook Type: {hook.hook_type.value}")

        return True
    finally:
        sys.stdin = old_stdin


def test_pre_tool_use():
    """Test the PreToolUse hook."""
    print("\n=== Testing PreToolUse Hook ===")

    # Mock stdin input
    test_input = {
        "session_id": "test_session_789",
        "tool_name": "Read",
        "tool_input": {
            "file_path": "/path/to/file.py"
        }
    }

    # Redirect stdin
    old_stdin = sys.stdin
    sys.stdin = StringIO(json.dumps(test_input))

    try:
        from src.capture.claude_code.hooks.pre_tool_use import PreToolUseHook

        hook = PreToolUseHook()

        # Verify hook initialized correctly
        assert hook.session_id == "test_session_789", "Session ID not extracted correctly"
        assert hook.hook_type.value == "PreToolUse", "Hook type incorrect"

        print("✓ PreToolUse hook initialized correctly")
        print(f"  - Session ID: {hook.session_id}")
        print(f"  - Hook Type: {hook.hook_type.value}")

        return True
    finally:
        sys.stdin = old_stdin


def test_post_tool_use():
    """Test the PostToolUse hook."""
    print("\n=== Testing PostToolUse Hook ===")

    # Mock stdin input
    test_input = {
        "session_id": "test_session_101",
        "tool_name": "Read",
        "tool_input": {
            "file_path": "/path/to/file.py"
        },
        "tool_result": "File contents here...",
        "tool_response": {
            "success": True
        },
        "error": None,
        "tool_use_error": None
    }

    # Redirect stdin
    old_stdin = sys.stdin
    sys.stdin = StringIO(json.dumps(test_input))

    try:
        from src.capture.claude_code.hooks.post_tool_use import PostToolUseHook

        hook = PostToolUseHook()

        # Verify hook initialized correctly
        assert hook.session_id == "test_session_101", "Session ID not extracted correctly"
        assert hook.hook_type.value == "PostToolUse", "Hook type incorrect"

        print("✓ PostToolUse hook initialized correctly")
        print(f"  - Session ID: {hook.session_id}")
        print(f"  - Hook Type: {hook.hook_type.value}")

        return True
    finally:
        sys.stdin = old_stdin


def main():
    """Run all tests."""
    print("=" * 60)
    print("Claude Code Hook Implementation Tests")
    print("=" * 60)

    all_passed = True

    try:
        all_passed &= test_session_start()
        all_passed &= test_user_prompt_submit()
        all_passed &= test_pre_tool_use()
        all_passed &= test_post_tool_use()
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    print("\n" + "=" * 60)
    if all_passed:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == '__main__':
    sys.exit(main())
