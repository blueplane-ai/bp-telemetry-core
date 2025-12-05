# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""Utilities for git repository identification."""

import logging
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# UUID v5 namespace for deterministic repo ID generation
# Using the DNS namespace as a stable base
REPO_NAMESPACE = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')


def normalize_remote_url(url: str) -> str:
    """
    Normalize git remote URL for repo ID generation.

    Removes .git suffix, converts to lowercase, and standardizes format.

    Args:
        url: Git remote URL

    Returns:
        Normalized URL
    """
    if not url:
        return ""

    # Convert to lowercase
    normalized = url.lower()

    # Remove .git suffix
    if normalized.endswith('.git'):
        normalized = normalized[:-4]

    # Remove trailing slashes
    normalized = normalized.rstrip('/')

    return normalized


def generate_repo_id(repo_path: Optional[str] = None, remote_url: Optional[str] = None) -> str:
    """
    Generate a stable, deterministic repo ID for a git repository.

    Strategy:
    1. If remote URL exists (e.g., git@github.com:org/repo.git), use it (preferred)
    2. Otherwise, use the absolute path to the repository root
    3. Generate UUID v5 from the source for determinism

    Args:
        repo_path: Absolute path to git repository root
        remote_url: Git remote URL (typically origin)

    Returns:
        UUID v5 string identifying the repository
    """
    if remote_url and remote_url.strip():
        # Prefer remote URL as it's more stable across clones
        normalized = normalize_remote_url(remote_url)
        source = f"remote:{normalized}"
    elif repo_path and repo_path.strip():
        # Fall back to repo path for local-only repositories
        source = f"path:{repo_path}"
    else:
        # Emergency fallback
        logger.warning("generate_repo_id called with no repo_path or remote_url")
        source = "unknown:unknown"

    # Generate deterministic UUID v5
    try:
        repo_id = str(uuid.uuid5(REPO_NAMESPACE, source))
        logger.debug(f"Generated repo_id from {source}: {repo_id}")
        return repo_id
    except Exception as e:
        logger.error(f"Error generating repo_id: {e}")
        # Fall back to a hash-based approach
        import hashlib
        fallback_id = hashlib.sha256(source.encode()).hexdigest()[:32]
        return fallback_id
