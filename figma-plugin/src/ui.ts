/**
 * UI logic for the Figma-to-HTML/CSS plugin.
 * This runs inside the plugin's UI iframe and handles:
 * - User interactions (export button, settings)
 * - Communication with the plugin sandbox via postMessage
 * - Communication with the backend API via HTTP and WebSocket
 * - Progress display and result presentation
 */

import type { PluginToUIMessage, UIToPluginMessage, ExportSettings } from './types/messages';
import { DEFAULT_EXPORT_SETTINGS } from './types/messages';
import type { DesignSpec } from './types/designSpec';
import type {
  CreateJobRequest,
  CreateJobResponse,
  JobStatusResponse,
  WebSocketMessage,
  JobResult,
} from './types/api';

// ─── State ────────────────────────────────────────────────────────────────────

let settings: ExportSettings = { ...DEFAULT_EXPORT_SETTINGS };
let currentDesignSpec: DesignSpec | null = null;
let currentJobId: string | null = null;
let currentWebSocket: WebSocket | null = null;
let isExporting = false;

// ─── DOM Elements ─────────────────────────────────────────────────────────────

function getEl<T extends HTMLElement>(id: string): T {
  return document.getElementById(id) as T;
}

// ─── Initialization ───────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initializeUI();
  loadSavedSettings();
  attachEventListeners();
});

/**
 * Set up the initial UI state.
 */
function initializeUI(): void {
  showSection('empty-state');
  hideSection('frame-info');
  hideSection('progress-section');
  hideSection('results-section');
  hideSection('error-section');
  setExportButtonEnabled(false);
}

/**
 * Attach event listeners to UI controls.
 */
function attachEventListeners(): void {
  // Export button
  const exportBtn = getEl<HTMLButtonElement>('export-btn');
  if (exportBtn) {
    exportBtn.addEventListener('click', handleExportClick);
  }

  // Cancel button
  const cancelBtn = getEl<HTMLButtonElement>('cancel-btn');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', handleCancelClick);
  }

  // Settings inputs
  const backendUrlInput = getEl<HTMLInputElement>('backend-url');
  if (backendUrlInput) {
    backendUrlInput.value = settings.backendUrl;
    backendUrlInput.addEventListener('change', () => {
      settings.backendUrl = backendUrlInput.value.trim() || DEFAULT_EXPORT_SETTINGS.backendUrl;
      saveSettings();
    });
  }

  const includeInvisibleCheck = getEl<HTMLInputElement>('include-invisible');
  if (includeInvisibleCheck) {
    includeInvisibleCheck.checked = settings.includeInvisible;
    includeInvisibleCheck.addEventListener('change', () => {
      settings.includeInvisible = includeInvisibleCheck.checked;
      saveSettings();
    });
  }

  const exportAssetsCheck = getEl<HTMLInputElement>('export-assets');
  if (exportAssetsCheck) {
    exportAssetsCheck.checked = settings.exportAssets;
    exportAssetsCheck.addEventListener('change', () => {
      settings.exportAssets = exportAssetsCheck.checked;
      saveSettings();
    });
  }

  const assetFormatSelect = getEl<HTMLSelectElement>('asset-format');
  if (assetFormatSelect) {
    assetFormatSelect.value = settings.assetFormat;
    assetFormatSelect.addEventListener('change', () => {
      settings.assetFormat = assetFormatSelect.value as 'PNG' | 'SVG';
      saveSettings();
    });
  }

  const assetScaleSelect = getEl<HTMLSelectElement>('asset-scale');
  if (assetScaleSelect) {
    assetScaleSelect.value = String(settings.assetScale);
    assetScaleSelect.addEventListener('change', () => {
      settings.assetScale = Number(assetScaleSelect.value) || 2;
      saveSettings();
    });
  }

  // Settings toggle
  const settingsToggle = getEl<HTMLButtonElement>('settings-toggle');
  if (settingsToggle) {
    settingsToggle.addEventListener('click', () => {
      const settingsPanel = getEl<HTMLDivElement>('settings-panel');
      if (settingsPanel) {
        const isHidden = settingsPanel.style.display === 'none' || !settingsPanel.style.display;
        settingsPanel.style.display = isHidden ? 'block' : 'none';
        settingsToggle.textContent = isHidden ? 'Hide Settings' : 'Settings';
      }
    });
  }

  // New export button (in results section)
  const newExportBtn = getEl<HTMLButtonElement>('new-export-btn');
  if (newExportBtn) {
    newExportBtn.addEventListener('click', () => {
      hideSection('results-section');
      hideSection('error-section');
      showSection('frame-info');
      setExportButtonEnabled(true);
    });
  }
}

