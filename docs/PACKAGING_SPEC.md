# Blueplane Telemetry Core - Packaging and Installation Specification

## Version 1.0 - macOS Focus

## Executive Summary

This specification defines the packaging, distribution, and installation strategy for Blueplane Telemetry Core, a privacy-first telemetry system for AI-assisted coding. The primary distribution method uses Docker containers for the processing layer while maintaining direct host access for telemetry capture from Claude Code and Cursor.

## 1. System Requirements

### 1.1 Prerequisites

- **Operating System**: macOS 11+ (Big Sur or later)
- **Architecture**: Intel x64 or Apple Silicon (ARM64)
- **Docker Desktop**: Version 4.0+
- **Python**: 3.9+ (for development and non-containerized fallback)
- **Disk Space**: Minimum 2GB available
- **Memory**: Minimum 4GB RAM (8GB recommended)

### 1.2 Target Applications

- **Claude Code**: Claude desktop application with hooks support
- **Cursor**: Cursor IDE (VSCode fork) with extension support

## 2. Architecture Overview

### 2.1 Component Topology

```
Host System (macOS)
│
├── Claude Code Application
│   └── ~/.claude/projects/ (JSONL transcripts) [READ]
│       └── ~/.claude/hooks/telemetry/ (Hooks) [INSTALLED]
│
├── Cursor Application
│   ├── ~/Library/Application Support/Cursor/User/globalStorage/state.vscdb [READ]
│   │   └── Table: cursorDiskKV (global conversation data)
│   ├── ~/Library/Application Support/Cursor/User/workspaceStorage/*/state.vscdb [READ]
│   │   └── Table: ItemTable (workspace-specific data)
│   └── Extension (VSIX) [INSTALLED]
│
├── Docker Desktop
│   ├── Redis Container (official redis:7-alpine)
│   └── Processing Server Container (custom Python)
│
└── Data Storage
    └── ~/.blueplane/ [READ/WRITE]
        ├── telemetry.db (SQLite)
        ├── config/*.yaml
        └── workspace_db_cache.json
```

### 2.2 Data Flow

1. **Capture Layer**: Claude hooks and Cursor extension write events to Redis streams
2. **Processing Layer**: Docker containers process events and store in SQLite
3. **Access Layer**: CLI reads from SQLite and Redis for analytics

## 3. Docker Container Architecture

### 3.1 Container Definitions

#### Redis Container

```yaml
service: redis
image: redis:7-alpine
ports:
  - "6379:6379"
volumes:
  - redis-data:/data
command: redis-server --appendonly yes
healthcheck:
  test: ["CMD", "redis-cli", "ping"]
  interval: 5s
  timeout: 3s
  retries: 5
```

#### Processing Server Container

```yaml
service: blueplane-server
build:
  context: .
  dockerfile: docker/Dockerfile.server
depends_on:
  redis:
    condition: service_healthy
volumes:
  # Data storage (read/write)
  - ~/.blueplane:/data/blueplane:rw

  # Claude Code monitoring (read-only)
  - ~/.claude/projects:/capture/claude/projects:ro

  # Cursor monitoring (read-only)
  - ~/Library/Application Support/Cursor:/capture/cursor:ro

  # Workspace directory (configurable, read-only)
  - ${WORKSPACE_DIR:-~/Dev}:/workspace:ro
environment:
  - REDIS_HOST=redis
  - REDIS_PORT=6379
  - BLUEPLANE_DATA_DIR=/data/blueplane
  - CLAUDE_PROJECTS_DIR=/capture/claude/projects
  - CURSOR_DATA_DIR=/capture/cursor
  - WORKSPACE_ROOT=/workspace
  - LOG_LEVEL=${LOG_LEVEL:-INFO}
restart: unless-stopped
```

### 3.2 Dockerfile for Processing Server

