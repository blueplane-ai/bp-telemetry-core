#!/bin/bash
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only

# =============================================================================
# Real Integration Tests Runner
# =============================================================================
#
# This script runs integration tests that invoke actual Claude Code commands
# and verify telemetry is properly captured.
#
# Prerequisites:
#   - Claude Code CLI installed: npm install -g @anthropic/claude-code
#   - Claude Code configured with API key
#   - Telemetry hooks configured OR telemetry server running
#
# Usage:
#   ./testing_integration/run_integration_tests.sh
#
# =============================================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}Blueplane Telemetry - Real Integration Tests${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check Claude CLI
if ! command -v claude &> /dev/null; then
    echo -e "${RED}Error: Claude Code CLI not found${NC}"
    echo "Install with: npm install -g @anthropic/claude-code"
    exit 1
fi

CLAUDE_VERSION=$(claude --version 2>/dev/null || echo "unknown")
echo -e "  ${GREEN}✓${NC} Claude CLI: $CLAUDE_VERSION"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: Python 3 not found${NC}"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Python 3 available"

# Check telemetry database
TELEMETRY_DB="$HOME/.blueplane/telemetry.db"
if [ -f "$TELEMETRY_DB" ]; then
    echo -e "  ${GREEN}✓${NC} Telemetry database exists"
else
    echo -e "  ${YELLOW}⚠${NC} Telemetry database not found at $TELEMETRY_DB"
    echo "     Some tests may be skipped"
fi

echo ""
echo -e "${YELLOW}Running integration tests...${NC}"
echo ""

# Run the Python test suite
cd "$PROJECT_ROOT"
set +e  # allow script to report results even if tests fail
python3 testing_integration/test_claude_telemetry.py
EXIT_CODE=$?
set -e

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}All integration tests passed!${NC}"
    echo -e "${GREEN}============================================================${NC}"
else
    echo -e "${RED}============================================================${NC}"
    echo -e "${RED}Some integration tests failed${NC}"
    echo -e "${RED}============================================================${NC}"
fi

exit $EXIT_CODE
