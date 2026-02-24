/**
 * Message types for communication between the plugin sandbox (main.ts)
 * and the UI iframe (ui.ts).
 *
 * The Figma plugin architecture uses a message-passing model:
 * - Plugin sandbox -> UI: figma.ui.postMessage(msg)
 * - UI -> Plugin sandbox: parent.postMessage({ pluginMessage: msg }, '*')
 */

import type { DesignSpec } from './designSpec';

// ─── Plugin -> UI Messages ────────────────────────────────────────────────────

export interface SelectionChangedMessage {
  type: 'selection-changed';
  /** Whether a valid frame is currently selected */
  hasSelection: boolean;
  /** Name of the selected frame (if any) */
  frameName?: string;
  /** Width of the selected frame */
  frameWidth?: number;
  /** Height of the selected frame */
  frameHeight?: number;
  /** Number of child nodes in the selection */
  nodeCount?: number;
}

export interface ExportCompleteMessage {
  type: 'export-complete';
  /** The full design specification */
  designSpec: DesignSpec;
  /** Time taken to extract the spec, in milliseconds */
  extractionTimeMs: number;
}

export interface ExportErrorMessage {
  type: 'export-error';
  /** Human-readable error message */
  error: string;
  /** Optional stack trace for debugging */
  stack?: string;
}

export interface ExportProgressMessage {
  type: 'export-progress';
  /** Current step name */
  step: string;
  /** Progress fraction (0 to 1) */
  progress: number;
  /** Optional detail message */
  detail?: string;
}

export interface PluginReadyMessage {
  type: 'plugin-ready';
}

export type PluginToUIMessage =
  | SelectionChangedMessage
  | ExportCompleteMessage
  | ExportErrorMessage
  | ExportProgressMessage
  | PluginReadyMessage;

// ─── UI -> Plugin Messages ────────────────────────────────────────────────────

export interface StartExportMessage {
  type: 'start-export';
  /** Export settings from the UI */
  settings?: ExportSettings;
}

export interface CancelExportMessage {
  type: 'cancel-export';
}

export interface UpdateSettingsMessage {
  type: 'update-settings';
  settings: ExportSettings;
}

export interface ResizeUIMessage {
  type: 'resize-ui';
  width: number;
  height: number;
}

export type UIToPluginMessage =
  | StartExportMessage
  | CancelExportMessage
  | UpdateSettingsMessage
  | ResizeUIMessage;

// ─── Shared Settings ──────────────────────────────────────────────────────────

export interface ExportSettings {
  /** Backend API URL */
  backendUrl: string;
  /** Whether to include invisible nodes */
  includeInvisible: boolean;
  /** Whether to export assets (images, complex vectors) */
  exportAssets: boolean;
  /** Asset export format */
  assetFormat: 'PNG' | 'SVG';
  /** Asset export scale */
  assetScale: number;
  /** Maximum depth to traverse the node tree (0 = unlimited) */
  maxDepth: number;
}

/** Default export settings */
export const DEFAULT_EXPORT_SETTINGS: ExportSettings = {
  backendUrl: 'http://localhost:8000',
  includeInvisible: false,
  exportAssets: true,
  assetFormat: 'PNG',
  assetScale: 2,
  maxDepth: 0,
};
