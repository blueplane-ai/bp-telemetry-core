// Copyright © 2025 Sierra Labs LLC
// SPDX-License-Identifier: AGPL-3.0-only
// License-Filename: LICENSE

/**
 * TypeScript type definitions for Cursor extension.
 */

/**
 * Session information
 */
export interface SessionInfo {
  sessionId: string;
  workspaceHash: string;
  startedAt: Date;
  platform: 'cursor';
}

/**
 * Telemetry event for message queue
 */
export interface TelemetryEvent {
  version: string;
  hookType: string;
  eventType: string;
  timestamp: string;
  payload: Record<string, any>;
  metadata?: Record<string, any>;
}
