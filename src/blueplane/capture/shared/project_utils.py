"""Shared helpers for deriving human-readable project identifiers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def derive_project_name(
    workspace_path: Optional[str],
    fallback_path: Optional[str] = None,
    *,
    max_length: int = 80,
) -> Optional[str]:
    """
    Derive a human-readable project name from a workspace path.

    Args:
        workspace_path: Full path to the workspace root provided by the caller.
        fallback_path: Optional secondary path (e.g., current working directory).
        max_length: Optional maximum length for the returned project name.

    Returns:
        A sanitized project name or None if it cannot be determined.
    """

    candidate = workspace_path or fallback_path
    if not candidate:
        return None

    # Remove trailing path separators to avoid empty stem/name results.
    candidate = candidate.rstrip("/\\")
    if not candidate:
        return None

    # Use pathlib for cross-platform path parsing.
    name = Path(candidate).name

    # As a fallback (e.g., if path ends with drive letter), fall back to basename.
    if not name:
        name = os.path.basename(candidate)

    # Final guard if basename is still empty (unlikely but defensive).
    if not name:
        return None

    name = name.strip()
    if not name:
        return None

    if len(name) > max_length:
        return f"{name[: max_length - 3]}..."

    return name


def recover_workspace_path_from_slug(project_dir: Path) -> Optional[str]:
    """
    Recover an absolute workspace path from a Claude project directory slug.

    Claude stores workspaces under ~/.claude/projects with directory names
    like -Users-user-Dev-project-name where path separators are replaced with
    hyphens. This helper attempts to reconstruct the original path while
    preserving legitimate hyphens in directory names by probing the real
    filesystem structure.
    """
    if not project_dir:
        return None

    slug = project_dir.name.lstrip("-")
    if not slug:
        return None

    tokens = slug.split("-")
    current_path = Path("/")
    idx = 0

    while idx < len(tokens):
        candidate = tokens[idx]
        next_idx = idx + 1
        candidate_path = current_path / candidate

        # Merge subsequent tokens until we find a real directory path or exhaust tokens
        while not candidate_path.exists() and next_idx < len(tokens):
            candidate = f"{candidate}-{tokens[next_idx]}"
            next_idx += 1
            candidate_path = current_path / candidate

        if candidate_path.exists():
            current_path = candidate_path
            idx = next_idx
        else:
            # No matching directory on disk; append remaining tokens as-is
            remaining = "-".join(tokens[idx:])
            current_path = current_path / remaining
            idx = len(tokens)

    return str(current_path)


__all__ = ["derive_project_name", "recover_workspace_path_from_slug"]


