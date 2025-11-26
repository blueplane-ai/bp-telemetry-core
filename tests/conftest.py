# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""Pytest configuration and shared fixtures."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Import fixtures so pytest can discover them
from tests.fixtures.sqlite_fixtures import *  # noqa: F401, F403
from tests.fixtures.duckdb_fixtures import *  # noqa: F401, F403

