#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only

"""Shared helpers and base classes for integration test harnesses.

Requires jleechanorg-orchestration framework for CLI profile management.
Install with: pip install jleechanorg-orchestration
"""

import json
import os
import shlex
import shutil
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Orchestration framework (required dependency)
# Install with: pip install jleechanorg-orchestration
from orchestration.task_dispatcher import CLI_PROFILES

def _get_branch_name() -> str:
    """Get current git branch name for results directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip().replace("/", "-")
    except Exception:
        # Best-effort: if git unavailable or fails, use default branch name
        pass
    return "unknown-branch"

RESULTS_DIR = Path(tempfile.gettempdir()) / "bp-telemetry-core" / _get_branch_name()
PROJECT_ROOT = Path(__file__).parent.parent


class BaseTelemetryTest:
    """Base test harness with common functionality for telemetry tests.

    Uses jleechanorg-orchestration CLI_PROFILES for CLI configuration.

    Subclasses only need to define class attributes:
        CLI_NAME: str - Key in CLI_PROFILES (e.g., "claude" or "cursor")
        TABLE: str - SQLite table name (e.g., "claude_raw_traces")
        SUITE_NAME: str - Test suite name for reporting
        FILE_PREFIX: str - Prefix for result files
    """

    # Subclasses must override these
    CLI_NAME: str = ""  # Key in CLI_PROFILES (e.g., "claude", "cursor")
    TABLE: str = ""
    SUITE_NAME: str = ""
    FILE_PREFIX: str = ""

    def __init__(self):
        self.telemetry_db = Path.home() / ".blueplane" / "telemetry.db"
        self.start_time = datetime.now(timezone.utc)
        self.results = {"passed": [], "failed": [], "skipped": []}
        self.test_marker = f"TEST_{uuid.uuid4().hex[:8]}"
        self.server_manager = TelemetryServerManager()

        # Get CLI profile from orchestration framework
        if self.CLI_NAME and self.CLI_NAME in CLI_PROFILES:
            self.cli_profile = CLI_PROFILES[self.CLI_NAME]
        else:
            self.cli_profile = None

    def record(self, name: str, passed: bool, message: str = "", skip: bool = False):
        """Record test result with consistent formatting."""
        if skip:
            self.results["skipped"].append((name, message))
            print(f"  ⏭️  {name}: SKIPPED - {message}")
        elif passed:
            self.results["passed"].append((name, message))
            print(f"  ✅ {name}: {message}")
        else:
            self.results["failed"].append((name, message))
            print(f"  ❌ {name}: {message}")

    def check_redis(self) -> bool:
        """Check if Redis is running using project configuration."""
        try:
            import redis
            # Load Redis config from project configuration
            from src.capture.shared.config import Config
            config = Config()
            redis_config = config.redis
            r = redis.Redis(host=redis_config.host, port=redis_config.port)
            r.ping()
            return True
        except Exception:
            return False

    def get_event_count(self, table: str, hours: Optional[int] = None) -> int:
        """
        Get count of events from a table.

        Args:
            table: Table name (must be in allowed list)
            hours: If provided, only count events from last N hours.
                   If None, counts events since test started.
        """
        allowed_tables = {"claude_raw_traces", "cursor_raw_traces"}
        if table not in allowed_tables:
            raise ValueError(f"Invalid table name: {table}")

        if not self.telemetry_db.exists():
            return 0

        if hours is not None:
            from datetime import timedelta
            since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        else:
            since = self.start_time.isoformat()

        try:
            with sqlite3.connect(str(self.telemetry_db)) as conn:
                cursor = conn.execute(f"""
                    SELECT COUNT(*) FROM {table}
                    WHERE timestamp >= ?
                """, (since,))
                return cursor.fetchone()[0]
        except sqlite3.Error as e:
            print(f"  Warning: DB error - {e}")
            return 0

    def get_recent_events(self, table: str, limit: int = 5) -> list:
        """
        Get recent events from a table.

        Args:
            table: Table name (must be in allowed list)
            limit: Maximum number of events to return
        """
        allowed_tables = {"claude_raw_traces", "cursor_raw_traces"}
        if table not in allowed_tables:
            raise ValueError(f"Invalid table name: {table}")

        if not self.telemetry_db.exists():
            return []

        try:
            with sqlite3.connect(str(self.telemetry_db)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(f"""
                    SELECT * FROM {table}
                    ORDER BY timestamp DESC
                    LIMIT ?
                """, (limit,))
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            print(f"  Warning: DB error - {e}")
            return []

    def check_table_exists(self, table: str) -> bool:
        """Check if a table exists in the telemetry database."""
        if not self.telemetry_db.exists():
            return False

        try:
            with sqlite3.connect(str(self.telemetry_db)) as conn:
                cursor = conn.execute("""
                    SELECT name FROM sqlite_master
                    WHERE type='table' AND name=?
                """, (table,))
                return cursor.fetchone() is not None
        except sqlite3.Error:
            return False

    def print_summary(self) -> None:
        """Print test results summary."""
        print("\n" + "=" * 70)
        print("RESULTS SUMMARY")
        print("=" * 70)
        print(f"  Passed:  {len(self.results['passed'])}")
        print(f"  Failed:  {len(self.results['failed'])}")
        print(f"  Skipped: {len(self.results['skipped'])}")

        if self.results['failed']:
            print("\nFailed tests:")
            for name, msg in self.results['failed']:
                print(f"  - {name}: {msg}")

    def check_cli(self) -> bool:
        """Check if CLI is available using orchestration CLI_PROFILES."""
        if not self.cli_profile:
            raise ValueError(f"CLI_NAME '{self.CLI_NAME}' not found in CLI_PROFILES")

        cli_binary = self.cli_profile.get("binary")
        if not cli_binary:
            raise ValueError(f"CLI profile '{self.CLI_NAME}' missing 'binary' field")
        
        cli_path = shutil.which(cli_binary)

        if not cli_path:
            return False

        try:
            result = subprocess.run(
                [cli_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                display_name = self.cli_profile.get("display_name", cli_binary)
                print(f"  {display_name} version: {result.stdout.strip()}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # CLI not found or hung - fall through to return False
            pass
        return False

    def run_cli(self, prompt: str, timeout: int = 60) -> tuple[bool, str]:
        """Run CLI with a prompt using orchestration CLI_PROFILES command template.

        Constructs command from CLI_PROFILES configuration.
        """
        if not self.cli_profile:
            raise ValueError(f"CLI_NAME '{self.CLI_NAME}' not found in CLI_PROFILES")

        cli_binary = self.cli_profile.get("binary")
        if not cli_binary:
            raise ValueError(f"CLI profile '{self.CLI_NAME}' missing 'binary' field")
        
        cli_path = shutil.which(cli_binary)
        if not cli_path:
            return False, f"{cli_binary} not found"

        # Write prompt to temp file (orchestration framework uses file-based prompts)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            # Build command as list to avoid shell injection (shell=False)
            # Parse command_template to extract binary and args
            command_template = self.cli_profile.get("command_template", "{binary} -p {prompt_file}")
            
            # Quote cli_path to handle spaces in paths
            cli_path_quoted = shlex.quote(cli_path)
            
            cli_command_str = command_template.format(
                binary=cli_path_quoted,
                prompt_file=shlex.quote(prompt_file),
                continue_flag=""
            )
            # Split into list for safe subprocess execution
            cli_command = shlex.split(cli_command_str)
            print(f"  Command: {' '.join(cli_command)}")

            # Handle stdin redirection - use context manager to prevent leaks
            stdin_template = self.cli_profile.get("stdin_template", "/dev/null")
            stdin_file = None

            try:
                if stdin_template != "/dev/null":
                    stdin_file = open(prompt_file, 'r')

                result = subprocess.run(
                    cli_command,
                    shell=False,  # Use shell=False for security
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    stdin=stdin_file,
                    env={**os.environ, "NO_COLOR": "1"}
                )

                return result.returncode == 0, result.stdout + result.stderr
            except subprocess.TimeoutExpired:
                return False, "Timeout"
            except FileNotFoundError:
                return False, f"{cli_binary} not found"
            except Exception as e:
                return False, str(e)
            finally:
                # Always close stdin_file if opened (prevents resource leak)
                if stdin_file:
                    stdin_file.close()
        finally:
            # Clean up temp file
            try:
                os.unlink(prompt_file)
            except OSError:
                pass

    def get_sqlite_count(self) -> int:
        """Count events in SQLite since test started."""
        return self.get_event_count(self.TABLE)

    def get_recent(self, limit: int = 5) -> list:
        """Get recent events filtered by test start time."""
        if not self.TABLE:
            raise ValueError("TABLE must be defined in subclass")
        # Validate table name to prevent SQL injection
        allowed_tables = {"claude_raw_traces", "cursor_raw_traces"}
        if self.TABLE not in allowed_tables:
            raise ValueError(f"Invalid table name: {self.TABLE}")
        if not self.telemetry_db.exists():
            return []
        try:
            with sqlite3.connect(str(self.telemetry_db)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(f"""
                    SELECT * FROM {self.TABLE}
                    WHERE timestamp >= ?
                    ORDER BY timestamp DESC LIMIT ?
                """, (self.start_time.isoformat(), limit))
                return [dict(row) for row in cursor.fetchall()]
        except sqlite3.Error:
            return []

    def run_all_tests(self) -> int:
        """Run all integration tests for this CLI.

        Returns exit code (0 = success, 1 = failure).
        """
        display_name = self.cli_profile.get("display_name", self.CLI_NAME) if self.cli_profile else "Unknown"
        print("=" * 70)
        print(f"{display_name} Telemetry - Integration Tests (REAL CLI)")
        print("=" * 70)
        print(f"Started: {datetime.now(timezone.utc).isoformat()}\n")

        we_started_server = False

        try:
            # Prerequisites
            print("[TEST] Redis...")
            if self.check_redis():
                self.record("redis", True, "Running")
            else:
                self.record("redis", False, "Not running - start with: redis-server")
                return self._finish()

            print(f"\n[TEST] {display_name} CLI...")
            if self.check_cli():
                self.record("cli", True, "Installed")
            else:
                cli_binary = self.cli_profile.get("binary", self.CLI_NAME) if self.cli_profile else self.CLI_NAME
                self.record("cli", False, f"Not found - install {cli_binary}", skip=True)
                return self._finish()

            # Server
            print("\n[TEST] Server...")
            if self.server_manager.is_running():
                self.record("server", True, "Already running")
            else:
                we_started_server = self.server_manager.start(timeout=30)
                self.record("server", we_started_server,
                           "Started" if we_started_server else "Failed")
                if not we_started_server:
                    return self._finish()

            # Database
            print("\n[TEST] Database...")
            time.sleep(2)
            if self.telemetry_db.exists():
                self.record("database", True, f"Exists at {self.telemetry_db}")
            else:
                self.record("database", False, "Not found", skip=True)
                return self._finish()

            # Event generation - REAL CLI INVOCATION
            print(f"\n[TEST] Event generation (invoking real {display_name} CLI)...")
            initial = self.get_sqlite_count()

            success, output = self.run_cli(f"echo 'test marker: {self.test_marker}'")
            if not success:
                # CLI failure is a real failure, not skip - prevents "passive" test passing
                self.record("events", False, f"{display_name} CLI failed: {output[:100]}")
                return self._finish()
            else:
                time.sleep(5)
                new_count = self.get_sqlite_count() - initial
                if new_count > 0:
                    self.record("events", True, f"Generated {new_count} events")
                else:
                    self.record("events", False, "No events captured - check telemetry hooks")

            # Event structure
            print("\n[TEST] Event structure...")
            events = self.get_recent(limit=3)
            if events:
                required = ["event_id", "event_type", "timestamp"]
                missing = [f for f in required if f not in events[0] or events[0][f] is None]
                if missing:
                    self.record("structure", False, f"Missing: {missing}")
                else:
                    self.record("structure", True, f"Fields: {len(events[0])} columns")
            else:
                self.record("structure", False, "No events to validate", skip=True)

        finally:
            if we_started_server:
                print("\n[CLEANUP] Stopping server...")
                self.server_manager.stop()

        return self._finish()

    def _finish(self) -> int:
        """Print summary, save results, return exit code."""
        self.print_summary()
        save_test_results(self.results, self.SUITE_NAME, self.FILE_PREFIX)
        return 1 if self.results['failed'] else 0


class TelemetryServerManager:
    """Manages telemetry server lifecycle for testing."""

    def __init__(self):
        self.server_process = None
        self.server_script = PROJECT_ROOT / "scripts" / "start_server.py"
        self.pid_file = Path.home() / ".blueplane" / "server.pid"

    def is_running(self) -> bool:
        """Check if telemetry server is running."""
        if self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text().strip())
                os.kill(pid, 0)
                return True
            except (ValueError, OSError):
                # Process is dead, clean up stale PID file
                try:
                    self.pid_file.unlink()
                except OSError:
                    # Best-effort cleanup: ignore if file already gone or permissions issue
                    pass
        return False

    def start(self, timeout: int = 30) -> bool:
        """Start telemetry server and wait for initialization."""
        if self.is_running():
            print("  Server already running")
            return True

        print(f"  Starting telemetry server...")
        # Use DEVNULL to prevent pipe buffer deadlock when server logs heavily
        self.server_process = subprocess.Popen(
            [sys.executable, str(self.server_script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(PROJECT_ROOT),
        )

        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.pid_file.exists():
                print(f"  Server started (PID: {self.pid_file.read_text().strip()})")
                time.sleep(2)
                return True
            time.sleep(0.5)

        if self.server_process.poll() is not None:
            print(f"  Server process exited with code: {self.server_process.returncode}")
            return False

        # Timeout - terminate orphaned process before returning
        print(f"  Server start timed out")
        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
        return False

    def stop(self) -> None:
        """Stop telemetry server."""
        if self.pid_file.exists():
            try:
                pid = int(self.pid_file.read_text().strip())
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                try:
                    os.kill(pid, 0)
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    # Process already terminated after SIGTERM - nothing more to do
                    pass
            except (ValueError, OSError):
                # PID file corrupt or process already gone - continue cleanup
                pass

        if self.server_process:
            self.server_process.terminate()
            try:
                self.server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()

        if self.pid_file.exists():
            try:
                self.pid_file.unlink()
            except OSError:
                # Best-effort cleanup: ignore if file already gone
                pass


def save_test_results(results_dict: dict, test_suite_name: str, file_prefix: str) -> None:
    """Persist integration test results to JSON and text summary files."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    results = {
        "test_suite": test_suite_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "passed": len(results_dict.get("passed", [])),
            "failed": len(results_dict.get("failed", [])),
            "skipped": len(results_dict.get("skipped", [])),
        },
        "passed": [{"name": n, "message": m} for n, m in results_dict.get("passed", [])],
        "failed": [{"name": n, "message": m} for n, m in results_dict.get("failed", [])],
        "skipped": [{"name": n, "message": m} for n, m in results_dict.get("skipped", [])],
    }

    # Save JSON (explicit UTF-8 for cross-platform compatibility)
    result_file = RESULTS_DIR / f"{file_prefix}_results.json"
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n📄 Results saved to: {result_file}")

    # Save text summary (explicit UTF-8 for emoji characters)
    summary_file = RESULTS_DIR / f"{file_prefix}_summary.txt"
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"{test_suite_name.replace('_', ' ').title()} - Integration Test Results\n")
        f.write("=" * 50 + "\n")
        f.write(f"Timestamp: {results['timestamp']}\n\n")
        f.write(f"Passed:  {results['summary']['passed']}\n")
        f.write(f"Failed:  {results['summary']['failed']}\n")
        f.write(f"Skipped: {results['summary']['skipped']}\n\n")

        sections = [
            ("passed", "✅", "PASSED"),
            ("failed", "❌", "FAILED"),
            ("skipped", "⏭️", "SKIPPED"),
        ]
        for key, emoji, title in sections:
            if results[key]:
                f.write(f"{title}:\n")
                for t in results[key]:
                    f.write(f"  {emoji} {t['name']}: {t['message']}\n")
                f.write("\n")

    print(f"📄 Summary saved to: {summary_file}")
