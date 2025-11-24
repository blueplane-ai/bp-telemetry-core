/*
 * Copyright © 2025 Sierra Labs LLC
 * SPDX-License-Identifier: AGPL-3.0-only
 * License-Filename: LICENSE
 */

/**
 * Configuration loader for Cursor VSCode extension.
 * Reads from the main project config.yaml to maintain single source of truth.
 */

import * as fs from "fs";
import * as path from "path";
import * as yaml from "js-yaml";

// =============================================================================
// TYPE DEFINITIONS
// =============================================================================

export interface RedisConfig {
  /** Redis host */
  host: string;
  /** Redis port */
  port: number;
}

export interface ExtensionConfig {
  /** Enable/disable telemetry capture */
  enabled: boolean;

  /** Redis connection settings */
  redis: RedisConfig;

  /** Connection timeout (milliseconds) */
  connectTimeout: number;

  /** Maximum reconnection attempts */
  maxReconnectAttempts: number;

  /** Base delay for exponential backoff (milliseconds) */
  reconnectBackoffBase: number;

  /** Maximum backoff delay (milliseconds) */
  reconnectBackoffMax: number;

  /** Stream trim threshold (max length) */
  streamTrimThreshold: number;

  /** Session directory relative to home (e.g., ".blueplane/cursor-session") */
  sessionDirectory: string;

  /** Hash truncation length for workspace hashes */
  hashTruncateLength: number;
}

// =============================================================================
// DEFAULT VALUES (fallback if config not found)
// =============================================================================

const DEFAULT_CONFIG: ExtensionConfig = {
  enabled: true,
  redis: {
    host: "localhost",
    port: 6379,
  },
  connectTimeout: 5000,
  maxReconnectAttempts: 3,
  reconnectBackoffBase: 100,
  reconnectBackoffMax: 3000,
  streamTrimThreshold: 10000,
  sessionDirectory: ".blueplane/cursor-session",
  hashTruncateLength: 16, // Not configurable in config.yaml
};

// =============================================================================
// CONFIG LOADER
// =============================================================================

/**
 * Load extension configuration from project config.yaml.
 * Falls back to defaults if config file not found or values missing.
 *
 * @param configPath Optional path to config.yaml. If not provided, searches standard locations.
 * @returns ExtensionConfig with values from YAML or defaults
 */
export function loadExtensionConfig(configPath?: string): ExtensionConfig {
  let config: any = {};

  // Try to load config.yaml
  try {
    const yamlPath = configPath || findConfigFile();
    if (yamlPath && fs.existsSync(yamlPath)) {
      const fileContents = fs.readFileSync(yamlPath, "utf8");
      config = yaml.load(fileContents) || {};
      console.log(`Loaded extension config from: ${yamlPath}`);
    } else {
      console.log("Config file not found, using defaults");
    }
  } catch (error) {
    console.warn("Failed to load config.yaml, using defaults:", error);
  }

  // Extract extension-relevant values from the main config
  // Map main config structure to extension config structure
  return {
    enabled: DEFAULT_CONFIG.enabled, // Extension enabled by default, controlled by VSCode settings

    redis: {
      host: config?.redis?.connection?.host || DEFAULT_CONFIG.redis.host,
      port: config?.redis?.connection?.port || DEFAULT_CONFIG.redis.port,
    },

    connectTimeout:
      config?.timeouts?.extension?.connect_timeout ||
      DEFAULT_CONFIG.connectTimeout,

    maxReconnectAttempts:
      config?.timeouts?.extension?.max_reconnect_attempts ||
      DEFAULT_CONFIG.maxReconnectAttempts,

    reconnectBackoffBase:
      config?.timeouts?.extension?.reconnect_backoff_base ||
      DEFAULT_CONFIG.reconnectBackoffBase,

    reconnectBackoffMax:
      config?.timeouts?.extension?.reconnect_backoff_max ||
      DEFAULT_CONFIG.reconnectBackoffMax,

    streamTrimThreshold:
      config?.streams?.message_queue?.max_length ||
      DEFAULT_CONFIG.streamTrimThreshold,

    sessionDirectory:
      stripHomePrefix(config?.paths?.cursor_sessions_dir) ||
      DEFAULT_CONFIG.sessionDirectory,

    hashTruncateLength: DEFAULT_CONFIG.hashTruncateLength, // Not configurable in config.yaml
  };
}

/**
 * Strip home directory prefix (~/) from path.
 * Returns the path relative to home, or null if input is null/undefined.
 */
function stripHomePrefix(pathStr: string | undefined | null): string | null {
  if (!pathStr) return null;

  // Remove leading ~/ or ~/
  if (pathStr.startsWith("~/")) {
    return pathStr.substring(2);
  }

  return pathStr;
}

/**
 * Find config.yaml in standard locations.
 * Search order:
 * 1. Project root (../../../../../../config/config.yaml from src/capture/cursor/extension/src/)
 * 2. ~/.blueplane/config.yaml
 */
function findConfigFile(): string | null {
  const searchPaths = [
    // Relative to extension source (src/capture/cursor/extension/src/config.ts)
    // Go up to project root: ../../../../../.. then into config/
    path.join(__dirname, "..", "..", "..", "..", "..", "config", "config.yaml"),

    // User home directory
    path.join(require("os").homedir(), ".blueplane", "config.yaml"),
  ];

  for (const searchPath of searchPaths) {
    try {
      if (fs.existsSync(searchPath)) {
        return searchPath;
      }
    } catch (error) {
      // Continue searching
    }
  }

  return null;
}

/**
 * Export default config for use in tests or as fallback.
 */
export const DEFAULT_EXTENSION_CONFIG = DEFAULT_CONFIG;
