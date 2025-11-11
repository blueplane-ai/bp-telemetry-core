// Copyright © 2025 Sierra Labs LLC
// SPDX-License-Identifier: AGPL-3.0-only
// License-Filename: LICENSE

/**
 * Database Monitor for Cursor Extension
 *
 * Monitors Cursor's SQLite database for trace events.
 * Uses dual strategy: file watcher + polling.
 */

import * as fs from 'fs';
import * as path from 'path';
import * as os from 'os';
import Database from 'better-sqlite3';
import chokidar from 'chokidar';
import { QueueWriter } from './queueWriter';
import { SessionManager } from './sessionManager';
import { GenerationData, TelemetryEvent } from './types';

export class DatabaseMonitor {
  private dbPath: string | null = null;
  private db: Database.Database | null = null;
  private watcher: chokidar.FSWatcher | null = null;
  private pollInterval: NodeJS.Timeout | null = null;
  private lastDataVersion: number = 0;
  private isMonitoring: boolean = false;

  constructor(
    private queueWriter: QueueWriter,
    private sessionManager: SessionManager
  ) {}

  /**
   * Start monitoring Cursor's database
   */
  async startMonitoring(): Promise<boolean> {
    try {
      // Find Cursor's database
      this.dbPath = this.locateCursorDatabase();
      if (!this.dbPath) {
        console.warn('Could not locate Cursor database');
        return false;
      }

      console.log(`Found Cursor database at: ${this.dbPath}`);

      // Open database in read-only mode
      this.db = new Database(this.dbPath, { readonly: true, fileMustExist: true });

      // Get initial data version
      this.lastDataVersion = this.getCurrentDataVersion();

      // Start file watcher (primary method)
      this.startFileWatcher();

      // Start polling (backup method, every 30 seconds)
      this.startPolling(30000);

      this.isMonitoring = true;
      return true;
    } catch (error) {
      console.error('Failed to start database monitoring:', error);
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
    console.log('Stopped database monitoring');
  }

  /**
   * Locate Cursor's SQLite database
   */
  private locateCursorDatabase(): string | null {
    const homeDir = os.homedir();

    // macOS path
    const macPath = path.join(
      homeDir,
      'Library/Application Support/Cursor/User/workspaceStorage'
    );

    // Linux path
    const linuxPath = path.join(
      homeDir,
      '.config/Cursor/User/workspaceStorage'
    );

    // Windows path
    const winPath = path.join(
      homeDir,
      'AppData/Roaming/Cursor/User/workspaceStorage'
    );

    // Try each platform path
    for (const basePath of [macPath, linuxPath, winPath]) {
      if (fs.existsSync(basePath)) {
        // Find workspace directories
        const workspaces = fs.readdirSync(basePath);
        for (const workspace of workspaces) {
          const dbFile = path.join(basePath, workspace, 'state.vscdb');
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

    this.watcher.on('change', () => {
      this.checkForChanges();
    });

    console.log('Started file watcher for database');
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
    try {
      const currentVersion = this.getCurrentDataVersion();

      if (currentVersion > this.lastDataVersion) {
        console.log(`Data version changed: ${this.lastDataVersion} -> ${currentVersion}`);
        this.captureChanges(this.lastDataVersion, currentVersion);
        this.lastDataVersion = currentVersion;
      }
    } catch (error) {
      console.error('Error checking for changes:', error);
    }
  }

  /**
   * Get current max data_version from database
   */
  private getCurrentDataVersion(): number {
    if (!this.db) return 0;

    try {
      const row = this.db.prepare(
        'SELECT MAX(data_version) as max_version FROM "aiService.generations"'
      ).get() as { max_version: number };

      return row?.max_version || 0;
    } catch (error) {
      // Table might not exist yet
      return 0;
    }
  }

  /**
   * Capture changes between data versions
   */
  private captureChanges(fromVersion: number, toVersion: number): void {
    if (!this.db) return;

    try {
      // Query new generations
      const generations = this.db.prepare(
        `SELECT * FROM "aiService.generations"
         WHERE data_version > ? AND data_version <= ?
         ORDER BY data_version ASC`
      ).all(fromVersion, toVersion) as any[];

      console.log(`Found ${generations.length} new generations`);

      // Process each generation
      for (const gen of generations) {
        this.processGeneration(gen);
      }
    } catch (error) {
      console.error('Error capturing changes:', error);
    }
  }

  /**
   * Process a single generation event
   */
  private processGeneration(gen: any): void {
    const session = this.sessionManager.getCurrentSession();
    if (!session) {
      console.debug('No active session, skipping generation');
      return;
    }

    try {
      // Parse generation value (JSON)
      const value = typeof gen.value === 'string'
        ? JSON.parse(gen.value)
        : gen.value;

      // Create trace event (use snake_case for consistency with Python hooks)
      const event: TelemetryEvent = {
        version: '0.1.0',
        hookType: 'DatabaseTrace',
        eventType: 'database_trace',
        timestamp: new Date().toISOString(),
        payload: {
          trace_type: 'generation',
          generation_id: gen.uuid,
          data_version: gen.data_version,
          model: value.model,
          tokens_used: value.tokensUsed || value.completionTokens,
        },
        metadata: {
          workspace_hash: session.workspaceHash,
        },
      };

      // Send to message queue
      this.queueWriter.enqueue(event, 'cursor', session.sessionId);

      console.debug(`Captured generation: ${gen.uuid}`);
    } catch (error) {
      console.error('Error processing generation:', error);
    }
  }

  /**
   * Check if monitoring is active
   */
  isActive(): boolean {
    return this.isMonitoring;
  }
}