```dockerfile
# docker/Dockerfile.server
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN useradd -m -u 1000 blueplane

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/

# Copy configuration files (default config.yaml and schema)
# User overrides are mounted from ~/.blueplane/config.yaml at runtime
COPY config/config.yaml ./config/config.yaml
COPY config/config.schema.yaml ./config/config.schema.yaml

# Set ownership
RUN chown -R blueplane:blueplane /app

# Switch to non-root user
USER blueplane

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Entry point
ENTRYPOINT ["python", "-m", "src.processing.server"]
```

**Configuration Loading**: The Python server loads config from `/app/config/config.yaml` (bundled default) but will prefer `/data/blueplane/config.yaml` (user override) if mounted. See Section 8.3 for configuration precedence.

## 4. Python Package Structure

### 4.1 Package Layout

```
bp-telemetry-core/
├── requirements.txt
├── pyproject.toml (planned)
├── src/
│   ├── capture/
│   │   ├── __init__.py
│   │   ├── claude_code/
│   │   │   ├── __init__.py
│   │   │   ├── hook_base.py
│   │   │   └── hooks/
│   │   │       ├── session_start.py
│   │   │       ├── session_end.py
│   │   │       ├── user_prompt_submit.py
│   │   │       ├── pre_tool_use.py
│   │   │       ├── post_tool_use.py
│   │   │       ├── pre_compact.py
│   │   │       └── stop.py
│   │   ├── cursor/
│   │   │   ├── __init__.py
│   │   │   ├── hook_base.py
│   │   │   ├── extension/
│   │   │   │   ├── package.json
│   │   │   │   ├── tsconfig.json
│   │   │   │   ├── src/           # TypeScript source
│   │   │   │   ├── out/           # Compiled JavaScript (gitignored)
│   │   │   │   └── *.vsix         # Built VSIX package (gitignored)
│   │   │   └── hooks/
│   │   │       ├── before_submit_prompt.py
│   │   │       ├── after_agent_response.py
│   │   │       ├── before_shell_execution.py
│   │   │       └── ...
│   │   └── shared/
│   │       ├── __init__.py
│   │       ├── config.py
│   │       ├── event_schema.py
│   │       ├── privacy.py
│   │       ├── project_utils.py
│   │       └── queue_writer.py
│   ├── processing/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── claude_code/
│   │   ├── cursor/
│   │   ├── common/
│   │   ├── database/
│   │   ├── metrics/
│   │   └── slow_path/
│   ├── cli/
│   │   ├── __init__.py (planned)
│   │   ├── main.py (planned)
│   │   └── config/
│   └── mcp/
│       └── (MCP server integration)
├── scripts/
│   ├── install_claude_hooks.py
│   ├── install_cursor.py
│   ├── init_database.py
│   ├── init_redis.py
│   ├── verify_installation.py
│   └── start_server.py
├── tests/
├── config/
├── docs/
├── docker/ (planned)
│   ├── Dockerfile.server
│   └── docker-compose.yml
└── installers/ (planned)
    └── install.sh
```

**Note**: The current structure uses a flat `src/` organization without a `blueplane/` namespace package. This simplifies development imports and allows direct module access (e.g., `from src.capture.shared import config`).

### 4.2 pyproject.toml

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "blueplane-telemetry"
version = "0.1.0"
description = "Privacy-first telemetry for AI-assisted coding"
authors = [{name = "Sierra Labs LLC", email = "support@blueplane.ai"}]
license = {text = "AGPL-3.0-only"}
requires-python = ">=3.9"
dependencies = [
    "redis>=4.6.0",
    "aiosqlite>=0.19.0",
    "pyyaml>=6.0",
    "click>=8.0",
    "rich>=13.0",
    "fastapi>=0.104.0",
    "uvicorn>=0.24.0",
    "watchdog>=3.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "black>=23.0",
    "mypy>=1.0",
    "ruff>=0.1.0",
]

[project.scripts]
bp = "src.cli.main:cli"
bp-server = "src.processing.server:main"

[tool.setuptools.packages.find]
where = ["."]
include = ["src*"]

