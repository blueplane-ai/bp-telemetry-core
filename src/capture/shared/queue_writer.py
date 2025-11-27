# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Redis Streams Message Queue Writer.

Writes telemetry events to Redis Streams with at-least-once delivery.
Implements fire-and-forget pattern with silent failure to never block IDE operations.
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

try:
    import redis
    from redis.exceptions import RedisError, ConnectionError, TimeoutError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .config import Config


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MessageQueueWriter:
    """
    Write events to Redis Streams message queue.

    Shared by all platforms (Claude Code, Cursor, etc.).
    Implements fire-and-forget pattern with silent failure.

    Features:
    - Atomic XADD operations
    - Connection pooling
    - 1-second timeout
    - Silent failure (never blocks IDE)
    - Auto-trim to prevent unbounded growth
    - Dead Letter Queue (DLQ) support
    """

    def __init__(self, config: Optional[Config] = None, stream_type: str = "message_queue"):
        """
        Initialize message queue writer.

        Args:
            config: Configuration object (auto-loads if None)
            stream_type: Stream type to write to ("events" for hooks, "message_queue" for monitors)
        """
        if not REDIS_AVAILABLE:
            logger.warning("Redis library not available - events will not be queued")
            self._redis_client = None
            return

        # Load configuration
        self.config = config or Config()

        # Redis connection
        self._redis_client: Optional[redis.Redis] = None
        self._connection_pool: Optional[redis.ConnectionPool] = None

        # Stream configuration
        self.stream_config = self.config.get_stream_config(stream_type)
        self.dlq_config = self.config.get_stream_config("dlq")

        # Initialize connection
        self._initialize_connection()

    def _initialize_connection(self) -> None:
        """
        Initialize Redis connection with pooling.

        Silently fails if Redis is not available.
        """
        try:
            redis_config = self.config.redis

            # Create connection pool
            self._connection_pool = redis.ConnectionPool(
                host=redis_config.host,
                port=redis_config.port,
                db=0,  # Redis default database
                max_connections=redis_config.max_connections,
                socket_timeout=redis_config.socket_timeout,
                socket_connect_timeout=redis_config.socket_connect_timeout,
                decode_responses=False,  # We handle encoding
            )

            # Create Redis client
            self._redis_client = redis.Redis(
                connection_pool=self._connection_pool
            )

            # Test connection with ping
            self._redis_client.ping()
            logger.info("Successfully connected to Redis at %s:%d",
                       redis_config.host, redis_config.port)

        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.warning("Failed to connect to Redis: %s - Events will not be queued", e)
            self._redis_client = None
        except Exception as e:
            logger.warning("Unexpected error initializing Redis: %s", e)
            self._redis_client = None

    def enqueue(
        self,
        event: Dict[str, Any],
        platform: str,
        session_id: str
    ) -> bool:
        """
        Write event to Redis Streams message queue.

        This is the main entry point for all hook scripts.

        Args:
            event: Event dictionary with hook_type, timestamp, payload
            platform: Platform identifier (claude_code, cursor)
            session_id: Session identifier

        Returns:
            True on success, False on failure (silent failure)

        Implementation:
        1. Validate event structure
        2. Generate event_id (UUID)
        3. Add enqueued_at timestamp
        4. Flatten event to Redis hash format
        5. XADD to telemetry:events with MAXLEN ~10000
        6. Return success/failure (never raises exceptions)
        """
        # Early return if Redis not available
        if not REDIS_AVAILABLE or self._redis_client is None:
            logger.debug("Redis not available, skipping event")
            return False

        try:
            # Generate event ID
            event_id = str(uuid.uuid4())
            enqueued_at = datetime.now(timezone.utc).isoformat()

            # Validate event (basic check)
            if not isinstance(event, dict):
                logger.error("Event must be a dictionary")
                return False

            required_fields = ["hook_type", "timestamp"]
            for field in required_fields:
                if field not in event:
                    logger.error("Event missing required field: %s", field)
                    return False

            # Build Redis stream entry (flat key-value pairs)
            # Redis Streams requires all values to be strings
            stream_entry = {
                'event_id': event_id,
                'enqueued_at': enqueued_at,
                'retry_count': '0',
                'platform': platform,
                'session_id': session_id,  # Used by session_monitor
                'external_session_id': session_id,  # Legacy field, kept for compatibility
                'hook_type': event['hook_type'],
                'timestamp': event['timestamp'],
            }

            # Add event_type if present
            if 'event_type' in event:
                stream_entry['event_type'] = event['event_type']

            # Serialize complex data (payload, metadata) to JSON
            if 'payload' in event:
                stream_entry['payload'] = json.dumps(event['payload'])

            if 'metadata' in event:
                stream_entry['metadata'] = json.dumps(event['metadata'])

            # Add any additional top-level fields
            for key, value in event.items():
                if key not in ['hook_type', 'timestamp', 'payload', 'metadata', 'event_type']:
                    # Store additional fields as JSON
                    if isinstance(value, (dict, list)):
                        stream_entry[key] = json.dumps(value)
                    else:
                        stream_entry[key] = str(value)

            # Write to Redis Streams with auto-trim
            message_id = self._redis_client.xadd(
                name=self.stream_config.name,
                fields=stream_entry,
                maxlen=self.stream_config.max_length,
                approximate=self.stream_config.trim_approximate
            )

            logger.debug(
                "Enqueued event %s to stream %s with ID %s",
                event_id,
                self.stream_config.name,
                message_id
            )

            return True

        except (ConnectionError, TimeoutError) as e:
            # Network/timeout errors - log but don't raise
            logger.warning("Network error writing to Redis: %s", e)
            return False

        except RedisError as e:
            # Redis-specific errors
            logger.error("Redis error: %s", e)
            return False

        except Exception as e:
            # Catch-all for unexpected errors
            logger.error("Unexpected error enqueueing event: %s", e, exc_info=True)
            return False

    def enqueue_to_dlq(
        self,
        original_event: Dict[str, Any],
        error_type: str,
        error_message: str,
        retry_count: int = 0
    ) -> bool:
        """
        Write failed event to Dead Letter Queue.

        Args:
            original_event: The original event that failed
            error_type: Type of error (processing_error, validation_error, etc.)
            error_message: Error message description
            retry_count: Number of retry attempts

        Returns:
            True on success, False on failure
        """
        if not REDIS_AVAILABLE or self._redis_client is None:
            return False

        try:
            dlq_entry = {
                'original_event_id': original_event.get('event_id', 'unknown'),
                'original_data': json.dumps(original_event),
                'error_type': error_type,
                'error_message': error_message,
                'retry_count': str(retry_count),
                'dlq_queued_at': datetime.now(timezone.utc).isoformat(),
                'can_retry': 'true' if retry_count < 3 else 'false',
            }

            self._redis_client.xadd(
                name=self.dlq_config.name,
                fields=dlq_entry,
                maxlen=self.dlq_config.max_length,
                approximate=True
            )

            logger.info("Sent event to DLQ: %s", error_message)
            return True

        except Exception as e:
            logger.error("Failed to write to DLQ: %s", e)
            return False

    def health_check(self) -> bool:
        """
        Check if Redis connection is healthy.

        Returns:
            True if connected and responsive, False otherwise
        """
        if not REDIS_AVAILABLE or self._redis_client is None:
            return False

        try:
            self._redis_client.ping()
            return True
        except Exception:
            return False

    def get_queue_stats(self) -> Optional[Dict[str, Any]]:
        """
        Get statistics about the message queue.

        Returns:
            Dictionary with queue stats or None if unavailable
        """
        if not REDIS_AVAILABLE or self._redis_client is None:
            return None

        try:
            info = self._redis_client.xinfo_stream(self.stream_config.name)
            return {
                'length': info.get('length', 0),
                'first_entry': info.get('first-entry'),
                'last_entry': info.get('last-entry'),
                'groups': info.get('groups', 0),
            }
        except Exception as e:
            logger.error("Failed to get queue stats: %s", e)
            return None

    def close(self) -> None:
        """Close Redis connection and cleanup."""
        if self._connection_pool:
            self._connection_pool.disconnect()
            logger.info("Closed Redis connection pool")
