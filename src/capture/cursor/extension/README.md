# Blueplane Cursor Extension

VSCode extension for Cursor IDE that provides session management for telemetry capture.

## Features

- **Session Management**: Generates unique session IDs and manages environment variables
- **Redis Integration**: Sends session events to Redis Streams message queue
- **Status Bar**: Shows active session status

**Note**: Database monitoring of Cursor's SQLite databases is handled by the Python processing server, not this extension.

## Building

```bash
npm install
npm run compile
```

## Development

```bash
npm run watch
```

Then press F5 in VSCode to launch Extension Development Host.

## Installation

1. Build the extension:
   ```bash
   npm install
   npm run compile
   ```

2. Package as VSIX (optional):
   ```bash
   npx vsce package
   ```

3. Install in Cursor:
   - Open Cursor
   - Extensions > Install from VSIX
   - Select the `.vsix` file

## Commands

- `Blueplane: Show Session Status` - Display current session info
- `Blueplane: Start New Session` - Start a new telemetry session
- `Blueplane: Stop Current Session` - Stop the current session

## Configuration

Settings available in Cursor preferences:

- `blueplane.enabled`: Enable/disable telemetry capture (default: true)
- `blueplane.redisHost`: Redis server host (default: localhost)
- `blueplane.redisPort`: Redis server port (default: 6379)

## Architecture

See parent documentation for details on the overall system architecture.
