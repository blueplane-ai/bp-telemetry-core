#!/bin/bash

# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

# =============================================================================
# Blueplane Telemetry - Cursor Extension Install Script
# =============================================================================
# Compiles, packages, and installs the Cursor extension
# Usage: ./install_cursor_extension.sh [--dry-run]
# =============================================================================

set -e  # Exit on error

# Parse arguments
DRY_RUN=false
for arg in "$@"; do
    case $arg in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--dry-run]"
            echo ""
            echo "Options:"
            echo "  --dry-run    Show what would be done without making changes"
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
EXTENSION_DIR="$PROJECT_ROOT/src/capture/cursor/extension"
CONFIG_FILE="$PROJECT_ROOT/config/config.yaml"

echo -e "${BLUE}================================${NC}"
echo -e "${BLUE}Blueplane Cursor Extension Install${NC}"
if [ "$DRY_RUN" = true ]; then
    echo -e "${MAGENTA}DRY RUN MODE - No changes will be made${NC}"
fi
echo -e "${BLUE}================================${NC}"
echo ""

# =============================================================================
# Check Prerequisites
# =============================================================================

echo -e "${BLUE}[1/7]${NC} Checking prerequisites..."

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js is not installed${NC}"
    echo "   Please install Node.js 18+ from https://nodejs.org/"
    exit 1
fi
NODE_VERSION=$(node --version)
echo -e "   ${GREEN}✅${NC} Node.js: $NODE_VERSION"

# Check npm
if ! command -v npm &> /dev/null; then
    echo -e "${RED}❌ npm is not installed${NC}"
    exit 1
fi
NPM_VERSION=$(npm --version)
echo -e "   ${GREEN}✅${NC} npm: $NPM_VERSION"

# Check Cursor CLI
if ! command -v cursor &> /dev/null; then
    echo -e "${YELLOW}⚠️  Cursor CLI not found in PATH${NC}"
    echo "   Extension will be packaged but you'll need to install manually"
    CURSOR_AVAILABLE=false
else
    CURSOR_VERSION=$(cursor --version | head -n 1)
    echo -e "   ${GREEN}✅${NC} Cursor: $CURSOR_VERSION"
    CURSOR_AVAILABLE=true
fi

# Check config file
if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ Configuration file not found: $CONFIG_FILE${NC}"
    exit 1
fi
echo -e "   ${GREEN}✅${NC} Config file: $CONFIG_FILE"

# Check extension directory
if [ ! -d "$EXTENSION_DIR" ]; then
    echo -e "${RED}❌ Extension directory not found: $EXTENSION_DIR${NC}"
    exit 1
fi
echo -e "   ${GREEN}✅${NC} Extension directory: $EXTENSION_DIR"

# =============================================================================
# Install Dependencies
# =============================================================================

echo ""
echo -e "${BLUE}[2/7]${NC} Installing npm dependencies..."
cd "$EXTENSION_DIR"

if [ -d "node_modules" ]; then
    echo "   Dependencies already installed, skipping..."
else
    if [ "$DRY_RUN" = true ]; then
        echo -e "   ${MAGENTA}[DRY RUN]${NC} Would run: npm install"
    else
        npm install
        echo -e "   ${GREEN}✅${NC} Dependencies installed"
    fi
fi

# =============================================================================
# Clean Previous Build
# =============================================================================

echo ""
echo -e "${BLUE}[3/7]${NC} Cleaning previous build..."
if [ -d "out" ]; then
    if [ "$DRY_RUN" = true ]; then
        echo -e "   ${MAGENTA}[DRY RUN]${NC} Would remove: out/"
    else
        rm -rf out
        echo "   Removed old build directory"
    fi
fi
if ls *.vsix 1> /dev/null 2>&1; then
    if [ "$DRY_RUN" = true ]; then
        echo -e "   ${MAGENTA}[DRY RUN]${NC} Would remove: *.vsix"
    else
        rm -f *.vsix
        echo "   Removed old VSIX packages"
    fi
fi
echo -e "   ${GREEN}✅${NC} Clean complete"

# =============================================================================
# Compile TypeScript
# =============================================================================

echo ""
echo -e "${BLUE}[4/7]${NC} Compiling TypeScript..."
if [ "$DRY_RUN" = true ]; then
    echo -e "   ${MAGENTA}[DRY RUN]${NC} Would run: npm run compile"
else
    npm run compile
    echo -e "   ${GREEN}✅${NC} TypeScript compiled to out/"
fi

# =============================================================================
# Copy Configuration
# =============================================================================

echo ""
echo -e "${BLUE}[5/7]${NC} Copying configuration files..."
if [ "$DRY_RUN" = true ]; then
    echo -e "   ${MAGENTA}[DRY RUN]${NC} Would create: out/config/"
    echo -e "   ${MAGENTA}[DRY RUN]${NC} Would copy: $CONFIG_FILE → out/config/config.yaml"
else
    mkdir -p out/config
    cp "$CONFIG_FILE" out/config/config.yaml
    echo -e "   ${GREEN}✅${NC} Configuration copied to out/config/"
fi

# Verify critical files (skip in dry-run)
if [ "$DRY_RUN" = false ] && [ ! -f "out/extension.js" ]; then
    echo -e "${RED}❌ Compilation failed: out/extension.js not found${NC}"
    exit 1