// ─── Plugin Message Handling ──────────────────────────────────────────────────

/**
 * Listen for messages from the plugin sandbox.
 */
window.onmessage = (event: MessageEvent) => {
  const msg = event.data.pluginMessage as PluginToUIMessage;
  if (!msg || !msg.type) return;

  switch (msg.type) {
    case 'plugin-ready':
      break;

    case 'selection-changed':
      handleSelectionChanged(msg);
      break;

    case 'export-progress':
      handleExportProgress(msg);
      break;

    case 'export-complete':
      handleExportComplete(msg);
      break;

    case 'export-error':
      handleExportError(msg);
      break;
  }
};

/**
 * Handle selection change from the plugin.
 */
function handleSelectionChanged(msg: Extract<PluginToUIMessage, { type: 'selection-changed' }>): void {
  if (isExporting) return; // Don't update during export

  if (msg.hasSelection) {
    hideSection('empty-state');
    showSection('frame-info');

    const frameName = getEl<HTMLSpanElement>('frame-name');
    const frameDimensions = getEl<HTMLSpanElement>('frame-dimensions');
    const nodeCount = getEl<HTMLSpanElement>('node-count');

    if (frameName) frameName.textContent = msg.frameName ?? 'Unknown';
    if (frameDimensions) frameDimensions.textContent = `${msg.frameWidth ?? 0} x ${msg.frameHeight ?? 0}`;
    if (nodeCount) nodeCount.textContent = `${msg.nodeCount ?? 0} nodes`;

    setExportButtonEnabled(true);
  } else {
    showSection('empty-state');
    hideSection('frame-info');
    setExportButtonEnabled(false);
  }

  hideSection('results-section');
  hideSection('error-section');
}

/**
 * Handle progress updates during design spec extraction.
 */
function handleExportProgress(msg: Extract<PluginToUIMessage, { type: 'export-progress' }>): void {
  showSection('progress-section');
  updateProgress(msg.progress, msg.step, msg.detail);
}

/**
 * Handle successful export from the plugin (DesignSpec received).
 * Now send the spec to the backend for HTML/CSS generation.
 */
function handleExportComplete(msg: Extract<PluginToUIMessage, { type: 'export-complete' }>): void {
  currentDesignSpec = msg.designSpec;
  const extractionTime = msg.extractionTimeMs;

  updateProgress(
    0.5,
    'Design spec extracted',
    `${(extractionTime / 1000).toFixed(1)}s - Sending to backend...`
  );

  // Send to backend
  submitToBackend(msg.designSpec);
}

/**
 * Handle export error from the plugin.
 */
function handleExportError(msg: Extract<PluginToUIMessage, { type: 'export-error' }>): void {
  isExporting = false;
  hideSection('progress-section');
  showError(msg.error, msg.stack);
  setExportButtonEnabled(true);
}

// ─── User Actions ─────────────────────────────────────────────────────────────

/**
 * Handle the Export button click.
 */
function handleExportClick(): void {
  if (isExporting) return;

  isExporting = true;
  setExportButtonEnabled(false);
  hideSection('results-section');
  hideSection('error-section');
  showSection('progress-section');
  updateProgress(0, 'Starting export...', 'Preparing design specification');

  // Send message to plugin sandbox to start extraction
  sendToPlugin({
    type: 'start-export',
    settings,
  });
}

/**
 * Handle the Cancel button click.
 */
function handleCancelClick(): void {
  // Cancel plugin extraction
  sendToPlugin({ type: 'cancel-export' });

  // Close WebSocket if open
  if (currentWebSocket) {
    currentWebSocket.close();
    currentWebSocket = null;
  }

  isExporting = false;
  hideSection('progress-section');
  setExportButtonEnabled(true);
}

// ─── Backend Communication ────────────────────────────────────────────────────

/**
 * Submit the DesignSpec to the backend API for HTML/CSS generation.
 */
