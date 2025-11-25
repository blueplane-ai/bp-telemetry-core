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
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any


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
            print("Status: NOT RUNNING (no PID file)")
            return 1

        pid = pid_info["pid"]

        # Check if process is running
        if not self.is_process_running(pid):
            print(f"Status: NOT RUNNING (stale PID {pid})")
            if verbose:
                print(f"  PID file: {self.pid_file}")
                print(f"  Cleanup required: yes")
            return 1

        # Check if it's our process
        if self.is_stale_pid(pid_info):
            print(f"Status: NOT RUNNING (PID {pid} is wrong process)")
            if verbose:
                print(f"  PID file: {self.pid_file}")
                print(f"  Cleanup required: yes")
            return 1

        # Server is running
        print(f"Status: RUNNING (PID {pid})")

        if verbose:
            print(f"  PID: {pid}")
            print(f"  PID file: {self.pid_file}")
            if pid_info["timestamp"]:
                print(f"  Started: {pid_info['timestamp']}")
            print(f"  Log file: {self.log_file}")

            # Show command line
            try:
                result = subprocess.run(
                    ["ps", "-p", str(pid), "-o", "args="],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    print(f"  Command: {result.stdout.strip()}")
            except Exception:
                pass

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

        return 0


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
