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
 * Uses snake_case to match Python backend conventions
 */
export interface TelemetryEvent {
  version: string;
  hook_type: string;
  event_type: string;
  timestamp: string;
  payload: Record<string, any>;
  metadata?: Record<string, any>;
}
