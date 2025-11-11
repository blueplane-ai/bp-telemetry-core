// Copyright © 2025 Sierra Labs LLC
// SPDX-License-Identifier: AGPL-3.0-only
// License-Filename: LICENSE

/**
 * Database Monitor for Cursor Extension
 *
 * Monitors Cursor's SQLite database for trace events.
 * Uses dual strategy: file watcher + polling.
 */

import * as fs from "fs";
import * as path from "path";
import * as os from "os";
import Database from "better-sqlite3";
import chokidar from "chokidar";
import { QueueWriter } from "./queueWriter";
import { TelemetryEvent } from "./types";

export class DatabaseMonitor {
  private dbPath: string | null = null;
  private db: Database.Database | null = null;
  private watcher: chokidar.FSWatcher | null = null;
  private pollInterval: NodeJS.Timeout | null = null;
  private lastDataVersion: number = 0;
  private isMonitoring: boolean = false;
  private getSessionInfo:
    | (() => { sessionId: string; workspaceHash: string } | null)
    | null = null;

  constructor(private queueWriter: QueueWriter) {
    // getSessionInfo will be set via setSessionInfoGetter after initialization
  }

  /**
   * Set the session info getter function
   * This method allows setting the callback after construction to avoid initialization order issues
   */
  setSessionInfoGetter(
    getSessionInfo: () => { sessionId: string; workspaceHash: string } | null
  ): void {
    this.getSessionInfo = getSessionInfo;
  }

  /**
   * Start monitoring Cursor's database
   */
  async startMonitoring(): Promise<boolean> {
    try {
      // Find Cursor's database
      this.dbPath = this.locateCursorDatabase();
      if (!this.dbPath) {
        console.warn("Could not locate Cursor database");
        return false;
      }

      console.log(`Found Cursor database at: ${this.dbPath}`);

      // Check if file exists before opening
      if (!fs.existsSync(this.dbPath)) {
        console.warn(`Cursor database file does not exist: ${this.dbPath}`);
        return false;
      }

      // Open database in read-only mode
      try {
        this.db = new Database(this.dbPath, {
          readonly: true,
          fileMustExist: true,
        });
      } catch (dbError) {
        console.error(`Failed to open database at ${this.dbPath}:`, dbError);
        // Database might be locked or corrupted - this is not fatal
        return false;
      }

      // Get initial data version
      try {
        this.lastDataVersion = this.getCurrentDataVersion();
      } catch (versionError) {
        console.warn("Failed to get initial data version:", versionError);
        // Continue anyway - version check will retry
        this.lastDataVersion = 0;
      }

      // Start file watcher (primary method)
      try {
        this.startFileWatcher();
      } catch (watcherError) {
        console.warn("Failed to start file watcher:", watcherError);
        // Continue with polling only
      }

      // Start polling (backup method, every 30 seconds)
      try {
        this.startPolling(30000);
      } catch (pollError) {
        console.error("Failed to start polling:", pollError);
        // If both watcher and polling fail, return false
        if (!this.watcher) {
          return false;
        }
      }

      this.isMonitoring = true;
      return true;
    } catch (error) {
      console.error("Failed to start database monitoring:", error);
      // Clean up on error
      this.stopMonitoring();
      return false;
    }
  }

  /**
   * Stop monitoring
   */
  stopMonitoring(): void {
    if (this.watcher) {
      this.watcher.close();
      this.watcher = null;
    }

    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }

    if (this.db) {
      this.db.close();
      this.db = null;
    }

