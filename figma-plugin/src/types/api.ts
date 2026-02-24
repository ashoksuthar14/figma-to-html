/**
 * Backend API types for communication between the Figma plugin UI
 * and the HTML/CSS generation backend service.
 */

import type { DesignSpec } from './designSpec';

// ─── Job Management ───────────────────────────────────────────────────────────

/** Request body for POST /jobs */
export interface CreateJobRequest {
  /** The design specification extracted from Figma */
  designSpec: DesignSpec;
  /** Generation options */
  options?: GenerationOptions;
}

/** Response body for POST /jobs */
export interface CreateJobResponse {
  /** Unique job identifier */
  jobId: string;
  /** Job status */
  status: JobStatus;
  /** Timestamp of job creation */
  createdAt: string;
  /** WebSocket URL for progress updates */
  wsUrl: string;
  /** Estimated time to completion in seconds */
  estimatedTimeSeconds?: number;
}

/** Possible job statuses */
export type JobStatus =
  | 'queued'
  | 'processing'
  | 'generating_html'
  | 'generating_css'
  | 'optimizing'
  | 'verifying'
  | 'completed'
  | 'failed'
  | 'cancelled';

/** Response body for GET /jobs/:jobId */
export interface JobStatusResponse {
  jobId: string;
  status: JobStatus;
  /** Progress from 0 to 100 */
  progress: number;
  /** Current processing step description */
  currentStep: string;
  /** When the job was created */
  createdAt: string;
  /** When the job was last updated */
  updatedAt: string;
  /** When the job completed (if finished) */
  completedAt?: string;
  /** Error message (if failed) */
  error?: string;
  /** Result details (if completed) */
  result?: JobResult;
}

/** Job result containing generated output and quality metrics */
export interface JobResult {
  /** URL to download the generated HTML file */
  htmlUrl: string;
  /** URL to download the generated CSS file */
  cssUrl: string;
  /** URL to download all assets as a zip */
  assetsUrl?: string;
  /** URL to download the complete project as a zip */
  zipUrl: string;
  /** URL to a live preview of the generated page */
  previewUrl?: string;
  /** Verification scores (0-100) */
  verification: VerificationResult;
}

/** Visual verification scores comparing original design to generated HTML */
export interface VerificationResult {
  /** Overall similarity score (0-100) */
  overallScore: number;
  /** Layout accuracy score (0-100) */
  layoutScore: number;
  /** Color accuracy score (0-100) */
  colorScore: number;
  /** Typography accuracy score (0-100) */
  typographyScore: number;
  /** Spacing accuracy score (0-100) */
  spacingScore: number;
  /** URL to a side-by-side comparison image */
  comparisonImageUrl?: string;
  /** Per-element differences detected */
  differences?: Array<{
    nodeId: string;
    nodeName: string;
    issue: string;
    severity: 'low' | 'medium' | 'high';
  }>;
}

// ─── WebSocket Messages ───────────────────────────────────────────────────────

/** Base WebSocket message */
export interface WebSocketMessageBase {
  jobId: string;
  timestamp: string;
}

/** Progress update message */
export interface WSProgressMessage extends WebSocketMessageBase {
  type: 'progress';
  status: JobStatus;
  progress: number;
  step: string;
  detail?: string;
}

/** Job completed message */
export interface WSCompletedMessage extends WebSocketMessageBase {
  type: 'completed';
  result: JobResult;
}

/** Job failed message */
export interface WSErrorMessage extends WebSocketMessageBase {
  type: 'error';
  error: string;
  code?: string;
}

/** Log message from the generation process */
export interface WSLogMessage extends WebSocketMessageBase {
  type: 'log';
  level: 'info' | 'warn' | 'error' | 'debug';
  message: string;
}

/** Heartbeat / keepalive */
export interface WSPingMessage extends WebSocketMessageBase {
  type: 'ping';
}

export type WebSocketMessage =
  | WSProgressMessage
  | WSCompletedMessage
  | WSErrorMessage
  | WSLogMessage
  | WSPingMessage;

// ─── Generation Options ───────────────────────────────────────────────────────

export interface GenerationOptions {
  /** CSS methodology to use */
  cssStrategy: 'inline' | 'class-based' | 'css-modules' | 'tailwind';
  /** Whether to make the output responsive */
  responsive: boolean;
  /** Target frameworks/libraries */
  framework: 'vanilla' | 'react' | 'vue' | 'svelte';
  /** Whether to optimize for accessibility */
  accessibility: boolean;
  /** Whether to include animations/transitions */
  includeAnimations: boolean;
  /** Whether to use semantic HTML elements */
  semanticHtml: boolean;
  /** Image optimization level */
  imageOptimization: 'none' | 'basic' | 'aggressive';
}

/** Default generation options */
export const DEFAULT_GENERATION_OPTIONS: GenerationOptions = {
  cssStrategy: 'class-based',
  responsive: true,
  framework: 'vanilla',
  accessibility: true,
  includeAnimations: false,
  semanticHtml: true,
  imageOptimization: 'basic',
};

// ─── API Error ────────────────────────────────────────────────────────────────

/** Standard API error response */
export interface ApiError {
  status: number;
  code: string;
  message: string;
  details?: Record<string, unknown>;
}