async function submitToBackend(designSpec: DesignSpec): Promise<void> {
  const apiUrl = settings.backendUrl.replace(/\/+$/, '');

  try {
    // Pre-flight check: verify the backend is reachable
    updateProgress(0.52, 'Connecting to backend...', `Checking ${apiUrl}`);
    try {
      const healthResp = await fetch(`${apiUrl}/health`, { method: 'GET' });
      if (!healthResp.ok) {
        throw new Error(`Backend health check returned HTTP ${healthResp.status}`);
      }
    } catch (healthErr) {
      const msg = healthErr instanceof Error ? healthErr.message : String(healthErr);
      throw new Error(
        `Cannot reach backend at ${apiUrl}/health: ${msg}. ` +
        'Make sure the backend server is running with: python main.py'
      );
    }

    updateProgress(0.55, 'Sending to backend...', 'Uploading design specification');

    const requestBody: CreateJobRequest = {
      designSpec,
      options: {
        cssStrategy: 'class-based',
        responsive: true,
        framework: 'vanilla',
        accessibility: true,
        includeAnimations: false,
        semanticHtml: true,
        imageOptimization: 'basic',
      },
    };

    const response = await fetch(`${apiUrl}/jobs`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const errorText = await response.text();
      let errorMessage: string;
      try {
        const errorJson = JSON.parse(errorText);
        errorMessage = errorJson.detail || errorJson.message || errorJson.error || errorText;
      } catch {
        errorMessage = errorText || `HTTP ${response.status}: ${response.statusText}`;
      }
      throw new Error(`Backend error (HTTP ${response.status}): ${errorMessage}`);
    }

    const jobResponse: CreateJobResponse = await response.json();
    currentJobId = jobResponse.jobId;

    updateProgress(0.6, 'Job created', `Job ID: ${jobResponse.jobId}`);

    // Connect to WebSocket for live progress updates
    connectWebSocket(jobResponse.jobId, apiUrl);

  } catch (error) {
    isExporting = false;
    const message = error instanceof Error ? error.message : String(error);

    // Provide helpful error messages for common cases
    if (message.includes('Failed to fetch') || message.includes('NetworkError')) {
      showError(
        `Cannot connect to backend at ${apiUrl}. Make sure the backend server is running.`,
        'Tip: Start the backend with "python -m uvicorn main:app --reload" or check the Backend URL in settings.'
      );
    } else {
      showError(message);
    }

    setExportButtonEnabled(true);
  }
}

/**
 * Connect to the backend WebSocket for real-time progress updates.
 */