[tool.setuptools.package-data]
# Include config files from config/ directory
"config" = ["*.yaml", "*.yml"]
# Include any YAML/JSON files in src/ tree (for future use)
"src" = ["*.yaml", "*.yml", "*.json"]
```

**Configuration Files**: The `config/` directory containing `config.yaml` and `config.schema.yaml` is included in the Python package. When installed via pip, these files are available at the package installation location. The Python code searches multiple locations (see Section 8.3) to find configuration files.

**Note**: The package structure uses direct `src.*` imports rather than a `blueplane.*` namespace. Entry points reference `src.cli.main` and `src.processing.server` directly. Dependencies reflect the actual `requirements.txt` in use.

## 5. Cursor Extension Packaging

### 5.1 VSIX Building

```bash
#!/bin/bash
# scripts/build_cursor_extension.sh

cd src/capture/cursor/extension

# Install dependencies
npm install

# Build VSIX (compile + copy config happens automatically via vscode:prepublish)
npx vsce package

echo "VSIX built: src/capture/cursor/extension/blueplane-cursor-telemetry-*.vsix"
```

**Configuration Bundling**: The `package.json` includes a `copy-config` script that runs automatically during `vscode:prepublish`:

```json
{
  "scripts": {
    "vscode:prepublish": "npm run compile && npm run copy-config",
    "copy-config": "mkdir -p out/config && cp ../../../../config/config.yaml out/config/config.yaml"
  },
  "files": ["out/**/*", "config/**/*"]
}
```

This ensures `config.yaml` is copied to `out/config/` and included in the VSIX package. At runtime, the extension searches for config in this order (highest to lowest precedence):

1. **User override**: `~/.blueplane/config.yaml` (user override, highest precedence)
2. **Bundled config**: `out/config/config.yaml` (relative to extension installation - works in VSIX)
3. **Development config**: Project root `config/config.yaml` (for development mode only)

The extension uses `__dirname` (which points to `out/` where `extension.js` lives) to locate the bundled config, ensuring it works correctly in both VSIX installations and development mode.

**Convention**: The VSIX file is built directly in the extension directory (`src/capture/cursor/extension/`) and should be gitignored. This keeps build artifacts colocated with their source.

### 5.2 Extension Installation

```bash
# Install in Cursor (command line)
cursor --install-extension src/capture/cursor/extension/*.vsix

# Or manual installation via Cursor UI:
# 1. Open Cursor
# 2. Cmd+Shift+P → "Install from VSIX"
# 3. Navigate to src/capture/cursor/extension/
# 4. Select blueplane-cursor-telemetry-*.vsix
```

### 5.3 Auto-Update Strategy (Fast-Follow)

**Option 1: GitHub Release Checking**

- Extension periodically checks GitHub releases API
- Notifies user when new version available
- Downloads and prompts for installation

**Option 2: Custom Update Server**

- Host simple version manifest on CDN
- Extension checks version on startup
- Auto-download and install with user consent

**Recommendation**: Start with manual updates, implement GitHub checking as fast-follow.

## 6. Claude Hooks Installation

### 6.1 Hook Installation Process

```bash
#!/bin/bash
# Part of installers/install.sh

CLAUDE_HOOKS_DIR="$HOME/.claude/hooks/telemetry"

# Create hooks directory
mkdir -p "$CLAUDE_HOOKS_DIR"

# Copy hook files
cp -r src/capture/claude_code/hooks/* "$CLAUDE_HOOKS_DIR/"

# Set execute permissions
chmod +x "$CLAUDE_HOOKS_DIR"/*.py

# Update settings.json to enable hooks
python3 scripts/install_claude_hooks.py
```

### 6.2 Hooks Verification

```python
# scripts/verify_claude_hooks.py
import json
import os
from pathlib import Path

def verify_hooks():
    hooks_dir = Path.home() / '.claude' / 'hooks' / 'telemetry'
    settings_file = Path.home() / '.claude' / 'settings.json'

    # Check hooks exist
    required_hooks = [
        'session_start.py',
        'session_end.py',
        'user_prompt_submit.py',
        'tool_use_pre.py',
        'tool_use_post.py'
    ]

    for hook in required_hooks:
        if not (hooks_dir / hook).exists():
            return False, f"Missing hook: {hook}"

    # Check settings enabled
    if settings_file.exists():
        with open(settings_file) as f:
            settings = json.load(f)
            if not settings.get('hooksEnabled', False):
                return False, "Hooks not enabled in settings"

    return True, "All hooks installed and enabled"
```

## 7. Unified Installer Implementation

### 7.1 Configuration Installation

The installer must ensure configuration files are properly installed:

```bash
# Install default config to user directory
install_config() {
    echo -e "\n${BLUE}Installing configuration...${NC}"

    BLUEPLANE_CONFIG_DIR="$HOME/.blueplane"
    mkdir -p "$BLUEPLANE_CONFIG_DIR"

    # Copy default config if user config doesn't exist
    if [ ! -f "$BLUEPLANE_CONFIG_DIR/config.yaml" ]; then
        cp config/config.yaml "$BLUEPLANE_CONFIG_DIR/config.yaml"
        echo -e "${GREEN}✓ Default configuration installed${NC}"
        echo -e "  Edit ${BLUE}$BLUEPLANE_CONFIG_DIR/config.yaml${NC} to customize"
    else
        echo -e "${YELLOW}⚠ User config already exists, skipping${NC}"
        echo -e "  Using existing: ${BLUE}$BLUEPLANE_CONFIG_DIR/config.yaml${NC}"
    fi

    # Always copy schema for reference
    cp config/config.schema.yaml "$BLUEPLANE_CONFIG_DIR/config.schema.yaml"
    echo -e "${GREEN}✓ Configuration schema installed${NC}"
}
```

### 7.2 Main Installation Script

```bash
#!/bin/bash
# installers/install.sh

set -e

BLUE='\033[0;34m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}Blueplane Telemetry Core Installer${NC}"
echo "======================================"

# 1. Check prerequisites
check_prerequisites() {
    echo -e "\n${BLUE}Checking prerequisites...${NC}"

    # Check macOS
    if [[ "$OSTYPE" != "darwin"* ]]; then
        echo -e "${RED}Error: This installer is for macOS only${NC}"
        exit 1
    fi

    # Check Docker Desktop
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker Desktop is not installed${NC}"
        echo "Please install from: https://www.docker.com/products/docker-desktop"
        exit 1
    fi

    # Check Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}Error: Python 3.9+ is required${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ All prerequisites met${NC}"
}

# 2. Install Python package
install_python_package() {
    echo -e "\n${BLUE}Installing Python package...${NC}"
    pip3 install --user blueplane-telemetry
    echo -e "${GREEN}✓ Python package installed${NC}"
}

# 3. Setup Docker containers
setup_docker() {
    echo -e "\n${BLUE}Setting up Docker containers...${NC}"

    # Create docker-compose.yml if not exists
    mkdir -p ~/.blueplane
    cp docker/docker-compose.yml ~/.blueplane/

    # Set workspace directory
    read -p "Enter your workspace directory [~/Dev]: " workspace_dir
    workspace_dir=${workspace_dir:-~/Dev}
    echo "WORKSPACE_DIR=$workspace_dir" > ~/.blueplane/.env

    # Start containers
    cd ~/.blueplane
    docker-compose up -d

    echo -e "${GREEN}✓ Docker containers started${NC}"
}

# 4. Install Claude hooks
install_claude_hooks() {
    echo -e "\n${BLUE}Installing Claude Code hooks...${NC}"

    if [ -d "$HOME/.claude" ]; then
        python3 scripts/install_claude_hooks.py
        echo -e "${GREEN}✓ Claude hooks installed${NC}"
    else
        echo -e "${YELLOW}⚠ Claude Code not found, skipping hooks${NC}"
    fi
}

# 5. Install Cursor extension
install_cursor_extension() {
    echo -e "\n${BLUE}Installing Cursor extension...${NC}"

    if command -v cursor &> /dev/null; then
        # Build VSIX
        ./scripts/build_cursor_extension.sh

        # Install extension (find the built VSIX)
        VSIX_PATH=$(find src/capture/cursor/extension -name "*.vsix" -type f | head -1)
        if [ -n "$VSIX_PATH" ]; then
            cursor --install-extension "$VSIX_PATH"
            echo -e "${GREEN}✓ Cursor extension installed${NC}"
        else
            echo -e "${RED}✗ VSIX not found${NC}"
        fi
    else
        echo -e "${YELLOW}⚠ Cursor not found, skipping extension${NC}"
    fi
}

# 6. Initialize databases
initialize_databases() {
    echo -e "\n${BLUE}Initializing databases...${NC}"

    # Initialize SQLite
    python3 scripts/init_database.py

    # Initialize Redis streams
    python3 scripts/init_redis.py

    echo -e "${GREEN}✓ Databases initialized${NC}"
}

# 7. Setup launchd service
setup_service() {
    echo -e "\n${BLUE}Setting up launch service...${NC}"

    # Create launchd plist
    cat > ~/Library/LaunchAgents/io.blueplane.telemetry.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.blueplane.telemetry</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/docker-compose</string>
        <string>-f</string>
        <string>$HOME/.blueplane/docker-compose.yml</string>
        <string>up</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$HOME/.blueplane/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$HOME/.blueplane/logs/stderr.log</string>
</dict>
</plist>
EOF

    # Load service
    launchctl load ~/Library/LaunchAgents/io.blueplane.telemetry.plist

    echo -e "${GREEN}✓ Launch service configured${NC}"
}

# 8. Verify installation
verify_installation() {
    echo -e "\n${BLUE}Verifying installation...${NC}"

    python3 scripts/verify_installation.py

    echo -e "${GREEN}✓ Installation verified${NC}"
}

# Main installation flow
main() {
    check_prerequisites
    install_config
    install_python_package
    setup_docker
    install_claude_hooks
    install_cursor_extension
    initialize_databases
    setup_service
    verify_installation

    echo -e "\n${GREEN}Installation complete!${NC}"
    echo -e "Run ${BLUE}bp status${NC} to check system status"
    echo -e "Run ${BLUE}bp help${NC} for available commands"
    echo -e "\nConfiguration: ${BLUE}$HOME/.blueplane/config.yaml${NC}"
}

main "$@"
```

## 8. Configuration Management

### 8.1 Configuration File Bundling Strategy

All components of Blueplane Telemetry Core use a unified `config.yaml` file located in the project root `config/` directory. This configuration must be bundled appropriately for each packaging target:

#### 8.1.1 Python Package (pip install)

**Location**: `config/config.yaml` and `config/config.schema.yaml` are included in the Python package via `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"config" = ["*.yaml", "*.yml"]
```

**Runtime Loading**: Python code (`src/capture/shared/config.py`) searches for config in this order:

1. `~/.blueplane/config.yaml` (user override, highest precedence)
2. Relative to source code: `config/config.yaml` (development)
3. Package installation location (installed package)
4. `/etc/blueplane/config.yaml` (system-wide)

#### 8.1.2 Docker Container

**Bundling**: Config files are explicitly copied in Dockerfile:

```dockerfile
COPY config/config.yaml ./config/config.yaml
COPY config/config.schema.yaml ./config/config.schema.yaml
```

**Runtime Loading**: Container loads from `/app/config/config.yaml` (bundled default), but user can mount `~/.blueplane/config.yaml` to `/data/blueplane/config.yaml` for overrides.

#### 8.1.3 Cursor Extension (VSIX)

**Bundling**: Config is copied to `out/config/` before VSIX packaging:

```bash
mkdir -p out/config
cp ../../../../config/config.yaml out/config/config.yaml
```

**Runtime Loading**: Extension (`src/capture/cursor/extension/src/config.ts`) searches in this order:

1. `~/.blueplane/config.yaml` (user override, highest precedence)
2. Bundled config: `out/config/config.yaml` (relative to extension installation - works in VSIX)
3. Development config: Project root `config/config.yaml` (for development mode only)

The extension uses `__dirname` to locate the bundled config relative to where `extension.js` is located, ensuring correct behavior in both packaged VSIX and development environments.

**VSIX Package Contents**: Ensure `package.json` includes config files:

```json
{
  "files": ["out/**/*", "config/**/*"]
}
```

#### 8.1.4 Claude Hooks

**Bundling**: Hooks are Python scripts that use the same config loading mechanism as the Python package. Config is loaded from:

1. `~/.blueplane/config.yaml` (user override)
2. Relative to hook location (if hooks are installed from source)
3. Package installation location (if installed via pip)

### 8.2 Configuration Structure

```yaml
# ~/.blueplane/config/main.yaml
version: "1.0"

