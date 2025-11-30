#!/bin/bash

# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

# =============================================================================
# Blueplane Telemetry - Cursor Extension Uninstall Script
# =============================================================================
# Uninstalls the Cursor extension and optionally cleans up session data
# Usage: ./uninstall_cursor_extension.sh [--dry-run] [--all]
# =============================================================================

set -e  # Exit on error

# Parse arguments
DRY_RUN=false
DELETE_ALL=false
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --all)
            DELETE_ALL=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run] [--all]"
            echo ""
            echo "Options:"
            echo "  --dry-run    Show what would be done without making changes"
            echo "  --all        Delete all session data without prompting"
            echo "  -h, --help   Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $arg"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo -e "${BLUE}===================================${NC}"
echo -e "${BLUE}Blueplane Cursor Extension Uninstall${NC}"
if [ "$DRY_RUN" = true ]; then
    echo -e "${MAGENTA}DRY RUN MODE - No changes will be made${NC}"
fi
echo -e "${BLUE}===================================${NC}"
echo ""

# =============================================================================
# Check Cursor CLI
# =============================================================================

if ! command -v cursor &> /dev/null; then
    echo -e "${RED}❌ Cursor CLI not found in PATH${NC}"
    echo ""
    echo "To uninstall manually:"
    echo "1. Open Cursor"
    echo "2. Go to Extensions (Cmd+Shift+X)"
    echo "3. Search for 'Blueplane Telemetry'"
    echo "4. Click Uninstall"
    exit 1
fi

CURSOR_VERSION=$(cursor --version | head -n 1)
echo -e "${GREEN}✅${NC} Cursor: $CURSOR_VERSION"
echo ""

# =============================================================================
# Check Extension Status
# =============================================================================

echo -e "${BLUE}[1/3]${NC} Checking extension status..."

EXTENSION_ID="blueplane.blueplane-cursor-telemetry"
if cursor --list-extensions | grep -q "$EXTENSION_ID"; then
    echo -e "   ${GREEN}✅${NC} Extension found: $EXTENSION_ID"
    EXTENSION_INSTALLED=true
else
    echo -e "   ${YELLOW}⚠️${NC}  Extension not installed"
    EXTENSION_INSTALLED=false
fi

# =============================================================================
# Uninstall Extension
# =============================================================================

if [ "$EXTENSION_INSTALLED" = true ]; then
    echo ""
    echo -e "${BLUE}[2/3]${NC} Uninstalling extension..."
    if [ "$DRY_RUN" = true ]; then
        echo -e "   ${MAGENTA}[DRY RUN]${NC} Would run: cursor --uninstall-extension $EXTENSION_ID"
    else
        cursor --uninstall-extension "$EXTENSION_ID"
        echo -e "   ${GREEN}✅${NC} Extension uninstalled"
    fi
else
    echo ""
    echo -e "${BLUE}[2/3]${NC} Extension not installed, skipping..."
fi

# =============================================================================
# Clean Up Session Data (Optional)
# =============================================================================

echo ""
echo -e "${BLUE}[3/3]${NC} Session data cleanup..."

SESSION_DIR="$HOME/.blueplane/cursor-session"

if [ -d "$SESSION_DIR" ]; then
    echo ""
    echo -e "${YELLOW}Session data found:${NC}"
    echo "  Location: $SESSION_DIR"

    # Count session files
    SESSION_COUNT=$(find "$SESSION_DIR" -type f -name "*.json" 2>/dev/null | wc -l | tr -d ' ')
    echo "  Files: $SESSION_COUNT session file(s)"

    # Show disk usage
    DISK_USAGE=$(du -sh "$SESSION_DIR" 2>/dev/null | cut -f1)
    echo "  Size: $DISK_USAGE"

    echo ""

    # Handle deletion based on flags
    if [ "$DRY_RUN" = true ]; then
        if [ "$DELETE_ALL" = true ]; then
            echo -e "   ${MAGENTA}[DRY RUN]${NC} Would delete: $SESSION_DIR"
        else
            echo -e "   ${MAGENTA}[DRY RUN]${NC} Would prompt to delete session data"
        fi
    elif [ "$DELETE_ALL" = true ]; then
        rm -rf "$SESSION_DIR"
        echo -e "   ${GREEN}✅${NC} Session data deleted"
    else
        read -p "Do you want to delete session data? This will remove all session history. (y/N): " -n 1 -r
        echo ""

        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$SESSION_DIR"
            echo -e "   ${GREEN}✅${NC} Session data deleted"
        else
            echo -e "   ${BLUE}ℹ${NC}  Session data preserved"
            echo ""
            echo "To manually delete later, run:"
            echo "  rm -rf $SESSION_DIR"
        fi
    fi
else
    echo "   No session data found at $SESSION_DIR"
fi

# =============================================================================
# Check Database Data (Optional)
# =============================================================================

echo ""
TELEMETRY_DB="$HOME/.blueplane/telemetry.db"
CURSOR_HISTORY_DB="$HOME/.blueplane/cursor_history.duckdb"

if [ -f "$TELEMETRY_DB" ] || [ -f "$CURSOR_HISTORY_DB" ]; then
    echo -e "${YELLOW}Database files found:${NC}"

    if [ -f "$TELEMETRY_DB" ]; then
        TELEMETRY_SIZE=$(du -sh "$TELEMETRY_DB" 2>/dev/null | cut -f1)
        echo "  - telemetry.db ($TELEMETRY_SIZE)"
    fi

    if [ -f "$CURSOR_HISTORY_DB" ]; then
        HISTORY_SIZE=$(du -sh "$CURSOR_HISTORY_DB" 2>/dev/null | cut -f1)
        echo "  - cursor_history.duckdb ($HISTORY_SIZE)"
    fi

    echo ""
    echo "These databases contain your telemetry data and are shared"
    echo "with other Blueplane components. They were NOT deleted."
    echo ""
    echo "To remove all Blueplane data, run:"
    echo "  rm -rf ~/.blueplane"
fi

# =============================================================================
# Summary
# =============================================================================

echo ""
if [ "$DRY_RUN" = true ]; then
    echo -e "${MAGENTA}===================================${NC}"
    echo -e "${MAGENTA}DRY RUN Complete!${NC}"
    echo -e "${MAGENTA}===================================${NC}"
    echo ""
    echo "No changes were made. Run without --dry-run to uninstall."
else
    echo -e "${GREEN}===================================${NC}"
    echo -e "${GREEN}Uninstallation Complete!${NC}"
    echo -e "${GREEN}===================================${NC}"
    echo ""

    if [ "$EXTENSION_INSTALLED" = true ]; then
        echo "The Cursor extension has been uninstalled."
        echo ""
        echo "Next steps:"
        echo "1. Restart Cursor to complete removal"
        echo "2. Extension logs will no longer appear in Output panel"
        echo "3. Session tracking for Cursor workspaces is disabled"
    else
        echo "No extension was found to uninstall."
    fi
fi

echo ""
echo -e "${BLUE}Remaining components:${NC}"
echo "  - Processing server (if running): python scripts/server_ctl.py stop"
echo "  - Redis data: redis-cli FLUSHALL (caution: removes all Redis data)"
echo "  - Blueplane home: ~/.blueplane/ (preserved)"
echo ""
