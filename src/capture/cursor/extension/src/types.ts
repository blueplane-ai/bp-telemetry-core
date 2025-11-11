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
 * Database trace event from Cursor's SQLite database
 */
export interface DatabaseTrace {
  uuid: string;
  dataVersion: number;
  timestamp: Date;
  model?: string;
  promptData?: PromptData;
  composerData?: ComposerData;
}

/**
 * Prompt data from aiService.prompts table
 */
export interface PromptData {
  uuid: string;
  text?: string; // Not captured for privacy
  textHash?: string;
  timestamp: Date;
}

/**
 * Composer data from composer.composerData table
 */
export interface ComposerData {
  uuid: string;
  sessionId?: string;
  timestamp: Date;
}

/**
 * Generation data from aiService.generations table
 */
export interface GenerationData {
  uuid: string;
  dataVersion: number;
  value: {
    model?: string;
    promptId?: string;
    responseText?: string; // Not captured for privacy
    tokensUsed?: number;
    completionTokens?: number;
    promptTokens?: number;
  };
  timestamp: Date;
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

/**
 * Configuration for the extension
 */
export interface ExtensionConfig {
  enabled: boolean;
  databaseMonitoring: boolean;
  redisHost: string;
  redisPort: number;
}
