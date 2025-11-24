#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Comprehensive installation verification for Blueplane Telemetry Core.

Checks all components according to PACKAGING_SPEC.md section 12.1:
- Docker Desktop and containers
- Redis connectivity and streams
- SQLite database and schema
- Claude hooks installation and enablement
- Cursor extension (optional)
- Processing server health
- Configuration validity
- Overall service status
"""

import sys
import os
import json
import argparse
import subprocess
import sqlite3
from pathlib import Path
from typing import Tuple, Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class ErrorCode(Enum):
    """Error codes for verification failures."""
    E001 = "Docker not installed"
    E002 = "Redis connection failed"
    E003 = "Database initialization failed"
    E004 = "Claude hooks installation failed"
    E005 = "Cursor extension build failed"
    E006 = "Docker daemon not running"
    E007 = "Docker containers not running"
    E008 = "Cursor extension not installed"
    E009 = "Processing server not healthy"
    E010 = "Configuration invalid"


@dataclass
class CheckResult:
    """Result of a single verification check."""
    name: str
    passed: bool
    message: str
    error_code: Optional[str] = None
    resolution: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


class VerificationReport:
    """Comprehensive verification report."""

    def __init__(self):
        self.checks: List[CheckResult] = []

    def add_check(self, result: CheckResult):
        """Add a check result to the report."""
        self.checks.append(result)

    def all_passed(self) -> bool:
        """Check if all verifications passed."""
        return all(check.passed for check in self.checks)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "all_passed": self.all_passed(),
            "total_checks": len(self.checks),
            "passed": sum(1 for c in self.checks if c.passed),
            "failed": sum(1 for c in self.checks if not c.passed),
            "checks": [asdict(check) for check in self.checks]
        }

    def print_summary(self, verbose: bool = False):
        """Print human-readable summary."""
        print("\n" + "=" * 70)
        print("📊 VERIFICATION SUMMARY")
        print("=" * 70)

        for check in self.checks:
            status = "✅ PASS" if check.passed else "❌ FAIL"
            print(f"{status:12} {check.name}")

            if verbose or not check.passed:
                print(f"             {check.message}")

                if check.error_code:
                    print(f"             Error: {check.error_code}")

                if check.resolution:
                    print(f"             💡 {check.resolution}")

                if check.details and verbose:
                    for key, value in check.details.items():
                        print(f"                {key}: {value}")

        print("\n" + "=" * 70)
        if self.all_passed():
            print("✅ All checks passed! Installation is ready.")
        else:
            failed_count = sum(1 for c in self.checks if not c.passed)
            print(f"⚠️  {failed_count} check(s) failed. Review details above.")
        print("=" * 70)


def check_docker_installed() -> CheckResult:
    """Check if Docker is installed."""
    try:
        result = subprocess.run(
            ['docker', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            version = result.stdout.strip()
            return CheckResult(
                name="Docker Installation",
                passed=True,
                message=f"Docker is installed: {version}",
                details={"version": version}
            )
        else:
            return CheckResult(
                name="Docker Installation",
                passed=False,
                message="Docker command failed",
                error_code=ErrorCode.E001.name,
                resolution="Install Docker Desktop from https://www.docker.com/products/docker-desktop"
            )

    except FileNotFoundError:
        return CheckResult(
            name="Docker Installation",
            passed=False,
            message="Docker command not found",
            error_code=ErrorCode.E001.name,
            resolution="Install Docker Desktop from https://www.docker.com/products/docker-desktop"
        )
    except Exception as e:
        return CheckResult(
            name="Docker Installation",
            passed=False,
            message=f"Error checking Docker: {e}",
            error_code=ErrorCode.E001.name,
            resolution="Install Docker Desktop and ensure it's in PATH"
        )


def check_docker_running() -> CheckResult:
    """Check if Docker daemon is running."""
    try:
        result = subprocess.run(
            ['docker', 'info'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            return CheckResult(
                name="Docker Daemon",
                passed=True,
                message="Docker daemon is running"
            )
        else:
            return CheckResult(
                name="Docker Daemon",
                passed=False,
                message="Docker daemon is not responding",
                error_code=ErrorCode.E006.name,
                resolution="Start Docker Desktop application"
            )

    except Exception as e:
        return CheckResult(
            name="Docker Daemon",
            passed=False,
            message=f"Cannot connect to Docker daemon: {e}",
            error_code=ErrorCode.E006.name,
            resolution="Start Docker Desktop application"
        )


def check_docker_containers() -> CheckResult:
    """Check if required Docker containers are running."""
    try:
        # Check for redis container
        redis_result = subprocess.run(
            ['docker', 'ps', '--filter', 'name=redis', '--format', '{{.Names}}\t{{.Status}}'],
            capture_output=True,
            text=True,
            timeout=5
        )

        # Check for blueplane-server container
        server_result = subprocess.run(
            ['docker', 'ps', '--filter', 'name=blueplane-server', '--format', '{{.Names}}\t{{.Status}}'],
            capture_output=True,
            text=True,
            timeout=5
        )

        redis_running = redis_result.returncode == 0 and redis_result.stdout.strip()
        server_running = server_result.returncode == 0 and server_result.stdout.strip()

        if redis_running and server_running:
            details = {
                "redis": redis_result.stdout.strip(),
                "blueplane_server": server_result.stdout.strip()
            }
            return CheckResult(
                name="Docker Containers",
                passed=True,
                message="Required containers are running",
                details=details
            )
        else:
            missing = []
            if not redis_running:
                missing.append("redis")
            if not server_running:
                missing.append("blueplane-server")

            return CheckResult(
                name="Docker Containers",
                passed=False,
                message=f"Missing containers: {', '.join(missing)}",
                error_code=ErrorCode.E007.name,
                resolution="Run: docker-compose up -d (from ~/.blueplane/ directory)"
            )

    except Exception as e:
        return CheckResult(
            name="Docker Containers",
            passed=False,
            message=f"Error checking containers: {e}",
            error_code=ErrorCode.E007.name,
            resolution="Ensure Docker is running and containers are started"
        )


def check_redis_connection() -> CheckResult:
    """Check Redis connectivity and streams."""
    try:
        import redis

        client = redis.Redis(host='localhost', port=6379, socket_timeout=2, decode_responses=True)

        # Test connection
        client.ping()

        details = {"host": "localhost", "port": 6379, "connected": True}

        # Check for telemetry streams
        try:
            stream_info = client.xinfo_stream('telemetry:events')
            details["stream_exists"] = True
            details["stream_length"] = stream_info.get('length', 0)
        except redis.ResponseError:
            details["stream_exists"] = False
            details["warning"] = "Stream 'telemetry:events' not found"

        # Check consumer groups
        try:
            groups = client.xinfo_groups('telemetry:events')
            details["consumer_groups"] = len(groups)
        except redis.ResponseError:
            details["consumer_groups"] = 0
            details["warning"] = "No consumer groups configured"

        # Overall pass if connected, warnings are acceptable for new installations
        return CheckResult(
            name="Redis Connection",
            passed=True,
            message="Redis is accessible",
            details=details
        )

    except ImportError:
        return CheckResult(
            name="Redis Connection",
            passed=False,
            message="Redis Python library not installed",
            error_code=ErrorCode.E002.name,
            resolution="Install: pip install redis"
        )
    except Exception as e:
        return CheckResult(
            name="Redis Connection",
            passed=False,
            message=f"Cannot connect to Redis: {e}",
            error_code=ErrorCode.E002.name,
            resolution="Check if Redis container is running: docker ps"
        )


def check_sqlite_database() -> CheckResult:
    """Check SQLite database existence and schema."""
    db_path = Path.home() / ".blueplane" / "telemetry.db"

    if not db_path.exists():
        return CheckResult(
            name="SQLite Database",
            passed=False,
            message=f"Database not found: {db_path}",
            error_code=ErrorCode.E003.name,
            resolution="Run: python scripts/init_database.py"
        )

    try:
        # Check database can be opened and has required tables
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get list of tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        # Required tables (based on schema.py)
        required_tables = ['raw_traces', 'conversations', 'sessions']
        missing_tables = [t for t in required_tables if t not in tables]

        details = {
            "path": str(db_path),
            "size_mb": round(db_path.stat().st_size / (1024 * 1024), 2),
            "tables": len(tables),
            "table_names": tables
        }

        if missing_tables:
            conn.close()
            return CheckResult(
                name="SQLite Database",
                passed=False,
                message=f"Missing tables: {', '.join(missing_tables)}",
                error_code=ErrorCode.E003.name,
                resolution="Run: python scripts/init_database.py",
                details=details
            )

        # Get row count for raw_traces
        cursor.execute("SELECT COUNT(*) FROM raw_traces")
        event_count = cursor.fetchone()[0]
        details["events"] = event_count

        conn.close()

        return CheckResult(
            name="SQLite Database",
            passed=True,
            message=f"Database is valid with {len(tables)} tables",
            details=details
        )

    except Exception as e:
        return CheckResult(
            name="SQLite Database",
            passed=False,
            message=f"Database error: {e}",
            error_code=ErrorCode.E003.name,
            resolution="Check database file permissions and integrity"
        )


def check_claude_hooks() -> CheckResult:
    """Check Claude Code hooks installation."""
    hooks_dir = Path.home() / ".claude" / "hooks" / "telemetry"

    if not hooks_dir.exists():
        return CheckResult(
            name="Claude Hooks",
            passed=False,
            message=f"Hooks directory not found: {hooks_dir}",
            error_code=ErrorCode.E004.name,
            resolution="Run: python scripts/install_claude_hooks.py"
        )

    # Expected hook files
    expected_hooks = [
        'session_start.py',
        'session_end.py',
    ]

    missing_hooks = []
    found_hooks = []

    for hook in expected_hooks:
        hook_path = hooks_dir / hook
        if hook_path.exists() and os.access(hook_path, os.X_OK):
            found_hooks.append(hook)
        else:
            missing_hooks.append(hook)

    # Check hook_base.py in parent directory
    hook_base = hooks_dir.parent / "hook_base.py"
    hook_base_exists = hook_base.exists()

    # Check settings.json for hook enablement
    settings_path = Path.home() / ".claude" / "settings.json"
    hooks_enabled = False

    if settings_path.exists():
        try:
            with open(settings_path) as f:
                settings = json.load(f)
                hooks_enabled = settings.get("hooks", {}).get("enabled", False)
        except:
            pass

    details = {
        "hooks_directory": str(hooks_dir),
        "found_hooks": found_hooks,
        "missing_hooks": missing_hooks,
        "hook_base_exists": hook_base_exists,
        "settings_exists": settings_path.exists(),
        "hooks_enabled": hooks_enabled
    }

    if missing_hooks:
        return CheckResult(
            name="Claude Hooks",
            passed=False,
            message=f"Missing hooks: {', '.join(missing_hooks)}",
            error_code=ErrorCode.E004.name,
            resolution="Run: python scripts/install_claude_hooks.py",
            details=details
        )

    if not hook_base_exists:
        return CheckResult(
            name="Claude Hooks",
            passed=False,
            message="hook_base.py not found",
            error_code=ErrorCode.E004.name,
            resolution="Run: python scripts/install_claude_hooks.py",
            details=details
        )

    if not hooks_enabled:
        details["warning"] = "Hooks are installed but not enabled in settings.json"

    return CheckResult(
        name="Claude Hooks",
        passed=True,
        message=f"Hooks installed ({len(found_hooks)} files)",
        details=details
    )


def check_cursor_extension() -> CheckResult:
    """Check Cursor extension installation (optional)."""
    # Check common Cursor installation locations
    cursor_paths = [
        Path.home() / "Library/Application Support/Cursor",  # macOS
        Path.home() / ".config/Cursor",  # Linux
    ]

    cursor_installed = any(p.exists() for p in cursor_paths)

    if not cursor_installed:
        return CheckResult(
            name="Cursor Extension (Optional)",
            passed=True,  # Optional, so pass even if not found
            message="Cursor not detected (optional component)",
            details={"cursor_installed": False, "checked_paths": [str(p) for p in cursor_paths]}
        )

    # Check for extension installation
    # Extension would be in workspace or user extensions
    extension_found = False
    extension_path = None

    for cursor_path in cursor_paths:
        if cursor_path.exists():
            # Check for VSIX or installed extension
            # This is a simplified check - actual implementation may vary
            extensions_dir = cursor_path / "extensions"
            if extensions_dir.exists():
                bp_extensions = list(extensions_dir.glob("blueplane*"))
                if bp_extensions:
                    extension_found = True
                    extension_path = str(bp_extensions[0])
                    break

    details = {
        "cursor_installed": True,
        "extension_found": extension_found,
        "extension_path": extension_path
    }

    if extension_found:
        return CheckResult(
            name="Cursor Extension (Optional)",
            passed=True,
            message="Cursor extension is installed",
            details=details
        )
    else:
        return CheckResult(
            name="Cursor Extension (Optional)",
            passed=True,  # Still pass since it's optional
            message="Cursor detected but extension not installed",
            details=details
        )


def check_processing_server() -> CheckResult:
    """Check processing server health."""
    try:
        import requests

        # Try health endpoint
        response = requests.get('http://localhost:8000/health', timeout=3)

        if response.status_code == 200:
            health_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
            return CheckResult(
                name="Processing Server",
                passed=True,
                message="Processing server is healthy",
                details={"status_code": 200, "health": health_data}
            )
        else:
            return CheckResult(
                name="Processing Server",
                passed=False,
                message=f"Server returned status {response.status_code}",
                error_code=ErrorCode.E009.name,
                resolution="Check server logs: docker logs blueplane-server"
            )

    except ImportError:
        # Fall back to checking if process is running
        try:
            result = subprocess.run(
                ['ps', 'aux'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if 'src.processing.server' in result.stdout or 'start_server' in result.stdout:
                return CheckResult(
                    name="Processing Server",
                    passed=True,
                    message="Processing server process detected (health endpoint check requires requests library)"
                )
            else:
                return CheckResult(
                    name="Processing Server",
                    passed=False,
                    message="Processing server not running",
                    error_code=ErrorCode.E009.name,
                    resolution="Start server: docker-compose up -d blueplane-server"
                )
        except:
            return CheckResult(
                name="Processing Server",
                passed=False,
                message="Cannot verify server status",
                error_code=ErrorCode.E009.name,
                resolution="Install requests library: pip install requests"
            )

    except Exception as e:
        return CheckResult(
            name="Processing Server",
            passed=False,
            message=f"Cannot reach server: {e}",
            error_code=ErrorCode.E009.name,
            resolution="Check if server container is running: docker ps"
        )


def check_configuration() -> CheckResult:
    """Check configuration files."""
    config_dir = Path.home() / ".blueplane" / "config"

    if not config_dir.exists():
        return CheckResult(
            name="Configuration",
            passed=False,
            message=f"Config directory not found: {config_dir}",
            error_code=ErrorCode.E010.name,
            resolution="Create config directory and initialize configuration"
        )

    # Expected configuration files
    expected_configs = ['claude.yaml', 'cursor.yaml', 'privacy.yaml', 'redis.yaml']

    found_configs = []
    missing_configs = []

    for config_file in expected_configs:
        config_path = config_dir / config_file
        if config_path.exists():
            found_configs.append(config_file)
        else:
            missing_configs.append(config_file)

    details = {
        "config_directory": str(config_dir),
        "found_configs": found_configs,
        "missing_configs": missing_configs
    }

    # All configs are required for full functionality
    if missing_configs:
        return CheckResult(
            name="Configuration",
            passed=False,
            message=f"Missing configs: {', '.join(missing_configs)}",
            error_code=ErrorCode.E010.name,
            resolution="Copy config files from config/ directory to ~/.blueplane/config/",
            details=details
        )

    return CheckResult(
        name="Configuration",
        passed=True,
        message=f"All configuration files present ({len(found_configs)} files)",
        details=details
    )


def run_verification(verbose: bool = False) -> VerificationReport:
    """Run all verification checks."""
    report = VerificationReport()

    # Run all checks
    checks = [
        check_docker_installed,
        check_docker_running,
        check_docker_containers,
        check_redis_connection,
        check_sqlite_database,
        check_claude_hooks,
        check_cursor_extension,
        check_processing_server,
        check_configuration,
    ]

    for check_fn in checks:
        if verbose:
            print(f"\n🔍 Running check: {check_fn.__name__}...")

        result = check_fn()
        report.add_check(result)

    return report


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Verify Blueplane Telemetry Core installation'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results in JSON format'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output with detailed information'
    )

    args = parser.parse_args()

    if not args.json:
        print("=" * 70)
        print("🔍 BLUEPLANE TELEMETRY CORE - INSTALLATION VERIFICATION")
        print("=" * 70)

    # Run verification
    report = run_verification(verbose=args.verbose)

    # Output results
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        report.print_summary(verbose=args.verbose)

    # Exit with appropriate code
    return 0 if report.all_passed() else 1


if __name__ == '__main__':
    sys.exit(main())
