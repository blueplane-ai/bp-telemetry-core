#!/bin/bash
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only

# =============================================================================
# Blueplane Telemetry Core - Test Runner
# =============================================================================
#
# Usage:
#   ./run_tests.sh              # Run all tests
#   ./run_tests.sh unit         # Run unit tests only
#   ./run_tests.sh integration  # Run integration tests only
#   ./run_tests.sh quick        # Run quick tests (no slow markers)
#   ./run_tests.sh coverage     # Run with coverage report
#
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project root
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo -e "${BLUE}============================================================${NC}"
echo -e "${BLUE}Blueplane Telemetry Core - Test Runner${NC}"
echo -e "${BLUE}============================================================${NC}"
echo ""

# Check for pytest
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}Error: pytest not found. Install with: pip install pytest${NC}"
    exit 1
fi

# Parse arguments
TEST_TYPE="${1:-all}"
PYTEST_ARGS=""

case "$TEST_TYPE" in
    unit)
        echo -e "${YELLOW}Running: Unit Tests${NC}"
        PYTEST_ARGS="tests/test_bug_audit_fixes.py tests/test_schema_migration.py -v"
        ;;
    integration)
        echo -e "${YELLOW}Running: Integration Tests${NC}"
        PYTEST_ARGS="tests/test_integration.py scripts/test_bug_fixes_integration.py -v"
        ;;
    quick)
        echo -e "${YELLOW}Running: Quick Tests (no slow markers)${NC}"
        PYTEST_ARGS="tests/ -v -m 'not slow'"
        ;;
    coverage)
        echo -e "${YELLOW}Running: All Tests with Coverage${NC}"
        PYTEST_ARGS="tests/ --cov=src --cov-report=term-missing --cov-report=html -v"
        ;;
    bug-fixes)
        echo -e "${YELLOW}Running: Bug Fix Tests Only${NC}"
        PYTEST_ARGS="tests/test_bug_audit_fixes.py -v"
        ;;
    all|*)
        echo -e "${YELLOW}Running: All Tests${NC}"
        PYTEST_ARGS="tests/ -v"
        ;;
esac

echo ""
echo -e "${BLUE}Command: pytest $PYTEST_ARGS${NC}"
echo ""

# Run tests
START_TIME=$(date +%s)

if pytest $PYTEST_ARGS; then
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    echo ""
    echo -e "${GREEN}============================================================${NC}"
    echo -e "${GREEN}✅ All tests passed in ${DURATION}s${NC}"
    echo -e "${GREEN}============================================================${NC}"
    exit 0
else
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))
    echo ""
    echo -e "${RED}============================================================${NC}"
    echo -e "${RED}❌ Some tests failed (${DURATION}s)${NC}"
    echo -e "${RED}============================================================${NC}"
    exit 1
fi
