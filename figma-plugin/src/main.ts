/**
 * Plugin sandbox entry point (main.ts).
 * This file runs in Figma's plugin sandbox — it has access to the Figma API
 * but not the DOM. It communicates with the UI iframe via postMessage.
 *
 * Responsibilities:
 * - Listen to selection changes and notify the UI
 * - Handle 'start-export' messages: parse the selected frame and return DesignSpec
 * - Handle 'cancel-export' messages: abort any in-progress export
 * - Report progress to the UI
 */

import type { PluginToUIMessage, UIToPluginMessage, ExportSettings } from './types/messages';
import { DEFAULT_EXPORT_SETTINGS } from './types/messages';
import { parseFrame, ProgressCallback } from './parser/index';
import { countDescendants } from './utils/figmaHelpers';

// ─── State ────────────────────────────────────────────────────────────────────

let currentSettings: ExportSettings = { ...DEFAULT_EXPORT_SETTINGS };
let isExporting = false;
let cancelRequested = false;

// ─── Plugin Initialization ────────────────────────────────────────────────────

/**
 * Show the plugin UI.
 * The UI is loaded from dist/ui.html (built by esbuild).
 */
figma.showUI(__html__, {
  width: 400,
  height: 600,
  themeColors: true,
  title: 'Figma to HTML/CSS',
});

// Notify UI that plugin is ready
sendToUI({ type: 'plugin-ready' });

// Send initial selection state
handleSelectionChange();

// ─── Event Listeners ──────────────────────────────────────────────────────────

/**
 * Listen for selection changes in the Figma editor.
 */
figma.on('selectionchange', () => {
  handleSelectionChange();
});

/**
 * Listen for messages from the UI iframe.
 */
figma.ui.onmessage = (msg: UIToPluginMessage) => {
  switch (msg.type) {
    case 'start-export':
      handleStartExport(msg.settings);
      break;

    case 'cancel-export':
      handleCancelExport();
      break;

    case 'update-settings':
      handleUpdateSettings(msg.settings);
      break;

    case 'resize-ui':
      figma.ui.resize(msg.width, msg.height);
      break;

    default:
      console.warn('Unknown message type from UI:', (msg as any).type);
  }
};

// ─── Selection Handling ───────────────────────────────────────────────────────

/**
 * Handle selection changes: notify the UI about the current selection state.
 */
function handleSelectionChange(): void {
  const selection = figma.currentPage.selection;

  if (selection.length === 0) {
    sendToUI({
      type: 'selection-changed',
      hasSelection: false,
    });
    return;
  }

  // Get the first selected node
  const selectedNode = selection[0];

  // Check if it's a valid frame-like node we can export
  if (!isExportableNode(selectedNode)) {
    sendToUI({
      type: 'selection-changed',
      hasSelection: false,
    });
    return;
  }

  const bounds = selectedNode.absoluteBoundingBox;
  const nodeCount = countDescendants(selectedNode);

  sendToUI({
    type: 'selection-changed',
    hasSelection: true,
    frameName: selectedNode.name,
    frameWidth: bounds ? Math.round(bounds.width) : 0,
    frameHeight: bounds ? Math.round(bounds.height) : 0,
    nodeCount,
  });
}

/**
 * Check if a node is a valid exportable frame-like container.
 */
function isExportableNode(node: SceneNode): boolean {
  return (
    node.type === 'FRAME' ||
    node.type === 'COMPONENT' ||
    node.type === 'INSTANCE' ||
    node.type === 'SECTION' ||
    node.type === 'GROUP'
  );
}

// ─── Export Handling ──────────────────────────────────────────────────────────

/**
 * Handle the 'start-export' message from the UI.
 * Validates selection, runs the parser, and sends the DesignSpec back.
 */
async function handleStartExport(settings?: ExportSettings): Promise<void> {
  if (isExporting) {
    sendToUI({
      type: 'export-error',
      error: 'An export is already in progress. Please wait or cancel it first.',
    });
    return;
  }

  // Apply settings if provided
  if (settings) {
    currentSettings = { ...currentSettings, ...settings };
  }

  // Validate selection
  const selection = figma.currentPage.selection;

  if (selection.length === 0) {
    sendToUI({
      type: 'export-error',
      error: 'No frame selected. Please select a frame, component, or section to export.',
    });
    return;
  }

  const selectedNode = selection[0];

  if (!isExportableNode(selectedNode)) {
    sendToUI({
      type: 'export-error',
      error: `Cannot export a ${selectedNode.type} node. Please select a Frame, Component, Instance, or Section.`,
    });
    return;
  }

  // Start export
  isExporting = true;
  cancelRequested = false;
  const startTime = Date.now();

  try {
    // Progress callback: forward parser progress to the UI
    const onProgress: ProgressCallback = (step, progress, detail) => {
      if (cancelRequested) {
        throw new Error('Export cancelled by user');
      }

      sendToUI({
        type: 'export-progress',
        step,
        progress,
        detail,
      });
    };

    sendToUI({
      type: 'export-progress',
      step: 'Starting export...',
      progress: 0,
      detail: `Frame: ${selectedNode.name}`,
    });

    // Run the parser
    const designSpec = await parseFrame(
      selectedNode as FrameNode | ComponentNode | InstanceNode | SectionNode,
      currentSettings,
      onProgress
    );

    // Calculate extraction time
    const extractionTimeMs = Date.now() - startTime;

    // Send the result to the UI
    sendToUI({
      type: 'export-complete',
      designSpec,
      extractionTimeMs,
    });

    // Show success notification
    figma.notify(
      `Export complete: ${designSpec.nodes.length > 0 ? countAllNodes(designSpec.nodes) : 0} nodes, ` +
      `${designSpec.assets.length} assets (${(extractionTimeMs / 1000).toFixed(1)}s)`,
      { timeout: 4000 }
    );

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    const stack = error instanceof Error ? error.stack : undefined;

    if (errorMessage === 'Export cancelled by user') {
      sendToUI({
        type: 'export-progress',
        step: 'Export cancelled',
        progress: 0,
      });
      figma.notify('Export cancelled', { timeout: 2000 });
    } else {
      sendToUI({
        type: 'export-error',
        error: errorMessage,
        stack,
      });
      figma.notify(`Export failed: ${errorMessage}`, { timeout: 4000, error: true });
    }
  } finally {
    isExporting = false;
    cancelRequested = false;
  }
}

/**
 * Handle export cancellation request from the UI.
 */
function handleCancelExport(): void {
  if (isExporting) {
    cancelRequested = true;
    figma.notify('Cancelling export...', { timeout: 2000 });
  }
}

/**
 * Handle settings updates from the UI.
 */
function handleUpdateSettings(settings: ExportSettings): void {
  currentSettings = { ...currentSettings, ...settings };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Send a typed message to the UI iframe.
 */
function sendToUI(message: PluginToUIMessage): void {
  figma.ui.postMessage(message);
}

/**
 * Count total nodes in a tree of DesignNodes.
 */
function countAllNodes(nodes: Array<{ children: any[] }>): number {
  let count = 0;
  for (const node of nodes) {
    count++;
    if (node.children && node.children.length > 0) {
      count += countAllNodes(node.children);
    }
  }
  return count;
}
