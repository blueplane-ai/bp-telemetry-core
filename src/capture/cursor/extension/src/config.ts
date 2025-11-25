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
 * Search order (highest to lowest precedence):
 * 1. User override: ~/.blueplane/config.yaml (user override, highest precedence)
 * 2. Bundled config: out/config/config.yaml (relative to extension installation - works in VSIX)
 * 3. Development config: Project root config/config.yaml (for development mode)
 */
function findConfigFile(): string | null {
  const os = require("os");

  // 1. User override (highest precedence)
  // This takes precedence over all bundled configs
  const userConfigPath = path.join(os.homedir(), ".blueplane", "config.yaml");
  try {
    if (fs.existsSync(userConfigPath)) {
      return userConfigPath;
    }
  } catch (error) {
    // Continue searching on error (permissions, etc.)
  }

  // 2. Bundled config (for VSIX installations)
  // When packaged, config is at out/config/config.yaml relative to extension.js
  // __dirname points to out/ directory where extension.js lives
  const bundledConfigPath = path.join(__dirname, "config", "config.yaml");
  try {
    if (fs.existsSync(bundledConfigPath)) {
      return bundledConfigPath;
    }
  } catch (error) {
    // Continue searching on error
  }

  // 3. Development config (for development mode)
  // Try to find project root config/config.yaml
  // Walk up from out/ to find project root
  let current = __dirname; // Start at out/
  for (let i = 0; i < 10; i++) {
    // Safety limit: don't walk too far up
    const projectConfigPath = path.join(
      current,
      "..",
      "..",
      "..",
      "config",
      "config.yaml"
    );
    try {
      if (fs.existsSync(projectConfigPath)) {
        return projectConfigPath;
      }
    } catch (error) {
      // Continue searching
    }
    const parent = path.dirname(current);
    if (parent === current) {
      // Reached filesystem root
      break;
    }
    current = parent;
  }

  return null;
}

/**
 * Export default config for use in tests or as fallback.
 */
export const DEFAULT_EXTENSION_CONFIG = DEFAULT_CONFIG;