function connectWebSocket(jobId: string, apiUrl: string): void {
  // Convert HTTP URL to WebSocket URL
  const wsUrl = apiUrl.replace(/^http/, 'ws') + `/ws/${jobId}`;

  try {
    const ws = new WebSocket(wsUrl);
    currentWebSocket = ws;

    ws.onopen = () => {
      updateProgress(0.62, 'Connected to backend', 'Waiting for generation to start...');
    };

    ws.onmessage = (event) => {
      try {
        const msg: WebSocketMessage = JSON.parse(event.data);
        handleWebSocketMessage(msg);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    ws.onerror = (event) => {
      console.error('WebSocket error:', event);
      // Don't show error immediately - fall back to polling
      startPolling(jobId, apiUrl);
    };

    ws.onclose = (event) => {
      currentWebSocket = null;
      if (isExporting && !event.wasClean) {
        // Connection lost during export, fall back to polling
        startPolling(jobId, apiUrl);
      }
    };

  } catch (error) {
    // WebSocket not available, fall back to polling
    console.warn('WebSocket connection failed, falling back to polling:', error);
    startPolling(jobId, apiUrl);
  }
}

/**
 * Handle a WebSocket message from the backend.
 */
function handleWebSocketMessage(msg: WebSocketMessage): void {
  switch (msg.type) {
    case 'progress': {
      const progress = 0.6 + (msg.progress / 100) * 0.35; // Map 0-100 to 60%-95%
      updateProgress(progress, msg.step, msg.detail);
      break;
    }

    case 'completed': {
      isExporting = false;
      if (currentWebSocket) {
        currentWebSocket.close();
        currentWebSocket = null;
      }
      updateProgress(1.0, 'Generation complete!', 'Your HTML/CSS is ready');
      showResults(msg.result);
      break;
    }

    case 'error': {
      isExporting = false;
      if (currentWebSocket) {
        currentWebSocket.close();
        currentWebSocket = null;
      }
      showError(`Generation failed: ${msg.error}`);
      setExportButtonEnabled(true);
      break;
    }

    case 'log': {
      // Append log message to progress detail
      if (msg.level !== 'debug') {
        const progressDetail = getEl<HTMLSpanElement>('progress-detail');
        if (progressDetail) {
          progressDetail.textContent = msg.message;
        }
      }
      break;
    }

    case 'ping':
      // Keepalive, no action needed
      break;
  }
}

/**
 * Fallback: poll the backend API for job status when WebSocket is unavailable.
 */
function startPolling(jobId: string, apiUrl: string): void {
  const pollInterval = 2000; // 2 seconds
  let pollCount = 0;
  const maxPolls = 300; // 10 minutes max

  const poll = async () => {
    if (!isExporting || pollCount >= maxPolls) {
      return;
    }
    pollCount++;

    try {
      const response = await fetch(`${apiUrl}/jobs/${jobId}`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const status: JobStatusResponse = await response.json();

      // Update progress
      const progress = 0.6 + (status.progress / 100) * 0.35;
      updateProgress(progress, status.currentStep, `${status.progress}%`);

      // Check terminal states
      if (status.status === 'completed' && status.result) {
        isExporting = false;
        updateProgress(1.0, 'Generation complete!', 'Your HTML/CSS is ready');
        showResults(status.result);
        return;
      }

      if (status.status === 'failed') {
        isExporting = false;
        showError(status.error ?? 'Job failed with unknown error');
        setExportButtonEnabled(true);
        return;
      }

      if (status.status === 'cancelled') {
        isExporting = false;
        hideSection('progress-section');
        setExportButtonEnabled(true);
        return;
      }

      // Continue polling
      setTimeout(poll, pollInterval);
    } catch (error) {
      // Network error, retry
      setTimeout(poll, pollInterval * 2);
    }
  };

  setTimeout(poll, pollInterval);
}

// ─── Results Display ──────────────────────────────────────────────────────────

/**
 * Display the generation results in the UI.
 */
function showResults(result: JobResult): void {
  hideSection('progress-section');
  showSection('results-section');

  // Verification scores
  if (result.verification) {
    const v = result.verification;
    setScoreBar('score-overall', v.overallScore);
    setScoreBar('score-layout', v.layoutScore);
    setScoreBar('score-color', v.colorScore);
    setScoreBar('score-typography', v.typographyScore);
    setScoreBar('score-spacing', v.spacingScore);
  }

  // Download links
  const downloadLinks = getEl<HTMLDivElement>('download-links');
  if (downloadLinks) {
    downloadLinks.innerHTML = '';

    if (result.zipUrl) {
      downloadLinks.appendChild(createDownloadLink('Download Project (ZIP)', result.zipUrl, 'primary'));
    }
    if (result.htmlUrl) {
      downloadLinks.appendChild(createDownloadLink('HTML File', result.htmlUrl, 'secondary'));
    }
    if (result.cssUrl) {
      downloadLinks.appendChild(createDownloadLink('CSS File', result.cssUrl, 'secondary'));
    }
    if (result.previewUrl) {
      downloadLinks.appendChild(createDownloadLink('Live Preview', result.previewUrl, 'link'));
    }
  }

  // Differences list
  if (result.verification?.differences && result.verification.differences.length > 0) {
    const diffList = getEl<HTMLDivElement>('differences-list');
    if (diffList) {
      diffList.innerHTML = '<h4>Differences Detected</h4>';
      for (const diff of result.verification.differences.slice(0, 10)) {
        const item = document.createElement('div');
        item.className = `diff-item diff-${diff.severity}`;
        item.innerHTML = `<span class="diff-name">${escapeHtml(diff.nodeName)}</span>
          <span class="diff-issue">${escapeHtml(diff.issue)}</span>`;
        diffList.appendChild(item);
      }
      diffList.style.display = 'block';
    }
  }

  setExportButtonEnabled(false);
}

// ─── UI Helpers ───────────────────────────────────────────────────────────────

/**
 * Send a typed message to the plugin sandbox.
 */
function sendToPlugin(message: UIToPluginMessage): void {
  parent.postMessage({ pluginMessage: message }, '*');
}

/**
 * Update the progress display.
 */
function updateProgress(fraction: number, step: string, detail?: string): void {
  const progressBar = getEl<HTMLDivElement>('progress-bar-fill');
  const progressStep = getEl<HTMLSpanElement>('progress-step');
  const progressDetail = getEl<HTMLSpanElement>('progress-detail');
  const progressPercent = getEl<HTMLSpanElement>('progress-percent');

  if (progressBar) {
    progressBar.style.width = `${Math.round(fraction * 100)}%`;
  }
  if (progressStep) {
    progressStep.textContent = step;
  }
  if (progressDetail && detail) {
    progressDetail.textContent = detail;
  }
  if (progressPercent) {
    progressPercent.textContent = `${Math.round(fraction * 100)}%`;
  }
}

/**
 * Show an error message.
 */
function showError(message: string, details?: string): void {
  hideSection('progress-section');
  showSection('error-section');

  const errorMessage = getEl<HTMLParagraphElement>('error-message');
  if (errorMessage) {
    errorMessage.textContent = message;
  }

  const errorDetails = getEl<HTMLParagraphElement>('error-details');
  if (errorDetails) {
    if (details) {
      errorDetails.textContent = details;
      errorDetails.style.display = 'block';
    } else {
      errorDetails.style.display = 'none';
    }
  }
}

/**
 * Show a UI section by ID.
 */
function showSection(id: string): void {
  const el = document.getElementById(id);
  if (el) el.style.display = 'block';
}

/**
 * Hide a UI section by ID.
 */
function hideSection(id: string): void {
  const el = document.getElementById(id);
  if (el) el.style.display = 'none';
}

/**
 * Enable or disable the export button.
 */
function setExportButtonEnabled(enabled: boolean): void {
  const btn = getEl<HTMLButtonElement>('export-btn');
  if (btn) {
    btn.disabled = !enabled;
    btn.classList.toggle('disabled', !enabled);
  }
}

/**
 * Set a score bar's width and label.
 */
function setScoreBar(id: string, score: number): void {
  const container = document.getElementById(id);
  if (!container) return;

  const fill = container.querySelector('.score-fill') as HTMLDivElement;
  const label = container.querySelector('.score-value') as HTMLSpanElement;

  if (fill) {
    fill.style.width = `${score}%`;
    // Color based on score
    if (score >= 90) fill.style.backgroundColor = '#18a957';
    else if (score >= 70) fill.style.backgroundColor = '#f5a623';
    else fill.style.backgroundColor = '#e03e3e';
  }
  if (label) {
    label.textContent = `${Math.round(score)}`;
  }
}

/**
 * Create a download link element.
 */
function createDownloadLink(text: string, url: string, style: 'primary' | 'secondary' | 'link'): HTMLElement {
  const a = document.createElement('a');
  a.href = url;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  a.textContent = text;
  a.className = `download-link download-${style}`;
  return a;
}

/**
 * Escape HTML special characters for safe insertion.
 */
function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ─── Settings Persistence ─────────────────────────────────────────────────────

const SETTINGS_KEY = 'figma-to-html-settings';

/**
 * Save current settings to localStorage.
 */
function saveSettings(): void {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
  } catch {
    // localStorage may not be available in some contexts
  }
}

/**
 * Load saved settings from localStorage.
 */
function loadSavedSettings(): void {
  try {
    const saved = localStorage.getItem(SETTINGS_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      settings = { ...DEFAULT_EXPORT_SETTINGS, ...parsed };

      // Update UI inputs
      const backendUrlInput = getEl<HTMLInputElement>('backend-url');
      if (backendUrlInput) backendUrlInput.value = settings.backendUrl;

      const includeInvisibleCheck = getEl<HTMLInputElement>('include-invisible');
      if (includeInvisibleCheck) includeInvisibleCheck.checked = settings.includeInvisible;

      const exportAssetsCheck = getEl<HTMLInputElement>('export-assets');
      if (exportAssetsCheck) exportAssetsCheck.checked = settings.exportAssets;

      const assetFormatSelect = getEl<HTMLSelectElement>('asset-format');
      if (assetFormatSelect) assetFormatSelect.value = settings.assetFormat;

      const assetScaleSelect = getEl<HTMLSelectElement>('asset-scale');
      if (assetScaleSelect) assetScaleSelect.value = String(settings.assetScale);
    }
  } catch {
    // Ignore localStorage errors
  }
}