    this.isMonitoring = false;
    console.log("Stopped database monitoring");
  }

  /**
   * Locate Cursor's SQLite database
   */
  private locateCursorDatabase(): string | null {
    const homeDir = os.homedir();

    // macOS path
    const macPath = path.join(
      homeDir,
      "Library/Application Support/Cursor/User/workspaceStorage"
    );

    // Linux path
    const linuxPath = path.join(
      homeDir,
      ".config/Cursor/User/workspaceStorage"
    );

    // Windows path
    const winPath = path.join(
      homeDir,
      "AppData/Roaming/Cursor/User/workspaceStorage"
    );

    // Try each platform path
    for (const basePath of [macPath, linuxPath, winPath]) {
      if (fs.existsSync(basePath)) {
        // Find workspace directories
        const workspaces = fs.readdirSync(basePath);
        for (const workspace of workspaces) {
          const dbFile = path.join(basePath, workspace, "state.vscdb");
          if (fs.existsSync(dbFile)) {
            return dbFile;
          }
        }
      }
    }

    return null;
  }

  /**
   * Start file watcher for real-time monitoring
   */
  private startFileWatcher(): void {
    if (!this.dbPath) return;

    this.watcher = chokidar.watch(this.dbPath, {
      persistent: true,
      ignoreInitial: true,
      awaitWriteFinish: {
        stabilityThreshold: 100,
        pollInterval: 100,
      },
    });

    this.watcher.on("change", () => {
      this.checkForChanges();
    });

    console.log("Started file watcher for database");
  }

  /**
   * Start polling as backup monitoring method
   */
  private startPolling(intervalMs: number): void {
    this.pollInterval = setInterval(() => {
      this.checkForChanges();
    }, intervalMs);

    console.log(`Started polling every ${intervalMs}ms`);
  }

  /**
   * Check for database changes
   */
  private checkForChanges(): void {
    if (!this.db || !this.isMonitoring) {
      return;
    }

    try {
      const currentVersion = this.getCurrentDataVersion();

      if (currentVersion > this.lastDataVersion) {
        console.log(
          `Data version changed: ${this.lastDataVersion} -> ${currentVersion}`
        );
        this.captureChanges(this.lastDataVersion, currentVersion);
        this.lastDataVersion = currentVersion;
      }
    } catch (error) {
      console.error("Error checking for changes:", error);
      // If database becomes unavailable, stop monitoring
      if (error instanceof Error && error.message.includes("database")) {
        console.warn("Database appears to be unavailable, stopping monitoring");
        this.stopMonitoring();
      }
    }
  }

  /**
   * Get current max data_version from database
   */
  private getCurrentDataVersion(): number {
    if (!this.db) return 0;

    try {
      const row = this.db
        .prepare(
          'SELECT MAX(data_version) as max_version FROM "aiService.generations"'
        )
        .get() as { max_version: number };

      return row?.max_version || 0;
    } catch (error) {
      // Table might not exist yet or database might be locked
      console.debug("Could not get data version:", error);
      return 0;
    }
  }

  /**
   * Capture changes between data versions
   */
  private captureChanges(fromVersion: number, toVersion: number): void {
    if (!this.db) return;

    try {
      // Query new generations with associated prompts (if table exists)
      // Try to join with prompts table to get prompt text
      let generations: any[];

      try {
        generations = this.db
          .prepare(
            `SELECT 
              g.*,
              p.text as prompt_text,
              p.timestamp as prompt_timestamp
             FROM "aiService.generations" g
             LEFT JOIN "aiService.prompts" p ON json_extract(g.value, '$.promptId') = p.uuid
             WHERE g.data_version > ? AND g.data_version <= ?
             ORDER BY g.data_version ASC`
          )
          .all(fromVersion, toVersion) as any[];
      } catch (joinError) {
        // If join fails (table doesn't exist or schema mismatch), fall back to simple query
        console.debug(
          "Could not join prompts table, using simple query:",
          joinError
        );
        generations = this.db
          .prepare(
            `SELECT * FROM "aiService.generations"
             WHERE data_version > ? AND data_version <= ?
             ORDER BY data_version ASC`
          )
          .all(fromVersion, toVersion) as any[];
      }

      console.log(`Found ${generations.length} new generations`);

      // Process each generation
      for (const gen of generations) {
        this.processGeneration(gen);
      }
    } catch (error) {
      console.error("Error capturing changes:", error);
    }
  }

  /**
   * Process a single generation event
   */
  private processGeneration(gen: any): void {
    if (!this.getSessionInfo) {
      console.debug("No session info getter available, skipping generation");
      return;
    }

    const session = this.getSessionInfo();
    if (!session) {
      console.debug("No active session, skipping generation");
      return;
    }

    if (!this.queueWriter || !this.queueWriter.isConnected()) {
      console.debug("QueueWriter not available, skipping generation");
      return;
    }

    try {
      // Parse generation value (JSON)
      const value =
        typeof gen.value === "string" ? JSON.parse(gen.value) : gen.value;

      // Create trace event (use snake_case for consistency with Python hooks)
      const event: TelemetryEvent = {
        version: "0.1.0",
        hookType: "DatabaseTrace",
        eventType: "database_trace",
        timestamp: new Date().toISOString(),
        payload: {
          trace_type: "generation",
          generation_id: gen.uuid,
          data_version: gen.data_version,

          // Model and token info
          model: value?.model || "unknown",
          tokens_used: value?.tokensUsed || value?.completionTokens || 0,
          prompt_tokens: value?.promptTokens || 0,
          completion_tokens: value?.completionTokens || 0,

          // Full content (privacy-aware)
          response_text: value?.responseText || value?.text || "",
          prompt_text: gen.prompt_text || "", // From joined prompts table
          prompt_id: value?.promptId || "",

          // Request metadata
          request_parameters: value?.requestParameters || {},

          // Timestamps
          generation_timestamp: value?.timestamp || gen.timestamp || "",
          prompt_timestamp: gen.prompt_timestamp || "",

          // Include full value for complete capture
          full_generation_data: value,
        },
        metadata: {
          workspace_hash: session.workspaceHash,
        },
      };

      // Send to message queue (fire and forget)
      this.queueWriter
        .enqueue(event, "cursor", session.sessionId)
        .catch((error) => {
          console.error("Failed to enqueue generation event:", error);
        });

      console.debug(`Captured generation: ${gen.uuid}`);
    } catch (error) {
      console.error("Error processing generation:", error);
      // Don't throw - continue processing other generations
    }
  }

  /**
   * Check if monitoring is active
   */
  isActive(): boolean {
    return this.isMonitoring;
  }
}
