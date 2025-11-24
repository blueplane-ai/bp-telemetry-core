// Copyright © 2025 Sierra Labs LLC
// SPDX-License-Identifier: AGPL-3.0-only
// License-Filename: LICENSE

/**
 * Redis Streams Message Queue Writer (TypeScript)
 *
 * TypeScript version of the queue writer for use in the extension.
 */

import { createClient, RedisClientType } from "redis";
import { TelemetryEvent } from "./types";
import { randomUUID } from "crypto";

export class QueueWriter {
  private client: RedisClientType | null = null;
  private connected: boolean = false;

  constructor(
    private redisHost: string = "localhost",
    private redisPort: number = 6379
  ) {}

  /**
   * Initialize Redis connection
   */
  async initialize(): Promise<boolean> {
    try {
      this.client = createClient({
        socket: {
          host: this.redisHost,
          port: this.redisPort,
          connectTimeout: 5000, // Increased timeout
          reconnectStrategy: (retries) => {
            // Don't retry indefinitely
            if (retries > 3) {
              console.warn("Redis reconnection failed after 3 attempts");
              return false;
            }
            return Math.min(retries * 100, 3000);
          },
        },
      });

      this.client.on("error", (err) => {
        console.error("Redis Client Error:", err);
        this.connected = false;
      });

      this.client.on("connect", () => {
        console.log("Connected to Redis");
        this.connected = true;
      });

      this.client.on("reconnecting", () => {
        console.log("Redis reconnecting...");
        this.connected = false;
      });

      await this.client.connect();
      await this.client.ping();

      this.connected = true;
      return true;
    } catch (error) {
      console.warn("Failed to connect to Redis:", error);
      this.connected = false;
      // Clean up client on failure
      if (this.client) {
        try {
          await this.client.quit();
        } catch (quitError) {
          // Ignore quit errors
        }
        this.client = null;
      }
      return false;
    }
  }

  /**
   * Enqueue event to Redis Streams
   */
  async enqueue(
    event: TelemetryEvent,
    platform: string,
    sessionId: string
  ): Promise<boolean> {
    if (!this.client || !this.connected) {
      console.debug("Redis not connected, skipping event");
      return false;
    }

    try {
      const eventId = randomUUID();
      const enqueuedAt = new Date().toISOString();

      // Build Redis stream entry (flat key-value pairs)
      const streamEntry: Record<string, string> = {
        event_id: eventId,
        enqueued_at: enqueuedAt,
        retry_count: "0",
        platform: platform,
        external_session_id: sessionId,
        hook_type: event.hookType,
        timestamp: event.timestamp,
        event_type: event.eventType,
      };

      // Serialize complex data to JSON
      if (event.payload) {
        streamEntry.payload = JSON.stringify(event.payload);
      }

      if (event.metadata) {
        streamEntry.metadata = JSON.stringify(event.metadata);
      }

      // Write to Redis Stream with auto-trim
      await this.client.xAdd(
        "telemetry:events",
        "*", // Auto-generate ID
        streamEntry,
        {
          TRIM: {
            strategy: "MAXLEN",
            strategyModifier: "~",
            threshold: 10000,
          },
        }
      );

      console.debug(`Enqueued event ${eventId} to telemetry:events`);
      return true;
    } catch (error) {
      console.error("Failed to enqueue event:", error);
      return false;
    }
  }

  /**
   * Check if Redis is connected
   */
  isConnected(): boolean {
    return this.connected;
  }

  /**
   * Disconnect from Redis
   */
  async disconnect(): Promise<void> {
    if (this.client) {
      await this.client.quit();
      this.connected = false;
    }
  }

  /**
   * Get queue statistics
   */
  async getQueueStats(): Promise<any> {
    if (!this.client || !this.connected) {
      return null;
    }

    try {
      const info = await this.client.xInfoStream("telemetry:events");
      return {
        length: info.length,
        firstEntry: info["first-entry"],
        lastEntry: info["last-entry"],
        groups: info.groups,
      };
    } catch (error) {
      console.error("Failed to get queue stats:", error);
      return null;
    }
  }
}
