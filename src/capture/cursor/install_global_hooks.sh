#!/bin/bash
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

#
# Install Cursor Global Hooks
#
# Installs Blueplane telemetry hooks to ~/.cursor/hooks/
# These hooks will fire for ALL Cursor workspaces.
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CURSOR_HOOKS_DIR="$HOME/.cursor/hooks"

echo "Installing Blueplane Cursor Global Hooks..."
echo ""

# DEPRECATION NOTICE
echo "========================================="
echo "NOTICE: Cursor hooks are deprecated for trace capture"
echo "========================================="
echo "Cursor now uses the VSCode extension for all telemetry capture."
echo "Hooks are no longer used for session tracking or trace capture."
echo ""

# Create hooks directory
echo "Creating hooks directory: $CURSOR_HOOKS_DIR"
mkdir -p "$CURSOR_HOOKS_DIR"

# Note: We no longer install hook scripts since we only use the extension
# for session tracking and telemetry capture
echo "Skipping hook scripts installation (deprecated - using extension events only)..."

# Copy base module (kept for compatibility but not used)
echo "Copying hook_base.py (for compatibility)..."
if [ -f "$SCRIPT_DIR/hook_base.py" ]; then
    cp "$SCRIPT_DIR/hook_base.py" "$CURSOR_HOOKS_DIR/hook_base.py"
fi

# Copy shared modules (kept for compatibility but not used)
echo "Copying shared modules (for compatibility)..."
SHARED_DIR="$CURSOR_HOOKS_DIR/shared"
mkdir -p "$SHARED_DIR"
if [ -d "$SCRIPT_DIR/../shared" ]; then
    cp "$SCRIPT_DIR/../shared"/*.py "$SHARED_DIR/" 2>/dev/null || true
fi

# Copy capture __init__.py for version (kept for compatibility)
echo "Copying capture module (for compatibility)..."
CAPTURE_DIR="$CURSOR_HOOKS_DIR/capture"
mkdir -p "$CAPTURE_DIR"
if [ -f "$SCRIPT_DIR/../__init__.py" ]; then
    cp "$SCRIPT_DIR/../__init__.py" "$CAPTURE_DIR/__init__.py"
fi

# Note: We no longer install actual hook scripts or merge hooks.json
echo "Skipping hooks.json merge (no hooks to register)..."

echo ""
echo "✅ Installation complete!"
echo ""
echo "The Cursor extension will handle all telemetry capture."
echo "No hooks are required for session tracking or trace capture."
echo ""
echo "Next steps:"
echo "  1. Install and activate the Cursor extension"
echo "  2. Start Redis: redis-server"
echo "  3. Open a Cursor workspace to test"
echo ""
