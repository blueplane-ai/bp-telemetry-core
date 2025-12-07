#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Server control CLI for Blueplane Telemetry processing server.

Provides simple, robust commands for server lifecycle management:
- start: Start server in foreground or daemon mode
- stop: Gracefully stop server with timeout and force option
- restart: Stop then start server
- status: Check server status and health

Handles PID validation, stale lock cleanup, and graceful vs force shutdown.
"""

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

try:
    from src.capture.shared.config import Config
    HAS_CONFIG = True
except ImportError:
    HAS_CONFIG = False

try:
    from src.capture.shared.redis_streams import (
        TELEMETRY_MESSAGE_QUEUE_STREAM,
        CDC_EVENTS_STREAM,
    )
    HAS_STREAM_CONSTANTS = True
except ImportError:
    HAS_STREAM_CONSTANTS = False
    # Fallback values if import fails
    TELEMETRY_MESSAGE_QUEUE_STREAM = "telemetry:message_queue"
    CDC_EVENTS_STREAM = "cdc:events"


class ServerController:
    """Controls Blueplane Telemetry processing server lifecycle."""

    def __init__(self, blueplane_home: Optional[Path] = None):
        """
        Initialize server controller.

        Args:
            blueplane_home: Path to .blueplane directory (default: ~/.blueplane)
        """
        self.blueplane_home = blueplane_home or Path.home() / ".blueplane"
        self.pid_file = self.blueplane_home / "server.pid"
        self.log_file = self.blueplane_home / "server.log"
        self.script_dir = Path(__file__).parent
        self.start_script = self.script_dir / "start_server.py"
        self._max_log_lines: Optional[int] = None

    def get_pid_info(self) -> Optional[Dict[str, Any]]:
        """
        Read PID file and return process information.

        Returns:
            Dictionary with pid, timestamp, process_name, or None if not found/invalid
        """
        if not self.pid_file.exists():
            return None

        try:
            content = self.pid_file.read_text().strip()

            # Try JSON format first (new format)
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    return {
                        "pid": data["pid"],
                        "timestamp": data.get("timestamp"),
                        "process_name": data.get("process_name", "unknown"),
                        "format": "json"
                    }
                else:
                    raise json.JSONDecodeError("Not a dict", content, 0)
            except (json.JSONDecodeError, KeyError, TypeError):
                # Fall back to plain PID (legacy format)
                try:
                    pid = int(content)
                    return {
                        "pid": pid,
                        "timestamp": None,
                        "process_name": "unknown",
                        "format": "legacy"
                    }
                except ValueError:
                    return None

        except Exception as e:
            print(f"Warning: Could not read PID file: {e}", file=sys.stderr)
            return None

    def is_process_running(self, pid: int) -> bool:
        """
        Check if process with given PID is running.

        Args:
            pid: Process ID to check

        Returns:
            True if process is running, False otherwise
        """
        try:
            # Signal 0 checks if process exists without sending actual signal
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def get_process_name(self, pid: int) -> Optional[str]:
        """
        Get process name for given PID.

        Args:
            pid: Process ID

        Returns:
            Process name or None if not found
        """
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "comm="],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def is_stale_pid(self, pid_info: Dict[str, Any]) -> bool:
        """
        Check if PID file is stale (process not running or wrong process).

        Args:
            pid_info: PID information from get_pid_info()

        Returns:
            True if stale, False if valid
        """
        pid = pid_info["pid"]

        # Check if process exists
        if not self.is_process_running(pid):
            return True

        # Check if it's our process (contains "start_server" or "processing.server")
        process_name = self.get_process_name(pid)
        if process_name:
            cmd_result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "args="],
                capture_output=True,
                text=True,
                timeout=2
            )
            if cmd_result.returncode == 0:
                cmd_line = cmd_result.stdout.strip()
                if "start_server" in cmd_line or "processing.server" in cmd_line:
                    return False

        # If we get here, it's either not our process or we couldn't determine
        return True

    def cleanup_stale_pid(self) -> bool:
        """
        Clean up stale PID file if it exists.

        Returns:
            True if cleaned up, False if no cleanup needed
        """
        pid_info = self.get_pid_info()
        if not pid_info:
            return False

        if self.is_stale_pid(pid_info):
            print(f"Removing stale PID file (PID {pid_info['pid']} not running)")
            self.pid_file.unlink()
            return True

        return False

    def check_database_status(self) -> Dict[str, Any]:
        """
        Check database connection status.

        Returns:
            Dictionary with database status information
        """
        db_path = self.blueplane_home / "telemetry.db"
        result = {
            "path": str(db_path),
            "exists": db_path.exists(),
            "accessible": False,
            "size_bytes": 0,
            "tables": [],
            "error": None,
        }

        if not db_path.exists():
            return result

        try:
            result["size_bytes"] = db_path.stat().st_size

            # Try to connect and query
            conn = sqlite3.connect(str(db_path), timeout=2.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get list of tables
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]
            result["tables"] = tables
            result["accessible"] = True

            # Get some stats if tables exist
            stats = {}
            for table in tables[:5]:  # Limit to first 5 tables
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    stats[table] = count
                except sqlite3.Error:
                    stats[table] = "error"
            result["table_counts"] = stats

            conn.close()

        except sqlite3.Error as e:
            result["error"] = str(e)
        except Exception as e:
            result["error"] = str(e)

        return result

    def check_redis_status(self) -> Dict[str, Any]:
        """
        Check Redis connection status.

        Returns:
            Dictionary with Redis status information
        """
        result = {
            "available": False,
            "connected": False,
            "host": "localhost",
            "port": 6379,
            "error": None,
            "info": {},
        }

        if not HAS_REDIS:
            result["error"] = "redis package not installed"
            return result

        # Load config if available
        if HAS_CONFIG:
            try:
                config = Config()
                redis_config = config.redis
                result["host"] = redis_config.host
                result["port"] = redis_config.port
            except Exception as e:
                result["error"] = f"Config load error: {e}"

        result["available"] = True

        try:
            client = redis.Redis(
                host=result["host"],
                port=result["port"],
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
            # Test connection
            client.ping()
            result["connected"] = True

            # Get basic info
            info = client.info()
            result["info"] = {
                "redis_version": info.get("redis_version", "unknown"),
                "connected_clients": info.get("connected_clients", 0),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
            }

            # Check for our streams
            streams = {}
            for stream_name in [TELEMETRY_MESSAGE_QUEUE_STREAM, CDC_EVENTS_STREAM]:
                try:
                    length = client.xlen(stream_name)
                    streams[stream_name] = {"length": length}
                except redis.ResponseError:
                    streams[stream_name] = {"length": 0, "exists": False}
            result["streams"] = streams

            client.close()

        except redis.ConnectionError as e:
            result["error"] = f"Connection failed: {e}"
        except redis.TimeoutError as e:
            result["error"] = f"Connection timeout: {e}"
        except Exception as e:
            result["error"] = str(e)

        return result

    def check_http_endpoint_status(self) -> Dict[str, Any]:
        """
        Check HTTP endpoint status.

        Returns:
            Dictionary with HTTP endpoint status information
        """
        result = {
            "configured": False,
            "enabled": False,
            "host": "127.0.0.1",
            "port": 8787,
            "reachable": False,
            "error": None,
        }

        # Load config if available
        if HAS_CONFIG:
            try:
                config = Config()
                http_config = config.get("http_endpoint", {})
                result["configured"] = True
                result["enabled"] = http_config.get("enabled", True)
                result["host"] = http_config.get("host", "127.0.0.1")
                result["port"] = http_config.get("port", 8787)
            except Exception as e:
                result["error"] = f"Config load error: {e}"
                return result

        if not result["enabled"]:
            return result

        # Try to reach the health endpoint
        try:
            import urllib.request
            import urllib.error

            url = f"http://{result['host']}:{result['port']}/health"
            request = urllib.request.Request(url, method="GET")

            with urllib.request.urlopen(request, timeout=2.0) as response:
                if response.status == 200:
                    result["reachable"] = True
                else:
                    result["error"] = f"Unexpected status: {response.status}"

        except urllib.error.URLError as e:
            result["error"] = f"Connection failed: {e.reason}"
        except urllib.error.HTTPError as e:
            result["error"] = f"HTTP error: {e.code}"
        except TimeoutError:
            result["error"] = "Connection timeout"
        except Exception as e:
            result["error"] = str(e)

        return result

    def get_max_log_lines(self) -> int:
        """
        Get max log lines configuration from config.yaml.

        Returns:
            Maximum number of lines to keep in log file (default: 10000)
        """
        if self._max_log_lines is not None:
            return self._max_log_lines

        # Load from config if available
        if HAS_CONFIG:
            try:
                config = Config()
                max_lines = config.get("logging.max_log_lines", 10000)
                self._max_log_lines = max_lines if max_lines > 0 else 0
                return self._max_log_lines
            except Exception:
                pass

        # Default to 10000 lines
        self._max_log_lines = 10000
        return self._max_log_lines

    def trim_log_file(self, log_file: Optional[Path] = None) -> None:
        """
        Trim log file to max_log_lines, keeping only the most recent lines.

        Args:
            log_file: Path to log file (default: self.log_file)
        """
        log_file = log_file or self.log_file

        if not log_file.exists():
            return

        max_lines = self.get_max_log_lines()

        # If trimming disabled (0) or file doesn't exist, skip
        if max_lines <= 0:
            return

        try:
            # Read all lines from the file
            with open(log_file, 'r') as f:
                lines = f.readlines()

            line_count = len(lines)

            # Only trim if we exceed the limit
            if line_count > max_lines:
                # Keep only the last max_log_lines
                lines_to_keep = lines[-max_lines:]

                # Write back to file with a header indicating trimming occurred
                with open(log_file, 'w') as f:
                    f.write(f"{'='*80}\n")
                    f.write(f"Log trimmed at {datetime.now(timezone.utc).isoformat()}\n")
                    f.write(f"Removed {line_count - max_lines} older lines (kept {max_lines} most recent)\n")
                    f.write(f"{'='*80}\n\n")
                    f.writelines(lines_to_keep)

        except Exception as e:
            # Don't fail the operation if trimming fails
            print(f"Warning: Failed to trim log file: {e}", file=sys.stderr)

    def check_monitor_status(self) -> Dict[str, Any]:
        """
        Check which monitors are configured and their settings.

        Returns:
            Dictionary with monitor configuration information
        """
        result = {
            "config_loaded": False,
            "monitors": {},
            "error": None,
        }

        if not HAS_CONFIG:
            result["error"] = "Config module not available"
            return result

        try:
            config = Config()
            result["config_loaded"] = True

            # Check each monitor's configuration
            monitors = {
                "cursor_database": {
                    "name": "Cursor Database Monitor",
                    "config_key": "cursor_database",
                },
                "cursor_markdown": {
                    "name": "Cursor Markdown Monitor",
                    "config_key": "cursor_markdown",
                },
                "unified_cursor": {
                    "name": "Unified Cursor Monitor",
                    "config_key": "unified_cursor",
                },
                "claude_jsonl": {
                    "name": "Claude Code JSONL Monitor",
                    "config_key": "claude_jsonl",
                },
            }

            for key, info in monitors.items():
                mon_config = config.get_monitoring_config(info["config_key"])
                result["monitors"][key] = {
                    "name": info["name"],
                    "enabled": mon_config.get("enabled", True),  # Default is enabled
                    "poll_interval": mon_config.get(
                        "poll_interval", mon_config.get("poll_interval_seconds")
                    ),
                }

            # Check feature flags
            result["features"] = {
                "duckdb_sink": config.get("features.duckdb_sink.enabled", False),
            }

        except Exception as e:
            result["error"] = str(e)

        return result

    def start(self, daemon: bool = False, verbose: bool = False) -> int:
        """
        Start the server.

        Args:
            daemon: Run in background mode
            verbose: Enable verbose logging

        Returns:
            Exit code (0 = success, non-zero = failure)
        """
        # Check for existing server
        self.cleanup_stale_pid()
        pid_info = self.get_pid_info()

        if pid_info and not self.is_stale_pid(pid_info):
            print(f"Error: Server already running with PID {pid_info['pid']}", file=sys.stderr)
            return 1

        # Ensure blueplane home exists
        self.blueplane_home.mkdir(parents=True, exist_ok=True)

        # Trim log file before starting to prevent unbounded growth
        self.trim_log_file()

        print("Starting Blueplane Telemetry server...")

        if daemon:
            # Run in background with output redirected to log file
            with open(self.log_file, "a") as log:
                log.write(f"\n{'='*80}\n")
                log.write(f"Server started at {datetime.now(timezone.utc).isoformat()}\n")
                log.write(f"{'='*80}\n\n")
                log.flush()

                process = subprocess.Popen(
                    [sys.executable, str(self.start_script)],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True  # Detach from parent
                )

            # Give it a moment to start
            time.sleep(2)

            # Check if it's still running
            if process.poll() is None:
                print(f"✓ Server started in background (PID will be in {self.pid_file})")
                print(f"  Log file: {self.log_file}")
                return 0
            else:
                print("✗ Server failed to start. Check log file:", self.log_file, file=sys.stderr)
                return 1
        else:
            # Run in foreground
            try:
                result = subprocess.run(
                    [sys.executable, str(self.start_script)],
                    check=False
                )
                return result.returncode
            except KeyboardInterrupt:
                print("\nServer interrupted by user")
                return 0

    def stop(self, force: bool = False, timeout: int = 30, verbose: bool = False) -> int:
        """
        Stop the server.

        Args:
            force: Force kill if graceful shutdown fails
            timeout: Timeout in seconds for graceful shutdown
            verbose: Enable verbose output

        Returns:
            Exit code (0 = success, non-zero = failure)
        """
        # Check for running server
        self.cleanup_stale_pid()
        pid_info = self.get_pid_info()

        if not pid_info:
            print("Server is not running (no PID file)")
            return 0

        if self.is_stale_pid(pid_info):
            print(f"Stale PID file found, cleaning up")
            self.pid_file.unlink()
            return 0

        pid = pid_info["pid"]
        print(f"Stopping server (PID {pid})...")

        # Try graceful shutdown first (SIGTERM)
        try:
            os.kill(pid, signal.SIGTERM)
            if verbose:
                print(f"Sent SIGTERM to PID {pid}")
        except ProcessLookupError:
            print("Process already stopped")
            self.pid_file.unlink()
            return 0
        except PermissionError:
            print(f"Error: Permission denied to stop PID {pid}", file=sys.stderr)
            return 1

        # Wait for graceful shutdown
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not self.is_process_running(pid):
                print(f"✓ Server stopped gracefully")
                # Clean up PID file if it still exists
                if self.pid_file.exists():
                    self.pid_file.unlink()
                return 0

            time.sleep(0.5)
            if verbose and int(time.time() - start_time) % 5 == 0:
                print(f"  Waiting for shutdown... ({int(time.time() - start_time)}s)")

        # Graceful shutdown failed
        if force:
            print(f"Graceful shutdown timed out after {timeout}s, forcing kill...")
            try:
                os.kill(pid, signal.SIGKILL)
                time.sleep(1)

                if not self.is_process_running(pid):
                    print(f"✓ Server force killed")
                    if self.pid_file.exists():
                        self.pid_file.unlink()
                    return 0
                else:
                    print(f"✗ Failed to kill process {pid}", file=sys.stderr)
                    return 1

            except ProcessLookupError:
                print("Process stopped during force kill")
                if self.pid_file.exists():
                    self.pid_file.unlink()
                return 0
        else:
            print(f"✗ Graceful shutdown timed out after {timeout}s", file=sys.stderr)
            print(f"  Process {pid} is still running", file=sys.stderr)
            print(f"  Use --force to force kill", file=sys.stderr)
            return 1

    def restart(self, daemon: bool = False, timeout: int = 30, verbose: bool = False) -> int:
        """
        Restart the server (stop then start).

        Args:
            daemon: Run in background mode after restart
            timeout: Timeout for stop operation
            verbose: Enable verbose output

        Returns:
            Exit code (0 = success, non-zero = failure)
        """
        print("Restarting server...")

        # Stop first
        stop_result = self.stop(force=True, timeout=timeout, verbose=verbose)
        if stop_result != 0:
            print("Failed to stop server, aborting restart", file=sys.stderr)
            return stop_result

        # Wait a moment
        time.sleep(2)

        # Start
        return self.start(daemon=daemon, verbose=verbose)

    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human readable size."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"

    def status(self, verbose: bool = False) -> int:
        """
        Check server status.

        Args:
            verbose: Show detailed status information

        Returns:
            Exit code (0 = running, 1 = not running, 2 = error)
        """
        # Check for PID file
        pid_info = self.get_pid_info()

        if not pid_info:
            print("Server Status: NOT RUNNING (no PID file)")
            server_running = False
            exit_code = 1
        elif not self.is_process_running(pid_info["pid"]):
            print(f"Server Status: NOT RUNNING (stale PID {pid_info['pid']})")
            server_running = False
            exit_code = 1
        elif self.is_stale_pid(pid_info):
            print(f"Server Status: NOT RUNNING (PID {pid_info['pid']} is wrong process)")
            server_running = False
            exit_code = 1
        else:
            pid = pid_info["pid"]
            print(f"Server Status: RUNNING (PID {pid})")
            server_running = True
            exit_code = 0

            if verbose:
                print(f"  PID file: {self.pid_file}")
                if pid_info["timestamp"]:
                    print(f"  Started: {pid_info['timestamp']}")
                print(f"  Log file: {self.log_file}")

                # Show uptime
                try:
                    result = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "etime="],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0:
                        print(f"  Uptime: {result.stdout.strip()}")
                except Exception:
                    pass

        # Always show component status (even if server not running)
        print("")

        # Database status
        print("Database:")
        db_status = self.check_database_status()
        if db_status["exists"]:
            if db_status["accessible"]:
                size_str = self._format_size(db_status["size_bytes"])
                table_count = len(db_status.get("tables", []))
                print(f"  Status: OK ({size_str}, {table_count} tables)")
                if verbose and db_status.get("table_counts"):
                    for table, count in db_status["table_counts"].items():
                        print(f"    - {table}: {count} rows")
            else:
                print(f"  Status: ERROR - {db_status.get('error', 'unknown error')}")
        else:
            print(f"  Status: NOT FOUND ({db_status['path']})")
        print(f"  Path: {db_status['path']}")

        # Redis status
        print("")
        print("Redis:")
        redis_status = self.check_redis_status()
        if redis_status["connected"]:
            info = redis_status.get("info", {})
            print(f"  Status: CONNECTED (v{info.get('redis_version', '?')})")
            print(f"  Host: {redis_status['host']}:{redis_status['port']}")
            if verbose:
                print(f"  Memory: {info.get('used_memory_human', 'unknown')}")
                print(f"  Clients: {info.get('connected_clients', 0)}")
                uptime = info.get("uptime_in_seconds", 0)
                if uptime:
                    hours = uptime // 3600
                    minutes = (uptime % 3600) // 60
                    print(f"  Uptime: {hours}h {minutes}m")

            # Show stream info
            streams = redis_status.get("streams", {})
            if streams:
                print("  Streams:")
                for stream_name, stream_info in streams.items():
                    short_name = stream_name.split(":")[-1]
                    if stream_info.get("exists") is False:
                        print(f"    - {short_name}: not created")
                    else:
                        print(f"    - {short_name}: {stream_info.get('length', 0)} messages")
        elif redis_status["available"]:
            print(f"  Status: NOT CONNECTED")
            print(f"  Host: {redis_status['host']}:{redis_status['port']}")
            if redis_status.get("error"):
                print(f"  Error: {redis_status['error']}")
        else:
            print(f"  Status: UNAVAILABLE")
            if redis_status.get("error"):
                print(f"  Error: {redis_status['error']}")

        # HTTP Endpoint status
        print("")
        print("HTTP Endpoint:")
        http_status = self.check_http_endpoint_status()
        if not http_status["enabled"]:
            print(f"  Status: DISABLED")
        elif http_status["reachable"]:
            print(f"  Status: OK")
            print(f"  URL: http://{http_status['host']}:{http_status['port']}")
        else:
            print(f"  Status: NOT REACHABLE")
            print(f"  URL: http://{http_status['host']}:{http_status['port']}")
            if http_status.get("error"):
                print(f"  Error: {http_status['error']}")

        # Monitor configuration status
        print("")
        print("Monitors:")
        monitor_status = self.check_monitor_status()
        if monitor_status["config_loaded"]:
            for key, info in monitor_status.get("monitors", {}).items():
                status = "enabled" if info.get("enabled", True) else "disabled"
                interval = info.get("poll_interval")
                interval_str = f" (poll: {interval}s)" if interval else ""
                print(f"  - {info['name']}: {status}{interval_str}")

            if verbose:
                features = monitor_status.get("features", {})
                if features:
                    print("  Features:")
                    for feature, enabled in features.items():
                        status = "enabled" if enabled else "disabled"
                        print(f"    - {feature}: {status}")
        else:
            if monitor_status.get("error"):
                print(f"  Error loading config: {monitor_status['error']}")
            else:
                print("  Config not available")

        return exit_code


def main():
    """Main entry point for server control CLI."""
    parser = argparse.ArgumentParser(
        description="Blueplane Telemetry server control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s start              # Start server in foreground
  %(prog)s start --daemon     # Start server in background
  %(prog)s stop               # Gracefully stop server
  %(prog)s stop --force       # Force kill if graceful fails
  %(prog)s restart --daemon   # Restart in background
  %(prog)s status --verbose   # Show detailed status
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start server")
    start_parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="Run server in background"
    )
    start_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop server")
    stop_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force kill if graceful shutdown fails"
    )
    stop_parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Timeout for graceful shutdown in seconds (default: 30)"
    )
    stop_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart server")
    restart_parser.add_argument(
        "--daemon", "-d",
        action="store_true",
        help="Run server in background after restart"
    )
    restart_parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=30,
        help="Timeout for stop operation in seconds (default: 30)"
    )
    restart_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )

    # Status command
    status_parser = subparsers.add_parser("status", help="Check server status")
    status_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed status information"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Create controller
    controller = ServerController()

    # Execute command
    if args.command == "start":
        return controller.start(daemon=args.daemon, verbose=args.verbose)
    elif args.command == "stop":
        return controller.stop(force=args.force, timeout=args.timeout, verbose=args.verbose)
    elif args.command == "restart":
        return controller.restart(daemon=args.daemon, timeout=args.timeout, verbose=args.verbose)
    elif args.command == "status":
        return controller.status(verbose=args.verbose)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
