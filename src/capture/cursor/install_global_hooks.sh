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

# Create hooks directory
echo "Creating hooks directory: $CURSOR_HOOKS_DIR"
mkdir -p "$CURSOR_HOOKS_DIR"

# Copy hook scripts
echo "Copying hook scripts..."
for hook in "$SCRIPT_DIR/hooks"/*.py; do
    hook_name=$(basename "$hook")
    echo "  - $hook_name"
    cp "$hook" "$CURSOR_HOOKS_DIR/$hook_name"
    chmod +x "$CURSOR_HOOKS_DIR/$hook_name"
done

# Copy base module
echo "Copying hook_base.py..."
cp "$SCRIPT_DIR/hook_base.py" "$CURSOR_HOOKS_DIR/hook_base.py"

# Copy shared modules
echo "Copying shared modules..."
SHARED_DIR="$CURSOR_HOOKS_DIR/shared"
mkdir -p "$SHARED_DIR"
cp "$SCRIPT_DIR/../shared"/*.py "$SHARED_DIR/"

# Copy capture __init__.py for version
echo "Copying capture module..."
CAPTURE_DIR="$CURSOR_HOOKS_DIR/capture"
mkdir -p "$CAPTURE_DIR"
cp "$SCRIPT_DIR/../__init__.py" "$CAPTURE_DIR/__init__.py"

# Copy session event sender
echo "Copying session event sender..."
cp "$SCRIPT_DIR/send_session_event.py" "$CURSOR_HOOKS_DIR/send_session_event.py"
chmod +x "$CURSOR_HOOKS_DIR/send_session_event.py"

# Copy hooks.json configuration
echo "Copying hooks.json configuration..."
cp "$SCRIPT_DIR/hooks.json" "$HOME/.cursor/hooks.json"

echo ""
echo "✅ Global hooks installed successfully!"
echo ""
echo "Installed to: $CURSOR_HOOKS_DIR"
echo ""
echo "These hooks will fire for ALL Cursor workspaces."
echo "The Cursor extension will send session start/end events"
echo "to track which workspace is active."
echo ""
echo "Next steps:"
echo "  1. Install and activate the Cursor extension"
echo "  2. Start Redis: redis-server"
echo "  3. Open a Cursor workspace to test"
echo ""