fi

# =============================================================================
# Package Extension
# =============================================================================

echo ""
echo -e "${BLUE}[6/7]${NC} Packaging extension as VSIX..."

# Install vsce if not present
if ! command -v vsce &> /dev/null; then
    if [ "$DRY_RUN" = true ]; then
        echo -e "   ${MAGENTA}[DRY RUN]${NC} Would install: @vscode/vsce globally"
    else
        echo "   Installing @vscode/vsce..."
        npm install -g @vscode/vsce
    fi
fi

# Create .vscodeignore if it doesn't exist
if [ ! -f ".vscodeignore" ]; then
    if [ "$DRY_RUN" = true ]; then
        echo -e "   ${MAGENTA}[DRY RUN]${NC} Would create: .vscodeignore"
    else
        echo "   Creating .vscodeignore..."
        cat > .vscodeignore << 'EOF'
.vscode/**
.vscode-test/**
src/**
.gitignore
.yarnrc
vsc-extension-quickstart.md
**/tsconfig.json
**/.eslintrc.json
**/*.map
**/*.ts
node_modules/**
EOF
    fi
fi

# Package the extension
if [ "$DRY_RUN" = true ]; then
    echo -e "   ${MAGENTA}[DRY RUN]${NC} Would run: vsce package"
    VSIX_FILE="blueplane-cursor-telemetry-0.1.0.vsix"
    echo -e "   ${MAGENTA}[DRY RUN]${NC} Would create: $VSIX_FILE"
else
    vsce package
    VSIX_FILE=$(ls -t *.vsix | head -n 1)
    echo -e "   ${GREEN}✅${NC} Extension packaged: $VSIX_FILE"
fi

# =============================================================================
# Install Extension
# =============================================================================

echo ""
echo -e "${BLUE}[7/7]${NC} Installing extension in Cursor..."

if [ "$CURSOR_AVAILABLE" = true ]; then
    # Uninstall old version if exists
    if cursor --list-extensions | grep -q "blueplane.blueplane-cursor-telemetry"; then
        if [ "$DRY_RUN" = true ]; then
            echo -e "   ${MAGENTA}[DRY RUN]${NC} Would uninstall: blueplane.blueplane-cursor-telemetry"
        else
            echo "   Uninstalling previous version..."
            cursor --uninstall-extension blueplane.blueplane-cursor-telemetry || true
        fi
    fi

    # Install new version
    if [ "$DRY_RUN" = true ]; then
        echo -e "   ${MAGENTA}[DRY RUN]${NC} Would run: cursor --install-extension $VSIX_FILE --force"
    else
        cursor --install-extension "$VSIX_FILE" --force
        echo -e "   ${GREEN}✅${NC} Extension installed in Cursor"
    fi

    echo ""
    if [ "$DRY_RUN" = true ]; then
        echo -e "${MAGENTA}================================${NC}"
        echo -e "${MAGENTA}DRY RUN Complete!${NC}"
        echo -e "${MAGENTA}================================${NC}"
        echo ""
        echo "No changes were made. Run without --dry-run to install."
    else
        echo -e "${GREEN}================================${NC}"
        echo -e "${GREEN}Installation Complete!${NC}"
        echo -e "${GREEN}================================${NC}"
        echo ""
        echo "Next steps:"
        echo "1. Restart Cursor or reload window (Cmd+Shift+P → 'Reload Window')"
        echo "2. Check extension status: View → Output → 'Blueplane Telemetry'"
        echo "3. Verify Redis is running: redis-cli ping"
        echo "4. Start the processing server: python scripts/server_ctl.py start"
        echo ""
        echo "Extension commands (Cmd+Shift+P):"
        echo "  - Blueplane: Show Session Status"
        echo "  - Blueplane: Start New Session"
        echo "  - Blueplane: Stop Current Session"
    fi
else
    if [ "$DRY_RUN" = true ]; then
        echo -e "   ${MAGENTA}[DRY RUN]${NC} Cursor CLI not available - would need manual installation"
        echo ""
        echo -e "${MAGENTA}================================${NC}"
        echo -e "${MAGENTA}DRY RUN Complete!${NC}"
        echo -e "${MAGENTA}================================${NC}"
        echo ""
        echo "No changes were made. Run without --dry-run to package extension."
    else
        echo -e "   ${YELLOW}⚠️  Cursor CLI not available${NC}"
        echo ""
        echo -e "${YELLOW}================================${NC}"
        echo -e "${YELLOW}Manual Installation Required${NC}"
        echo -e "${YELLOW}================================${NC}"
        echo ""
        echo "The extension has been packaged as: $VSIX_FILE"
        echo ""
        echo "To install manually:"
        echo "1. Open Cursor"
        echo "2. Go to Extensions (Cmd+Shift+X)"
        echo "3. Click '...' menu → Install from VSIX"
        echo "4. Select: $EXTENSION_DIR/$VSIX_FILE"
        echo "5. Restart Cursor"
    fi
fi

echo ""
echo -e "${BLUE}Configuration:${NC}"
echo "  Redis: localhost:6379 (default)"
echo "  Config: $CONFIG_FILE"
echo "  Sessions: ~/.blueplane/cursor-session/"
echo ""