# Data storage
storage:
  database: ~/.blueplane/telemetry.db
  cache_dir: ~/.blueplane/cache

# Redis connection
redis:
  host: localhost
  port: 6379
  streams:
    claude_code: bp:stream:claude_code
    cursor: bp:stream:cursor
    cdc: bp:stream:cdc

# Processing settings
processing:
  batch_size: 100
  batch_timeout_ms: 100
  worker_count: 4

# Privacy settings
privacy:
  capture_file_content: false
  capture_directory_names: true

# Platform-specific paths
platforms:
  claude_code:
    projects_dir: ~/.claude/projects
  cursor:
    data_dir: ~/Library/Application Support/Cursor

# Workspace configuration
workspace:
  root: ~/Dev
  ignore_patterns:
    - node_modules
    - .git
    - __pycache__

# Logging
logging:
  level: INFO
  file: ~/.blueplane/logs/telemetry.log
  max_size_mb: 100
  backup_count: 5
```

### 8.3 Configuration Precedence

Configuration files are loaded with the following precedence (highest to lowest):

1. **User Override**: `~/.blueplane/config.yaml` (always takes precedence)
2. **Bundled Default**: Component-specific bundled config
   - Python package: Package installation location
   - Docker: `/app/config/config.yaml`
   - Extension: `out/config/config.yaml` (bundled in VSIX)
3. **Schema Defaults**: Values defined in `config.schema.yaml`

**Merging Strategy**: User config (`~/.blueplane/config.yaml`) merges with defaults. Only specified keys override; unspecified keys use defaults from bundled config or schema.

**Installation**: The installer script (`installers/install.sh`) copies `config/config.yaml` to `~/.blueplane/config.yaml` during installation, allowing users to customize settings.

### 8.4 Debug Mode Configuration

```yaml
# ~/.blueplane/config/debug.yaml
# Activated with BP_DEBUG=true environment variable

