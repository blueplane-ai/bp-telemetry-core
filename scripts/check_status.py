#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Comprehensive status check for Blueplane Telemetry Core.

Checks all components:
- Hooks installation
- Database trace monitoring
- Redis queue status
- Database status
- Processing server status
"""

import sys
import json
import subprocess
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def check_hooks():
    """Check hooks installation status."""
    print("\n1️⃣  HOOKS STATUS")
    print("-" * 70)
    hooks_dir = Path.home() / ".cursor" / "hooks"
    if hooks_dir.exists():
        hook_files = list(hooks_dir.glob("*.py"))
        print(f"✅ Hooks directory exists: {hooks_dir}")
        print(f"   Hook scripts found: {len(hook_files)}")
        
        hooks_json = Path.home() / ".cursor" / "hooks.json"
        if hooks_json.exists():
            print(f"✅ hooks.json exists")
            try:
                with open(hooks_json) as f:
                    hooks_config = json.load(f)
                    hooks_dict = hooks_config.get("hooks", {})
                    if isinstance(hooks_dict, dict):
                        enabled = sum(1 for h in hooks_dict.values() 
                                    if isinstance(h, dict) and h.get("enabled", True))
                        print(f"   Enabled hooks: {enabled}")
            except Exception as e:
                print(f"   ⚠️  Could not parse hooks.json: {e}")
        else:
            print("⚠️  hooks.json not found")
        return True
    else:
        print("❌ Hooks directory not found!")
        return False


def check_database_traces():
    """Check database trace monitoring setup."""
    print("\n2️⃣  DATABASE TRACES STATUS")
    print("-" * 70)
    extension_dir = project_root / "src" / "capture" / "cursor" / "extension"
    if extension_dir.exists():
        compiled_js = list(extension_dir.glob("out/**/*.js"))
        print(f"✅ Extension source exists")
        print(f"   Compiled JS files: {len(compiled_js)}")
        
        # Check for Cursor database
        cursor_db_paths = [
            Path.home() / "Library/Application Support/Cursor/User/workspaceStorage",
            Path.home() / ".config/Cursor/User/workspaceStorage",
        ]
        for db_path in cursor_db_paths:
            if db_path.exists():
                db_files = list(db_path.glob("*/state.vscdb"))
                if db_files:
                    print(f"✅ Found Cursor database: {db_files[0]}")
                    return True
        print("⚠️  Cursor database not found (extension may not be able to monitor)")
        return False
    else:
        print("⚠️  Extension directory not found")
        return False


def check_redis_queue():
    """Check Redis queue and consumer status."""
    print("\n3️⃣  REDIS QUEUE STATUS")
    print("-" * 70)
    try:
        result = subprocess.run(['redis-cli', 'XLEN', 'telemetry:events'], 
                              capture_output=True, text=True, timeout=2)
        if result.returncode == 0:
            queue_len = int(result.stdout.strip())
            print(f"✅ Redis connection: OK")
            print(f"   Events in queue: {queue_len}")
            
            result = subprocess.run(['redis-cli', 'XINFO', 'GROUPS', 'telemetry:events'],
                                  capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                consumers = 0
                pending = 0
                lag = 0
                for i, line in enumerate(lines):
                    if line == 'consumers' and i+1 < len(lines):
                        try:
                            consumers = int(lines[i+1])
                        except:
                            pass
                    elif line == 'pending' and i+1 < len(lines):
                        try:
                            pending = int(lines[i+1])
                        except:
                            pass
                    elif line == 'lag' and i+1 < len(lines):
                        try:
                            lag = int(lines[i+1])
                        except:
                            pass
                
                print(f"   Active consumers: {consumers}")
                print(f"   Pending messages: {pending}")
                print(f"   Lag: {lag}")
                
                if consumers == 0:
                    print("   ⚠️  WARNING: No active consumers!")
                    return False
                elif lag > 100:
                    print(f"   ⚠️  WARNING: High lag ({lag} messages)")
                    return False
                else:
                    print("   ✅ Consumer group healthy")
                    return True
        else:
            print("❌ Redis not responding")
            return False
    except Exception as e:
        print(f"❌ Redis check failed: {e}")
        return False


def check_database():
    """Check database status and content."""
    print("\n4️⃣  DATABASE STATUS")
    print("-" * 70)
    from blueplane.processing.database.sqlite_client import SQLiteClient
    
    db_path = Path.home() / ".blueplane" / "telemetry.db"
    if db_path.exists():
        print(f"✅ Database exists: {db_path}")
        print(f"   Size: {db_path.stat().st_size / 1024 / 1024:.2f} MB")
        
        try:
            client = SQLiteClient(str(db_path))
            with client.get_connection() as conn:
                cursor = conn.execute('SELECT COUNT(*) FROM raw_traces')
                total = cursor.fetchone()[0]
                print(f"   Total events: {total}")
                
                cursor = conn.execute('''
                    SELECT COUNT(*) FROM raw_traces 
                    WHERE timestamp > datetime('now', '-1 hour')
                ''')
                recent = cursor.fetchone()[0]
                print(f"   Events (last hour): {recent}")
                
                cursor = conn.execute('''
                    SELECT event_type, COUNT(*) as cnt 
                    FROM raw_traces 
                    GROUP BY event_type 
                    ORDER BY cnt DESC
                    LIMIT 10
                ''')
                print("   Event breakdown:")
                for row in cursor.fetchall():
                    print(f"     - {row[0]}: {row[1]}")
                
                cursor = conn.execute('SELECT COUNT(*) FROM raw_traces WHERE model IS NOT NULL')
                with_model = cursor.fetchone()[0]
                if with_model > 0:
                    print(f"   ✅ Events with model data: {with_model}")
                else:
                    print(f"   ⚠️  No events with model data (hooks may need update)")
                
                cursor = conn.execute('SELECT COUNT(*) FROM raw_traces WHERE event_type = "database_trace"')
                db_traces = cursor.fetchone()[0]
                if db_traces > 0:
                    print(f"   ✅ Database traces: {db_traces}")
                else:
                    print(f"   ⚠️  No database traces (extension may not be active)")
                    
            return True
        except Exception as e:
            print(f"   ❌ Database error: {e}")
            return False
    else:
        print(f"❌ Database not found: {db_path}")
        return False


def check_processing_server():
    """Check if processing server is running."""
    print("\n5️⃣  PROCESSING SERVER STATUS")
    print("-" * 70)
    result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
    server_processes = [line for line in result.stdout.split('\n') 
                       if 'start_server' in line or 'processing.server' in line]
    if server_processes:
        print("✅ Processing server running:")
        for proc in server_processes[:3]:
            parts = proc.split()
            if len(parts) > 1:
                pid = parts[1]
                print(f"   PID: {pid}")
        return True
    else:
        print("❌ Processing server not running!")
        print("   Start with: python scripts/start_server.py")
        return False


def main():
    """Run all status checks."""
    print("=" * 70)
    print("BLUEPLANE TELEMETRY CORE - COMPREHENSIVE STATUS CHECK")
    print("=" * 70)
    
    results = {
        'hooks': check_hooks(),
        'database_traces': check_database_traces(),
        'redis': check_redis_queue(),
        'database': check_database(),
        'server': check_processing_server(),
    }
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("-" * 70)
    for component, status in results.items():
        status_icon = "✅" if status else "❌"
        print(f"{status_icon} {component.replace('_', ' ').title()}")
    
    all_ok = all(results.values())
    print("\n" + "=" * 70)
    if all_ok:
        print("✅ All systems operational")
    else:
        print("⚠️  Some issues detected - see details above")
    print("=" * 70)
    
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())

