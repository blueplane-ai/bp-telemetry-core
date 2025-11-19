# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Platform detection utilities for Cursor database monitoring.
"""

import platform
import sys
from pathlib import Path
from typing import List

logger = None  # Will be set when logging is initialized


def get_cursor_database_paths() -> List[Path]:
    """
    Get Cursor database base paths for the current platform.

    Returns:
        List of possible database base paths
    """
    system = platform.system()
    home = Path.home()

    if system == "Darwin":  # macOS
        return [
            home / "Library/Application Support/Cursor/User/workspaceStorage",
        ]
    elif system == "Linux":
        return [
            home / ".config/Cursor/User/workspaceStorage",
        ]
    elif system == "Windows":
        return [
            home / "AppData/Roaming/Cursor/User/workspaceStorage",
        ]
    else:
        # Fallback: try all common locations
        return [
            home / "Library/Application Support/Cursor/User/workspaceStorage",
            home / ".config/Cursor/User/workspaceStorage",
            home / "AppData/Roaming/Cursor/User/workspaceStorage",
        ]


def normalize_path(path: str) -> Path:
    """
    Normalize a path string to a Path object.

    Handles platform-specific path separators and expansion.
    """
    return Path(path).expanduser().resolve()
















