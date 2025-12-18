// Copyright © 2025 Sierra Labs LLC
// SPDX-License-Identifier: AGPL-3.0-only
// License-Filename: LICENSE

/**
 * HTTP Queue Writer for Cursor Extension
 *
 * Zero-dependency HTTP-based event submission.
 * Sends telemetry events to the Blueplane server via HTTP POST.
 */

import * as http from "http";
import { TelemetryEvent } from "./types";
import { ExtensionConfig } from "./config";

/**
 * HTTP-based queue writer for telemetry events
 *
 * Similar to Claude Code HTTP hooks, this sends events to the server
 * via HTTP POST, and the server queues them to Redis.
 */
export class HTTPQueueWriter {
  private serverUrl: string;
  private timeout: number;

  constructor(private config: ExtensionConfig) {
    // Use server URL from config
    this.serverUrl = config.serverUrl || "http://127.0.0.1:8787";
    this.timeout = config.httpTimeout || 1000; // 1 second default
  }

  /**
   * Initialize (no-op for HTTP client, kept for API compatibility)
   */
  async initialize(): Promise<boolean> {
    // No initialization needed for HTTP client
    // Just verify server URL is valid
    try {
      new URL(this.serverUrl);
      console.log(`HTTP queue writer initialized (server: ${this.serverUrl})`);
      return true;
    } catch (error) {
      console.error(`Invalid server URL: ${this.serverUrl}`, error);
      return false;
    }
  }

  /**
   * Enqueue event via HTTP POST to server
   */
  async enqueue(
    event: TelemetryEvent,
    platform: string,
    sessionId: string
  ): Promise<boolean> {
    return new Promise((resolve) => {
      try {
        const url = new URL("/events", this.serverUrl);

        // Build request payload
        const payload = {
          event: event,
          platform: platform,
          session_id: sessionId,
        };

        const data = JSON.stringify(payload);

        const options: http.RequestOptions = {
          hostname: url.hostname,
          port: url.port || 8787,
          path: url.pathname,
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Content-Length": Buffer.byteLength(data),
          },
          timeout: this.timeout,
        };

        const req = http.request(options, (res) => {
          // Consume response data to free up memory
          res.on("data", () => {});

          res.on("end", () => {
            // Success if 202 Accepted
            if (res.statusCode === 202) {
              console.debug(
                `Event enqueued successfully (session: ${sessionId})`
              );
              resolve(true);
            } else {
              console.error(`Server returned ${res.statusCode} for event`);
              resolve(false);
            }
          });
        });

        req.on("error", (error) => {
          console.error("HTTP request failed:", error.message);
          resolve(false);
        });

        req.on("timeout", () => {
          console.error("HTTP request timed out");
          req.destroy();
          resolve(false);
        });

        // Send request
        req.write(data);
        req.end();
      } catch (error) {
        console.error("Failed to send HTTP request:", error);
        resolve(false);
      }
    });
  }

  /**
   * Check if HTTP client is ready
   */
  isConnected(): boolean {
    // HTTP client is always "connected" (no persistent connection)
    return true;
  }

  /**
   * Disconnect (no-op for HTTP client, kept for API compatibility)
   */
  async disconnect(): Promise<void> {
    // No persistent connection to close
    console.log("HTTP queue writer disconnected (no-op)");
  }

  /**
   * Get queue statistics (not available for HTTP client)
   */
  async getQueueStats(): Promise<any> {
    return null;
  }
}