logging:
  level: DEBUG
  console_output: true
  include_timestamps: true
  include_caller: true

processing:
  log_all_events: true
  dry_run: false

monitoring:
  metrics_interval_s: 10
  health_check_interval_s: 5
```

## 9. Service Management

### 9.1 launchd Configuration (macOS)

```xml
<!-- ~/Library/LaunchAgents/io.blueplane.telemetry.plist -->
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.blueplane.telemetry</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/docker-compose</string>
        <string>-f</string>
        <string>/Users/USERNAME/.blueplane/docker-compose.yml</string>
        <string>up</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>ThrottleInterval</key>
    <integer>30</integer>
    <key>StandardOutPath</key>
    <string>/Users/USERNAME/.blueplane/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/USERNAME/.blueplane/logs/stderr.log</string>
</dict>
</plist>
```

### 9.2 Service Control Commands

```bash
# Start service
launchctl load ~/Library/LaunchAgents/io.blueplane.telemetry.plist

# Stop service
launchctl unload ~/Library/LaunchAgents/io.blueplane.telemetry.plist

# Restart service
launchctl unload ~/Library/LaunchAgents/io.blueplane.telemetry.plist
launchctl load ~/Library/LaunchAgents/io.blueplane.telemetry.plist

# Check status
launchctl list | grep io.blueplane.telemetry
```

## 10. CLI Interface

### 10.1 Command Structure

```bash
bp - Blueplane Telemetry CLI

