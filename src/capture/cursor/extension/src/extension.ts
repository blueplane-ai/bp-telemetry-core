// Copyright © 2025 Sierra Labs LLC
// SPDX-License-Identifier: AGPL-3.0-only
// License-Filename: LICENSE

/**
 * Blueplane Telemetry Extension for Cursor
 *
 * Main entry point for the VSCode extension.
 * Manages session lifecycle.
 */

import * as vscode from "vscode";
import { SessionManager } from "./sessionManager";
import { HTTPQueueWriter } from "./httpQueueWriter";
import { ExtensionConfig, loadExtensionConfig } from "./config";

let sessionManager: SessionManager | undefined;
let queueWriter: HTTPQueueWriter | undefined;
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
      queueWriter = new HTTPQueueWriter(config);
      sessionManager = new SessionManager(context, config, queueWriter);
    } catch (error) {
      console.error("Failed to initialize Blueplane components:", error);
      vscode.window.showErrorMessage(
        `Blueplane: Failed to initialize. Error: ${
          error instanceof Error ? error.message : String(error)
        }`
      );
      return;
    }

    // Initialize HTTP queue writer
    try {
      const initialized = await queueWriter.initialize();
      if (!initialized) {
        vscode.window.showWarningMessage(
          "Blueplane: Invalid server configuration. Telemetry will not be captured."
        );
        return;
      }
    } catch (error) {
      console.error("Failed to initialize HTTP queue writer:", error);
      vscode.window.showWarningMessage(
        `Blueplane: HTTP queue writer initialization failed. Telemetry will not be captured. Error: ${
          error instanceof Error ? error.message : String(error)
        }`
      );
      return;
    }

    // Start new session (only if workspace is available)
    try {
      const session = sessionManager.startNewSession();
      if (!session) {
        console.log("Session not started - workspace not available yet");
      }
    } catch (error) {
      console.error("Failed to start session:", error);
      // Continue anyway - session is not critical
    }

    // Register commands first (before creating status bar item that references them)
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
        vscode.workspace.onDidChangeWorkspaceFolders((event) => {
          try {
            if (sessionManager) {
              // Stop existing session if workspace was removed
              if (event.removed.length > 0) {
                sessionManager.stopSession();
              }

              // Start new session if workspace was added
              if (event.added.length > 0) {
                const session = sessionManager.startNewSession();
                if (session) {
                  console.log(`Started session for new workspace: ${session.sessionId}`);
                }
              }
            }
          } catch (error) {
            console.error("Error handling workspace change:", error);
          }
        })
      );
    } catch (error) {
      console.error("Failed to register commands:", error);
      // Continue anyway - commands are not critical
    }

    // Create status bar item after commands are registered
    try {
      statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
      );
      statusBarItem.text = "$(pulse) Blueplane";
      statusBarItem.tooltip = "Blueplane Telemetry Active";
      statusBarItem.command = "blueplane.showStatus";
      context.subscriptions.push(statusBarItem);
      
      // Show status bar item after a short delay to ensure UI is ready
      setTimeout(() => {
        try {
          if (statusBarItem) {
            statusBarItem.show();
          }
        } catch (error) {
          console.error("Failed to show status bar item:", error);
        }
      }, 100);
    } catch (error) {
      console.error("Failed to create status bar item:", error);
      // Continue anyway - status bar is not critical
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

  // Stop session
  if (sessionManager) {
    sessionManager.stopSession();
  }

  // Disconnect HTTP queue writer (no-op for HTTP, but kept for API compatibility)
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
 * Load configuration from config.yaml and VSCode settings.
 * VSCode settings override config.yaml values.
 */
function loadConfiguration(): ExtensionConfig {
  // Load from config.yaml first
  const baseConfig = loadExtensionConfig();

  // VSCode settings can override specific values
  const vsConfig = vscode.workspace.getConfiguration("blueplane");

  return {
    // Enabled is primarily controlled by VSCode setting
    enabled: vsConfig.get<boolean>("enabled", baseConfig.enabled),

    // Server URL can be overridden via VSCode settings
    serverUrl: vsConfig.get<string>("serverUrl", baseConfig.serverUrl),

    // HTTP timeout can be overridden via VSCode settings
    httpTimeout: vsConfig.get<number>("httpTimeout", baseConfig.httpTimeout),

    // Other settings use config.yaml values but can be overridden
    sessionDirectory: vsConfig.get<string>("sessionDirectory", baseConfig.sessionDirectory),
    hashTruncateLength: vsConfig.get<number>("hashTruncateLength", baseConfig.hashTruncateLength),
  };
}
