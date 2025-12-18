#!/usr/bin/env python3
# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Initialize Redis Streams for Blueplane Telemetry Core.

Creates consumer groups and verifies Redis connectivity.
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    import redis
    from redis.exceptions import RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    print("Error: Redis library not installed. Run: pip install redis")
    sys.exit(1)

from capture.shared.config import Config


def check_redis_connection(host: str, port: int) -> bool:
    """
    Check if Redis is running and accessible.

    Args:
        host: Redis host
        port: Redis port

    Returns:
        True if connected, False otherwise
    """
    try:
        client = redis.Redis(host=host, port=port, socket_timeout=2)
        client.ping()
        print(f"✅ Connected to Redis at {host}:{port}")
        return True
    except Exception as e:
        print(f"❌ Failed to connect to Redis at {host}:{port}: {e}")
        return False


def create_consumer_group(client: redis.Redis, stream: str, group: str) -> bool:
    """
    Create consumer group for a stream.

    Args:
        client: Redis client
        stream: Stream name
        group: Consumer group name

    Returns:
        True if created or already exists, False on error
    """
    try:
        # Try to create the stream and consumer group
        client.xgroup_create(stream, group, id='$', mkstream=True)
        print(f"✅ Created consumer group '{group}' for stream '{stream}'")
        return True
    except redis.ResponseError as e:
        if 'BUSYGROUP' in str(e):
            # Group already exists - that's fine
            print(f"ℹ️  Consumer group '{group}' already exists for stream '{stream}'")
            return True
        else:
            print(f"❌ Error creating consumer group '{group}': {e}")
            return False
    except Exception as e:
        print(f"❌ Unexpected error creating consumer group: {e}")
        return False


def initialize_streams(host: str, port: int) -> bool:
    """
    Initialize all required streams and consumer groups.

    Args:
        host: Redis host
        port: Redis port

    Returns:
        True if successful, False otherwise
    """
    try:
        client = redis.Redis(host=host, port=port, socket_timeout=5)

        # Define streams and consumer groups
        streams = [
            ('telemetry:message_queue', 'processors'),
            ('cdc:events', 'workers'),
        ]

        print("\n🔧 Initializing Redis Streams...")

        all_success = True
        for stream_name, group_name in streams:
            success = create_consumer_group(client, stream_name, group_name)
            if not success:
                all_success = False

        return all_success

    except Exception as e:
        print(f"❌ Failed to initialize streams: {e}")
        return False


def verify_setup(host: str, port: int) -> bool:
    """
    Verify Redis setup is correct.

    Args:
        host: Redis host
        port: Redis port

    Returns:
        True if verified, False otherwise
    """
    try:
        client = redis.Redis(host=host, port=port, socket_timeout=5)

        print("\n🔍 Verifying Redis setup...")

        # Check streams exist
        streams = ['telemetry:message_queue', 'cdc:events']
        for stream in streams:
            try:
                info = client.xinfo_stream(stream)
                print(f"✅ Stream '{stream}' exists (length: {info.get('length', 0)})")
            except Exception as e:
                print(f"❌ Stream '{stream}' check failed: {e}")
                return False

        # Check consumer groups
        groups = [
            ('telemetry:message_queue', 'processors'),
            ('cdc:events', 'workers'),
        ]
        for stream, group in groups:
            try:
                group_info = client.xinfo_groups(stream)
                group_names = [g['name'].decode() if isinstance(g['name'], bytes) else g['name']
                              for g in group_info]
                if group in group_names:
                    print(f"✅ Consumer group '{group}' exists for '{stream}'")
                else:
                    print(f"❌ Consumer group '{group}' not found for '{stream}'")
                    return False
            except Exception as e:
                print(f"❌ Group check failed for '{stream}': {e}")
                return False

        print("\n✅ All Redis streams and consumer groups verified!")
        return True

    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return False


def main():
    """Main entry point."""
    # Load config to get default Redis connection settings
    default_host = 'localhost'
    default_port = 6379
    try:
        config = Config()
        redis_config = config.redis
        default_host = redis_config.host
        default_port = redis_config.port
    except Exception as e:
        print(f"Warning: Could not load config, using defaults: {e}", file=sys.stderr)

    parser = argparse.ArgumentParser(
        description='Initialize Redis Streams for Blueplane Telemetry'
    )
    parser.add_argument(
        '--host',
        default=default_host,
        help=f'Redis host (default: {default_host} from config)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=default_port,
        help=f'Redis port (default: {default_port} from config)'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify setup, don\'t create anything'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Blueplane Telemetry - Redis Initialization")
    print("=" * 60)

    # Check connection
    if not check_redis_connection(args.host, args.port):
        print("\n❌ Cannot proceed without Redis connection.")
        print("\n💡 To start Redis:")
        print("   - macOS: brew services start redis")
        print("   - Linux: sudo systemctl start redis")
        print("   - Docker: docker run -d -p 6379:6379 redis:latest")
        return 1

    if args.verify_only:
        # Only verify
        success = verify_setup(args.host, args.port)
        return 0 if success else 1
    else:
        # Initialize streams
        init_success = initialize_streams(args.host, args.port)
        if not init_success:
            print("\n❌ Initialization failed")
            return 1

        # Verify
        verify_success = verify_setup(args.host, args.port)
        if not verify_success:
            print("\n⚠️  Initialization completed but verification failed")
            return 1

        print("\n" + "=" * 60)
        print("✅ Redis initialization completed successfully!")
        print("=" * 60)
        return 0


if __name__ == '__main__':
    sys.exit(main())