Commands:
  bp status           # Show system status
  bp start            # Start telemetry services
  bp stop             # Stop telemetry services
  bp restart          # Restart services
  bp stats            # Show telemetry statistics
  bp sessions         # List recent sessions
  bp export           # Export data for analysis
  bp config           # Manage configuration
  bp verify           # Verify installation
  bp logs             # View system logs
  bp debug            # Enable debug mode
```

### 10.2 Implementation Example

```python
# src/blueplane/cli/main.py
import click
from rich.console import Console
from rich.table import Table

console = Console()

@click.group()
def cli():
    """Blueplane Telemetry CLI"""
    pass

@cli.command()
def status():
    """Check system status"""
    # Check Docker containers
    # Check Redis connection
    # Check SQLite database
    # Display status table
    pass

@cli.command()
def stats():
    """Show telemetry statistics"""
    table = Table(title="Telemetry Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    # Fetch stats from database
    # Display in table
    console.print(table)
```

## 11. Distribution Channels

### 11.1 PyPI Distribution

```bash
# Build and upload to PyPI
python -m build
twine upload dist/*

# Users install via pip
pip install blueplane-telemetry
```

### 11.2 Docker Hub Distribution

```bash
# Build and push Docker images
docker build -t blueplane/telemetry-server:latest -f docker/Dockerfile.server .
docker push blueplane/telemetry-server:latest

# docker-compose.yml references published image
image: blueplane/telemetry-server:latest
```

### 11.3 One-Line Installer

```bash
# Install from main branch (latest)
curl -sSL https://raw.githubusercontent.com/blueplane-ai/bp-telemetry-core/main/installers/install.sh | bash

# Install specific version (using Git tags)
curl -sSL https://raw.githubusercontent.com/blueplane-ai/bp-telemetry-core/v1.0.0/installers/install.sh | bash

# Recommended: Review before running
curl -sSL https://raw.githubusercontent.com/blueplane-ai/bp-telemetry-core/main/installers/install.sh -o install.sh
cat install.sh  # Review the script
bash install.sh
```

## 12. Verification and Testing

### 12.1 Installation Verification

```python
# scripts/verify_installation.py
def verify_installation():
    checks = [
        ("Docker", check_docker),
        ("Redis", check_redis),
        ("SQLite Database", check_database),
        ("Claude Hooks", check_claude_hooks),
        ("Cursor Extension", check_cursor_extension),
        ("Python Package", check_python_package),
    ]

    for name, check_func in checks:
        success, message = check_func()
        if success:
            print(f"✓ {name}: {message}")
        else:
            print(f"✗ {name}: {message}")
```

### 12.2 End-to-End Test

```bash
# scripts/test_e2e.sh
#!/bin/bash

# 1. Generate test event in Claude
echo "Test event" > ~/.claude/projects/test/test.jsonl

# 2. Wait for processing
sleep 5

# 3. Check if event appears in database
bp stats | grep "Events processed"

# 4. Clean up
rm -rf ~/.claude/projects/test
```

## 13. Fast-Follow Roadmap

### Phase 1: Core Features (v1.0)

- ✅ Docker-based installation
- ✅ Basic CLI interface
- ✅ Claude hooks and Cursor extension
- ✅ macOS support

### Phase 2: Enhanced Monitoring (v1.1)

- Monitoring dashboard in Python server
- Prometheus metrics export
- Grafana dashboard templates
- Container health monitoring

### Phase 3: Operations (v1.2)

- Backup and restore procedures
- Log aggregation and rotation
- Database migration framework
- Data export formats (CSV, JSON, Parquet)

### Phase 4: Developer Experience (v1.3)

- Hot reload for development
- Development vs production configs
- VSIX auto-update mechanism
- Extension configuration UI

### Phase 5: Platform Expansion (v2.0)

- Linux support
- Windows support (WSL2)
- Additional IDE support (VSCode, IntelliJ)

## 14. Future Packaging Targets

### 14.1 General Configuration Bundling Principles

For any future packaging target (Homebrew, system packages, standalone binaries, etc.), follow these principles:

1. **Always Bundle Default Config**: Include `config/config.yaml` as the default configuration
2. **Respect User Overrides**: User config at `~/.blueplane/config.yaml` always takes precedence
3. **Document Config Location**: Clearly document where bundled config is located for each packaging format
4. **Schema Reference**: Include `config.schema.yaml` for documentation/reference

### 14.2 Homebrew Formula (Future)

```ruby
# Formula would install config to:
# - Default: /opt/homebrew/etc/blueplane/config.yaml (Apple Silicon)
# - Default: /usr/local/etc/blueplane/config.yaml (Intel)
# - User override: ~/.blueplane/config.yaml (always preferred)
```

### 14.3 System Packages (deb/rpm) (Future)

- **Default config**: `/etc/blueplane/config.yaml` (system-wide)
- **User override**: `~/.blueplane/config.yaml` (per-user, takes precedence)
- **Schema**: `/usr/share/doc/blueplane-telemetry/config.schema.yaml`

### 14.4 Standalone Binaries (Future)

- Bundle config as embedded resource or separate file in distribution
- User override at `~/.blueplane/config.yaml` always takes precedence
- Document config location in distribution README

### 14.5 Configuration Search Order (Universal)

All components should search for config in this order:

1. **User Override**: `~/.blueplane/config.yaml` (highest precedence)
2. **Bundled Default**: Component-specific location (package-dependent)
3. **System Default**: `/etc/blueplane/config.yaml` (if applicable)
4. **Schema Defaults**: Hardcoded defaults from `config.schema.yaml`

This ensures consistent behavior across all packaging formats.

## Appendix A: Error Codes

| Code | Description                      | Resolution                 |
| ---- | -------------------------------- | -------------------------- |
| E001 | Docker not installed             | Install Docker Desktop     |
| E002 | Redis connection failed          | Check Docker containers    |
| E003 | Database initialization failed   | Check disk space           |
| E004 | Claude hooks installation failed | Check permissions          |
| E005 | Cursor extension build failed    | Check Node.js installation |

## Appendix B: File Locations

| Component                  | Location                                                                   |
| -------------------------- | -------------------------------------------------------------------------- |
| SQLite Database            | `~/.blueplane/telemetry.db`                                                |
| User Configuration         | `~/.blueplane/config.yaml` (user overrides)                                |
| Default Configuration      | `~/.blueplane/config.schema.yaml` (reference schema)                       |
| Bundled Config (Python)    | Package installation location (via pip)                                    |
| Bundled Config (Docker)    | `/app/config/config.yaml` (inside container)                               |
| Bundled Config (Extension) | Extension installation directory `out/config/config.yaml` (in VSIX)        |
| Logs                       | `~/.blueplane/logs/`                                                       |
| Claude Hooks               | `~/.claude/hooks/telemetry/`                                               |
| Claude Projects            | `~/.claude/projects/`                                                      |
| Cursor User Database       | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`      |
| Cursor Workspace Databases | `~/Library/Application Support/Cursor/User/workspaceStorage/*/state.vscdb` |
| Docker Compose             | `~/.blueplane/docker-compose.yml`                                          |
| Launch Agent               | `~/Library/LaunchAgents/io.blueplane.telemetry.plist`                      |

## Appendix C: Environment Variables

| Variable        | Default     | Description                                 |
| --------------- | ----------- | ------------------------------------------- |
| `WORKSPACE_DIR` | `~/Dev`     | Root directory for workspace monitoring     |
| `BP_DEBUG`      | `false`     | Enable debug mode                           |
| `LOG_LEVEL`     | `INFO`      | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `REDIS_HOST`    | `localhost` | Redis server hostname                       |
| `REDIS_PORT`    | `6379`      | Redis server port                           |

---

**Document Version**: 1.0
**Last Updated**: 2025
**Status**: Implementation Ready
