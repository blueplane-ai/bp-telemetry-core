#!/bin/bash
set -e

EXT_DIR="/Users/bbalaran/Dev/sierra/blueplane/bp-telemetry-core/src/capture/cursor/extension"
CURSOR_EXT_DIR="$HOME/Library/Application Support/Cursor/User/extensions"
TARGET="$CURSOR_EXT_DIR/blueplane-cursor-telemetry"

echo "📦 Compiling extension..."
cd "$EXT_DIR"
npm run compile

echo ""
echo "📥 Installing extension to: $TARGET"

# Create extensions directory
mkdir -p "$CURSOR_EXT_DIR"

# Remove existing installation
if [ -d "$TARGET" ]; then
    echo "   Removing existing installation..."
    rm -rf "$TARGET"
fi

# Create target directory
mkdir -p "$TARGET"

# Copy essential files
echo "   Copying files..."
cp package.json package-lock.json tsconfig.json README.md "$TARGET/" 2>/dev/null || true

# Copy compiled output
if [ -d "out" ]; then
    cp -r out "$TARGET/"
    echo "   ✅ out/"
fi

# Copy node_modules
if [ -d "node_modules" ]; then
    echo "   Copying node_modules (this may take a moment)..."
    cp -r node_modules "$TARGET/"
    echo "   ✅ node_modules/"
fi

echo ""
echo "✅ Extension installed successfully!"
echo "   Location: $TARGET"
echo ""
echo "📋 Next steps:"
echo "   1. Restart Cursor IDE"
echo "   2. The extension should activate automatically"


