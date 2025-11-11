// Copyright © 2025 Sierra Labs LLC
// SPDX-License-Identifier: AGPL-3.0-only
// License-Filename: LICENSE

/**
 * Blueplane Telemetry Extension for Cursor
 *
 * Main entry point for the VSCode extension.
 * Manages session lifecycle and database monitoring.
 */

import * as vscode from "vscode";
import { SessionManager } from "./sessionManager";
import { DatabaseMonitor } from "./databaseMonitor";
import { QueueWriter } from "./queueWriter";
import { ExtensionConfig } from "./types";

let sessionManager: SessionManager | undefined;
let databaseMonitor: DatabaseMonitor | undefined;
let queueWriter: QueueWriter | undefined;
let statusBarItem: vscode.StatusBarItem | undefined;

/**
 * Extension activation
 */
export async function activate(context: vscode.ExtensionContext) {
  try {
    console.log("Blueplane Telemetry extension activating...");

    // Load configuration
    const config = loadConfiguration();

    if (!config.enabled) {
      console.log("Blueplane Telemetry is disabled");
      return;
    }

    // Initialize components
    try {
      queueWriter = new QueueWriter(config.redisHost, config.redisPort);
      sessionManager = new SessionManager(context, queueWriter);
    } catch (error) {
      console.error("Failed to initialize Blueplane components:", error);
      vscode.window.showErrorMessage(
        `Blueplane: Failed to initialize. Error: ${
          error instanceof Error ? error.message : String(error)
        }`
      );
      return;
    }

    // Create database monitor after sessionManager is initialized
    // Use setter method to avoid any closure capture issues during construction
    try {
      databaseMonitor = new DatabaseMonitor(queueWriter);
      // Set the session info getter after construction to avoid initialization order issues
      databaseMonitor.setSessionInfoGetter(() => {
        if (!sessionManager) {
          return null;
        }
        const session = sessionManager.getCurrentSession();
        return session
          ? {
              sessionId: session.sessionId,
              workspaceHash: session.workspaceHash,
            }
          : null;
      });
    } catch (error) {
      console.error("Failed to initialize DatabaseMonitor:", error);
      vscode.window.showErrorMessage(
        `Blueplane: Failed to initialize DatabaseMonitor. Error: ${
          error instanceof Error ? error.message : String(error)
        }`
      );
      return;
    }

    // Initialize Redis connection
    try {
      const redisConnected = await queueWriter.initialize();
      if (!redisConnected) {
        vscode.window.showWarningMessage(
          "Blueplane: Could not connect to Redis. Telemetry will not be captured."
        );
        return;
      }
    } catch (error) {
      console.error("Failed to connect to Redis:", error);
      vscode.window.showWarningMessage(
        `Blueplane: Redis connection failed. Telemetry will not be captured. Error: ${
          error instanceof Error ? error.message : String(error)
        }`
      );
      return;
    }

    // Start new session
    try {
      sessionManager.startNewSession();
    } catch (error) {
      console.error("Failed to start session:", error);
      // Continue anyway - session is not critical
    }

    // Start database monitoring if enabled
    if (config.databaseMonitoring) {
      try {
        const monitoringStarted = await databaseMonitor.startMonitoring();
        if (!monitoringStarted) {
          console.warn("Database monitoring could not be started");
        }
      } catch (error) {
        console.error("Failed to start database monitoring:", error);
        // Continue anyway - database monitoring is optional
      }
    }

    // Create status bar item
    try {
      statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
      );
      statusBarItem.text = "$(pulse) Blueplane";
      statusBarItem.tooltip = "Blueplane Telemetry Active";
      statusBarItem.command = "blueplane.showStatus";
      statusBarItem.show();
      context.subscriptions.push(statusBarItem);
    } catch (error) {
      console.error("Failed to create status bar item:", error);
      // Continue anyway - status bar is not critical
    }

    // Register commands
    try {
      context.subscriptions.push(
        vscode.commands.registerCommand("blueplane.showStatus", () => {
          try {
            if (sessionManager) {
              sessionManager.showStatus();
            }
          } catch (error) {
            console.error("Error showing status:", error);
          }
        })
      );

      context.subscriptions.push(
        vscode.commands.registerCommand("blueplane.newSession", () => {
          try {
            if (sessionManager) {
              sessionManager.stopSession();
              sessionManager.startNewSession();
              vscode.window.showInformationMessage(
                "Started new Blueplane session"
              );
            }
          } catch (error) {
            console.error("Error starting new session:", error);
            vscode.window.showErrorMessage("Failed to start new session");
          }
        })
      );

      context.subscriptions.push(
        vscode.commands.registerCommand("blueplane.stopSession", () => {
          try {
            if (sessionManager) {
              sessionManager.stopSession();
              vscode.window.showInformationMessage("Stopped Blueplane session");
            }
          } catch (error) {
            console.error("Error stopping session:", error);
            vscode.window.showErrorMessage("Failed to stop session");
          }
        })
      );

      // Handle workspace changes
      context.subscriptions.push(
        vscode.workspace.onDidChangeWorkspaceFolders(() => {
          try {
            if (sessionManager) {
              // Start new session for new workspace
              sessionManager.stopSession();
              sessionManager.startNewSession();
            }
          } catch (error) {
            console.error("Error handling workspace change:", error);
          }
        })
      );
    } catch (error) {
      console.error("Failed to register commands:", error);
      // Continue anyway
    }

    console.log("Blueplane Telemetry extension activated successfully");
  } catch (error) {
    console.error("Fatal error during extension activation:", error);
    vscode.window.showErrorMessage(
      `Blueplane: Extension activation failed. Error: ${
        error instanceof Error ? error.message : String(error)
      }`
    );
  }
}

/**
 * Extension deactivation
 */
export async function deactivate() {
  console.log("Blueplane Telemetry extension deactivating...");

  // Stop monitoring
  if (databaseMonitor) {
    databaseMonitor.stopMonitoring();
  }

  // Stop session
  if (sessionManager) {
    sessionManager.stopSession();
  }

  // Disconnect from Redis
  if (queueWriter) {
    await queueWriter.disconnect();
  }

  // Hide status bar
  if (statusBarItem) {
    statusBarItem.hide();
    statusBarItem.dispose();
  }

  console.log("Blueplane Telemetry extension deactivated");
}

/**
 * Load configuration from VSCode settings
 */
function loadConfiguration(): ExtensionConfig {
  const config = vscode.workspace.getConfiguration("blueplane");

  return {
    enabled: config.get<boolean>("enabled", true),
    databaseMonitoring: config.get<boolean>("databaseMonitoring", true),
    redisHost: config.get<string>("redisHost", "localhost"),
    redisPort: config.get<number>("redisPort", 6379),
  };
}
