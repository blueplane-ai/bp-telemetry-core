# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
HTTP Endpoint for Hook Event Submission.

Provides a lightweight HTTP server for receiving telemetry events from
zero-dependency hooks. Uses Python stdlib only (http.server).

Endpoints:
- POST /events - Accept hook events, return 202 Accepted
- GET /health - Health check
"""

import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server for concurrent request handling."""

    daemon_threads = True  # Threads die when main thread dies
    allow_reuse_address = True  # Allow quick restart after shutdown


def create_handler_factory(
    enqueue_func: Callable[[Dict[str, Any], str, str], bool],
) -> type:
    """
    Create a request handler class with access to the enqueue function.

    Args:
        enqueue_func: Function to enqueue events (typically MessageQueueWriter.enqueue)

    Returns:
        Request handler class
    """

    class HookEventHandler(BaseHTTPRequestHandler):
        """Handle HTTP requests for hook event submission."""

        # Suppress default logging to stderr
        def log_message(self, format: str, *args) -> None:
            logger.debug("HTTP: %s", format % args)

        def _send_response(self, status: int, body: Dict[str, Any]) -> None:
            """Send JSON response."""
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode("utf-8"))

        def do_GET(self) -> None:
            """Handle GET requests (health check)."""
            if self.path == "/health":
                self._send_response(200, {"status": "ok"})
            else:
                self._send_response(404, {"error": "Not found"})

        def do_POST(self) -> None:
            """Handle POST requests (event submission)."""
            if self.path != "/events":
                self._send_response(404, {"error": "Not found"})
                return

            try:
                # Read request body
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length == 0:
                    self._send_response(400, {"error": "Empty request body"})
                    return

                # Limit body size (1MB max)
                if content_length > 1048576:
                    self._send_response(413, {"error": "Request body too large"})
                    return

                body = self.rfile.read(content_length)

                # Parse JSON
                try:
                    data = json.loads(body.decode("utf-8"))
                except json.JSONDecodeError as e:
                    self._send_response(400, {"error": f"Invalid JSON: {e}"})
                    return

                # Validate required fields
                if not isinstance(data, dict):
                    self._send_response(400, {"error": "Request body must be a JSON object"})
                    return

                event = data.get("event")
                platform = data.get("platform")
                session_id = data.get("session_id")

                if not event:
                    self._send_response(400, {"error": "Missing 'event' field"})
                    return

                if not platform:
                    self._send_response(400, {"error": "Missing 'platform' field"})
                    return

                if not session_id:
                    self._send_response(400, {"error": "Missing 'session_id' field"})
                    return

                # Enqueue event (fire-and-forget on client side, but we log failures)
                success = enqueue_func(event, platform, session_id)

                if success:
                    # Return 202 Accepted - event queued for processing
                    self._send_response(202, {"status": "accepted"})
                else:
                    # Return 503 Service Unavailable - Redis not available
                    self._send_response(503, {"error": "Event queue unavailable"})

            except Exception as e:
                logger.error("Error processing event: %s", e, exc_info=True)
                self._send_response(500, {"error": "Internal server error"})

    return HookEventHandler


class HTTPEndpoint:
    """
    HTTP endpoint for receiving hook events.

    Runs in a separate thread and receives events from zero-dependency hooks
    via HTTP POST, then forwards them to the Redis message queue.
    """

    def __init__(
        self,
        enqueue_func: Callable[[Dict[str, Any], str, str], bool],
        host: str = "127.0.0.1",
        port: int = 8787,
    ):
        """
        Initialize HTTP endpoint.

        Args:
            enqueue_func: Function to enqueue events to Redis
            host: Host to bind to (default: localhost only)
            port: Port to listen on (default: 8787)
        """
        self.host = host
        self.port = port
        self.enqueue_func = enqueue_func
        self.server: Optional[ThreadedHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.running = False

    def start(self) -> None:
        """Start the HTTP server in a background thread."""
        if self.running:
            logger.warning("HTTP endpoint already running")
            return

        try:
            # Create handler class with access to enqueue function
            handler_class = create_handler_factory(self.enqueue_func)

            # Create and start server
            self.server = ThreadedHTTPServer((self.host, self.port), handler_class)

            def serve():
                logger.info(f"HTTP endpoint listening on {self.host}:{self.port}")
                self.server.serve_forever()

            self.thread = threading.Thread(target=serve, daemon=True)
            self.thread.start()
            self.running = True

            logger.info(f"HTTP endpoint started on {self.host}:{self.port}")

        except OSError as e:
            if "Address already in use" in str(e):
                logger.error(f"Port {self.port} is already in use. "
                           f"Check if another server is running or choose a different port.")
            raise

    def stop(self) -> None:
        """Stop the HTTP server."""
        if not self.running:
            return

        logger.info("Stopping HTTP endpoint...")

        if self.server:
            self.server.shutdown()
            self.server.server_close()

        self.running = False
        logger.info("HTTP endpoint stopped")

    def health_check(self) -> bool:
        """Check if the HTTP server is healthy."""
        return self.running and self.server is not None
