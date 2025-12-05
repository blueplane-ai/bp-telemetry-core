# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""Pytest configuration and shared fixtures."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Configure pytest-asyncio if available
try:
    import pytest_asyncio
    pytest_plugins = ['pytest_asyncio']
    # Configure asyncio default fixture loop scope to avoid deprecation warning
    import pytest
    pytest_asyncio.fixture_scope = "function"  # Default to function scope
except ImportError:
    # pytest-asyncio not installed, async tests will be skipped
    pass

# Import fixtures so pytest can discover them
from tests.fixtures.sqlite_fixtures import *  # noqa: F401, F403
from tests.fixtures.duckdb_fixtures import *  # noqa: F401, F403

