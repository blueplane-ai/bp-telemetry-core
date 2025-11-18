# Blueplane CLI

Privacy-first command-line interface for AI coding telemetry analytics.

## Installation

### Using uv (Recommended)

```bash
# Install as a global tool
uv tool install blueplane-cli

# Or install from local directory
cd src/cli
uv tool install .
```

### Using pip

```bash
# Basic installation
pip install blueplane-cli

# With all optional features
pip install "blueplane-cli[all]"

# Specific features
pip install "blueplane-cli[charts]"      # ASCII charts support
pip install "blueplane-cli[websocket]"   # Real-time monitoring
pip install "blueplane-cli[export]"      # Advanced export formats
```

### Development Installation

```bash
cd src/cli
pip install -e ".[dev]"
```

## Quick Start

```bash
# Check system status
blueplane doctor

# View current metrics
blueplane metrics

# List recent sessions
blueplane sessions

# Analyze a specific session
blueplane analyze sess_abc123

# Watch real-time metrics
blueplane watch --metrics

# Export data
blueplane export -f csv -o data.csv

# Get help
blueplane --help
```

## Shell Completion

Enable tab completion for your shell:

```bash
# Bash
blueplane completion bash >> ~/.bashrc

# Zsh
blueplane completion zsh >> ~/.zshrc

# Fish
blueplane completion fish > ~/.config/fish/completions/blueplane.fish
```

## Configuration

The CLI can be configured via:

1. **Configuration file**: `~/.blueplane/cli/config.yaml`
2. **Environment variables**:
   - `BLUEPLANE_SERVER`: Server URL (default: http://localhost:7531)
   - `BLUEPLANE_FORMAT`: Default output format (table/json/chart)
   - `BLUEPLANE_DEBUG`: Enable debug mode
   - `NO_COLOR`: Disable colored output

3. **Command-line options**: Override any setting per command

## Commands

### `blueplane metrics`
Display performance metrics for coding sessions.

```bash
blueplane metrics --period 7d --format chart
```

### `blueplane sessions`
List and filter coding sessions.

```bash
blueplane sessions --platform claude --min-acceptance 0.7
```

### `blueplane analyze`
Deep analysis of a specific session.

```bash
blueplane analyze sess_abc123 --verbose --tools --files
```

### `blueplane insights`
Get AI-powered recommendations.

```bash
blueplane insights --type productivity --priority high
```

### `blueplane export`
Export telemetry data for external analysis.

```bash
blueplane export -f parquet -o telemetry.parquet --anonymize
```

### `blueplane config`
Manage CLI configuration.

```bash
blueplane config --list
blueplane config --set server.timeout 60
```

### `blueplane watch`
Real-time monitoring dashboard.

```bash
blueplane watch --metrics --interval 5
```

## Output Formats

### Table (Default)
Beautiful formatted tables using Rich library.

### JSON
Structured JSON output for scripting.

```bash
blueplane metrics --format json | jq '.metrics.acceptance_rate'
```

### Chart
ASCII charts for visual representation.

```bash
blueplane sessions --format chart
```

## Examples

### Daily Report Script

```bash
#!/bin/bash
DATE=$(date +%Y-%m-%d)
blueplane export -f csv -o "report_${DATE}.csv" --start "$DATE"
blueplane insights --type productivity > "insights_${DATE}.txt"
```

### CI/CD Integration

```yaml
- name: Check Code Quality Metrics
  run: |
    ACCEPTANCE=$(blueplane metrics --format json | jq '.metrics.acceptance_rate')
    if (( $(echo "$ACCEPTANCE < 0.6" | bc -l) )); then
      echo "Low acceptance rate: $ACCEPTANCE"
      exit 1
    fi
```

## Troubleshooting

### Connection Issues

```bash
# Check server status
blueplane ping

# Run diagnostics
blueplane doctor

# Enable debug mode
BLUEPLANE_DEBUG=1 blueplane metrics
```

### Cache Issues

```bash
# Clear cache
rm -rf ~/.blueplane/cli/cache

# Disable cache temporarily
blueplane metrics --no-cache
```

## License

Copyright © 2025 Sierra Labs LLC
Licensed under AGPL-3.0-only