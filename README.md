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
- **Zero Configuration**: Embedded databases (DuckDB, SQLite, Redis) with no setup required
- **Multiple Interfaces**: CLI, MCP Server, and Web Dashboard for accessing your data

## Architecture

Blueplane Telemetry Core is built on a three-layer architecture:

- **Layer 1: Capture** - Lightweight hooks and monitors that capture telemetry events from IDEs
- **Layer 2: Processing** - High-performance async pipeline for event processing and storage
- **Layer 3: Interfaces** - CLI, MCP Server, and Dashboard for data access and visualization

See [Architecture Overview](./docs/ARCHITECTURE.md) for detailed information.

## Quick Start

### Installation

TBD

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

- **IDE Hooks**: Capture events from Claude Code, Cursor, and other platforms
- **Database Monitor**: Track database changes for platforms like Cursor
- **Message Queue**: Reliable event delivery to Layer 2

[Learn more →](./docs/architecture/layer1_capture.md)

### Layer 2: Processing

High-performance async pipeline for event processing:

- **Fast Path**: Zero-latency raw event ingestion (<1ms P95)
- **Slow Path**: Async workers for metrics calculation and conversation reconstruction
- **Storage**: DuckDB for raw traces, SQLite for conversations, Redis for real-time metrics

[Learn more →](./docs/architecture/layer2_async_pipeline.md)

### Layer 3: Interfaces

Multiple ways to access your telemetry data:

- **CLI**: Rich terminal interface with tables and charts
- **MCP Server**: Enable AI assistants to become telemetry-aware
- **Dashboard**: Web-based visualization and analytics (coming soon)

[Learn more →](./docs/architecture/layer3_cli_interface.md)

## Privacy & Security

Blueplane Telemetry Core is designed with privacy as the top priority:

### What We DON'T Capture

- Source code content
- File names or full paths
- User prompts (text content)
- API keys or credentials
- Personal information

### What We DO Capture

- Timing and performance metrics
- Tool usage patterns
- File extensions only
- Acceptance/rejection events
- Session metadata
- Model information

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

- **Fast Path Ingestion**: <1ms latency at P95
- **Memory Footprint**: ~50MB baseline
- **Storage Efficiency**: Columnar compression for raw traces
- **Real-Time Metrics**: Sub-millisecond dashboard updates

## Technology Stack

- **Languages**: Python 3.11+, TypeScript (Dashboard)
- **Databases**: DuckDB, SQLite, Redis
- **CLI**: Rich, Plotext, Click
- **Async**: asyncio, aiohttp, httpx
- **Web**: FastAPI, React (Dashboard)

## Roadmap

### Phase 1: MVP (Current)

- [ ] Layer 1 capture for Claude Code and Cursor
- [ ] Layer 2 async pipeline with fast/slow paths
- [ ] Layer 3 CLI interface
- [ ] Core metrics and analytics
- [ ] MCP Server implementation
- [ ] Web Dashboard (basic)

## Contributing

We welcome contributions! See the documentation in [./docs/](./docs/) for technical details.

### Development Setup

TBD

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
