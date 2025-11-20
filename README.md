<!--
Copyright © 2025 Sierra Labs LLC
SPDX-License-Identifier: AGPL-3.0-only
License-Filename: LICENSE
-->

# Blueplane Telemetry Core

> Local telemetry and analytics for AI-assisted coding

[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%203.0-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## Overview

Blueplane Telemetry Core is an open-source system for capturing, processing, and analyzing telemetry from AI coding assistants like Claude Code, Cursor. It provides deep insights into your AI-assisted development workflow while maintaining strict privacy standards—all data stays local on your machine.

### Key Features

- **Privacy-First**: All data stays local, no cloud transmission, sensitive content hashed
- **Multi-Platform**: Supports Claude Code, Cursor, and extensible to other AI assistants
- **Real-Time Analytics**: Sub-second metrics updates with async processing pipeline
- **Rich Insights**: Track acceptance rates, productivity, tool usage, and conversation patterns
- **Zero Configuration**: Embedded databases (SQLite, Redis) with minimal setup required
- **Multiple Interfaces**: CLI, MCP Server, and Web Dashboard for accessing your data

## Architecture

Blueplane Telemetry Core is built on a three-layer architecture:

- **Layer 1: Capture** - Lightweight hooks and monitors that capture telemetry events from IDEs
- **Layer 2: Processing** - High-performance async pipeline for event processing and storage
- **Layer 3: Interfaces** - CLI, MCP Server, and Dashboard for data access and visualization

See [Architecture Overview](./docs/ARCHITECTURE.md) for detailed information.

## Quick Start

### Installation (Cursor)

**Prerequisites:**

- Python 3.11+
- Redis server
- Cursor IDE

```bash
# 1. Clone the repository
git clone https://github.com/blueplane-ai/bp-telemetry-core.git
cd bp-telemetry-core

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Start Redis server
redis-server

# 4. Initialize Redis streams
python scripts/init_redis.py

# 5. Initialize SQLite database
python scripts/init_database.py

# 6. Install and activate Cursor extension (required for session management and telemetry)
cd extension
npm install
npm run compile
# Then install the VSIX in Cursor via Extensions panel

# Note: The extension handles session management and event capture.
# Database monitoring is handled by the Python processing server (step 8).

# 7. Configure Cursor for telemetry
# In Cursor: Open Command Palette (Cmd+Shift+P / Ctrl+Shift+P)
# Run: "Developer: Set Log Level" → Select "Trace"
# This enables detailed logging (optional, for debugging)

# 8. Start the processing server (in a separate terminal)
cd ../..
python scripts/start_server.py

# The processing server includes:
# - Fast path consumer (Redis → SQLite)
# - Database monitor (polls Cursor SQLite databases)
# - Session monitor (tracks active sessions from Redis)

# 9. Verify installation
# Check extension is active in Cursor: Extensions → Blueplane Telemetry
# Check processing server logs for any errors
# Monitor Redis: redis-cli XLEN telemetry:events
```

### Installation (Claude Code)

**Prerequisites:**

- Python 3.11+
- Redis server
- Claude Code IDE

```bash
# 1. Clone the repository
git clone https://github.com/blueplane-ai/bp-telemetry-core.git
cd bp-telemetry-core

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Start Redis server
redis-server

# 4. Initialize Redis streams
python scripts/init_redis.py

# 5. Initialize SQLite database
python scripts/init_database.py

# 6. Install Claude Code hooks
# TODO: Add Claude Code installation instructions

# 7. Start the processing server (in a separate terminal)
python scripts/start_server.py

# 8. Verify installation
# TODO: Add Claude Code verification steps
```

### Verification (Cursor)

After installation, the extension and database monitor will automatically capture events as you work in Cursor:

```bash
# Check Redis queue
redis-cli XLEN telemetry:events

# View recent events
redis-cli XREAD COUNT 5 STREAMS telemetry:events 0-0

# Check SQLite database (events are stored here)
python -c "
from src.processing.database.sqlite_client import SQLiteClient
from pathlib import Path
client = SQLiteClient(str(Path.home() / '.blueplane' / 'telemetry.db'))
with client.get_connection() as conn:
    cursor = conn.execute('SELECT COUNT(*) FROM raw_traces')
    print(f'Total events in database: {cursor.fetchone()[0]}')
"

# Run end-to-end test
python scripts/test_end_to_end.py
```

## Use Cases

### For Individual Developers

- Track your productivity patterns over time
- Understand which AI suggestions you accept vs. reject
- Identify areas where AI helps most
- Optimize your workflow based on data

### For Researchers

- Study AI-assisted coding patterns
- Measure acceptance rates and productivity impacts
- Analyze workflow optimization opportunities
- Research human-AI collaboration dynamics

## Components

### Layer 1: Capture

Lightweight telemetry capture that integrates with your IDE:

- **IDE Hooks**: Capture events from Claude Code and other platforms (Claude Code uses hooks)
- **Session Management**: Cursor extension manages session IDs and captures telemetry events
- **Database Monitor**: Python processing server monitors Cursor's SQLite databases (runs in Layer 2)
- **Message Queue**: Reliable event delivery to Layer 2

[Learn more →](./docs/architecture/layer1_capture.md)

### Layer 2: Processing ✅

High-performance async pipeline for event processing:

- **Fast Path**: Low-latency raw event ingestion (<10ms P95) - ✅ Implemented
- **Slow Path**: Async workers for metrics calculation and conversation reconstruction (coming soon)
- **Storage**: SQLite for raw traces and conversations, Redis for real-time metrics and message queue

[Learn more →](./docs/architecture/layer2_async_pipeline.md)

### Layer 3: Interfaces

Multiple ways to access your telemetry data:

- **CLI**: Rich terminal interface with tables and charts
- **MCP Server**: Enable AI assistants to become telemetry-aware
- **Dashboard**: Web-based visualization and analytics (coming soon)

[Learn more →](./docs/architecture/layer3_cli_interface.md)

## Privacy & Security

Blueplane Telemetry Core is designed with privacy as the top priority:

### Local-Only Architecture

- All data stored locally on your machine
- No network transmission of telemetry data
- No cloud services or external dependencies
- You own and control all your data

## Documentation

- [Architecture Overview](./docs/ARCHITECTURE.md) - System design and component details
- [Layer 1: Capture](./docs/architecture/layer1_capture.md) - Event capture specifications
- [Layer 2: Processing](./docs/architecture/layer2_async_pipeline.md) - Async pipeline architecture
- [Layer 3: CLI Interface](./docs/architecture/layer3_cli_interface.md) - Command-line interface documentation
- [Layer 3: MCP Server](./docs/architecture/layer3_mcp_server.md) - Model Context Protocol integration
- [Database Architecture](./docs/architecture/layer2_db_architecture.md) - Storage design details

## Performance

Blueplane Telemetry Core is optimized for minimal overhead:

- **Fast Path Ingestion**: <10ms latency at P95 (per batch of 100 events)
- **Memory Footprint**: ~50MB baseline
- **Storage Efficiency**: zlib compression (7-10x ratio) for raw traces
- **Real-Time Metrics**: Sub-second updates (coming soon)

## Technology Stack

- **Languages**: Python 3.11+, TypeScript (Extension)
- **Databases**: SQLite (raw traces + conversations), Redis (message queue + metrics)
- **CLI**: Rich, Plotext, Click (coming soon)
- **Async**: asyncio, redis-py
- **Web**: FastAPI, React (Dashboard - coming soon)

## Roadmap

### Phase 1: MVP (Current)

- [x] **Layer 1 capture for Cursor** (✅ Complete)
  - [x] TypeScript VSCode extension (session management and event capture)
  - [x] Database monitoring (Python processing server)
  - [x] Redis Streams message queue
  - [x] Installation scripts
- [ ] Layer 1 capture for Claude Code
- [x] **Layer 2 async pipeline** (✅ Fast Path Complete)
  - [x] Fast path consumer (Redis Streams → SQLite)
  - [x] SQLite database with compression
  - [x] CDC event publishing
  - [ ] Slow path workers (metrics, conversations)
- [ ] Layer 3 CLI interface
- [ ] Core metrics and analytics
- [ ] MCP Server implementation
- [ ] Web Dashboard (basic)

### Phase 2: Analytics & Insights

- [ ] Advanced metrics derivation
- [ ] Conversation reconstruction
- [ ] AI-powered insights
- [ ] Pattern recognition
- [ ] Workflow optimization suggestions

## Contributing

We welcome contributions! See the documentation in [./docs/](./docs/) for technical details.

### Development Setup

```bash
# Clone repository
git clone https://github.com/blueplane-ai/bp-telemetry-core.git
cd bp-telemetry-core

# Install development dependencies
pip install -r requirements.txt
pip install pytest pytest-asyncio black mypy

# Run tests
pytest src/capture/tests/

# Format code
black src/

# Type check
mypy src/
```

### Project Structure

```
bp-telemetry-core/
├── src/
│   ├── capture/              # Layer 1 implementation ✅
│   │   ├── shared/           # Shared components
│   │   │   ├── queue_writer.py
│   │   │   ├── event_schema.py
│   │   │   ├── config.py
│   │   │   └── privacy.py
│   │   ├── cursor/           # Cursor platform
│   │   │   └── extension/    # VSCode extension (handles telemetry)
│   │   └── claude_code/      # Claude Code platform
│   │       └── hooks/        # Hook scripts for Claude Code
│   └── processing/           # Layer 2 implementation ✅
│       ├── database/         # SQLite client and schema
│       │   ├── sqlite_client.py
│       │   ├── schema.py
│       │   └── writer.py
│       ├── fast_path/       # Fast path consumer
│       │   ├── consumer.py
│       │   ├── batch_manager.py
│       │   └── cdc_publisher.py
│       └── server.py        # Main processing server
├── config/
│   ├── redis.yaml           # Redis configuration
│   └── privacy.yaml         # Privacy settings
├── scripts/
│   ├── init_redis.py        # Initialize Redis streams
│   ├── init_database.py     # Initialize SQLite database
│   ├── start_server.py      # Start processing server
│   ├── install_claude_code.py # Install Claude Code hooks
│   ├── test_end_to_end.py   # End-to-end test
│   └── test_database_traces.py
├── docs/
│   └── architecture/        # Architecture docs
└── README.md
```

## License

AGPL-3.0 License - see [LICENSE](./LICENSE) file for details.

Copyright © 2025 Sierra Labs LLC

## Acknowledgments

- Inspired by the need for better understanding of AI-assisted coding workflows
- Built with privacy and developer control as core principles
- Thanks to the Claude Code and Cursor communities for feedback and insights

## Support

- **Documentation**: [Full Documentation](./docs/)
- **Issues**: Report issues via github
- **Questions**: Refer to documentation or ask a contributor

---
