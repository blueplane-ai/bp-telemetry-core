# Blueplane Server Management Skill

This skill provides comprehensive knowledge for managing the Blueplane telemetry processing server using `server_ctl.py`.

## What This Skill Covers

- **Server Lifecycle**: Start, stop, restart operations
- **Daemon Management**: Running server in background vs foreground
- **Log Monitoring**: Real-time log viewing and analysis
- **Status Checking**: Server health and system status
- **Troubleshooting**: Common issues and solutions
- **Development Workflow**: Integration with git, testing, debugging

## When to Use This Skill

Use this skill when you need to:
- Start/stop/restart the telemetry server
- Check if the server is running
- Monitor server logs for debugging
- Troubleshoot server issues
- Verify changes after code updates
- Manage the server during development

## Quick Commands

```bash
# Most common operations
python scripts/server_ctl.py restart --daemon     # Restart as daemon
python scripts/server_ctl.py status --verbose     # Check detailed status
tail -f ~/.blueplane/server.log                   # Monitor logs
```

## Skill Activation

This skill is automatically available when working in the bp-telemetry-core repository. Invoke it by:
- Asking about server management
- Requesting help with server_ctl.py
- Asking about logs or monitoring
- Troubleshooting server issues

## Files

- `SKILL.md`: Complete skill documentation with all commands and workflows
