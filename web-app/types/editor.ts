export type JobStatus = "queued" | "processing" | "verifying" | "completed" | "failed";

export interface JobResult {
  htmlUrl: string;
  cssUrl: string;
  zipUrl: string;
  previewUrl: string | null;
  verification: VerificationResult | null;
}

export interface VerificationResult {
  overallScore: number;
  layoutScore: number;
  colorScore: number;
  typographyScore: number;
  spacingScore: number;
  comparisonImageUrl: string | null;
  differences: VerificationDifference[];
}

export interface VerificationDifference {
  nodeId: string;
  nodeName: string;
  issue: string;
  severity: string;
}

export interface Job {
  jobId: string;
  status: JobStatus;
  frameName?: string;
  progress: number;
  currentStep: string;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  error: string | null;
  result: JobResult | null;
}

export interface ViewportPreset {
  name: string;
  width: number;
  height: number;
  icon: string;
}

export const VIEWPORT_PRESETS: ViewportPreset[] = [
  { name: "Desktop", width: 1440, height: 900, icon: "🖥" },
  { name: "Tablet", width: 768, height: 1024, icon: "📱" },
  { name: "Mobile", width: 375, height: 812, icon: "📲" },
];

export interface NodeRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ComputedSpacing {
  marginTop: string;
  marginRight: string;
  marginBottom: string;
  marginLeft: string;
  paddingTop: string;
  paddingRight: string;
  paddingBottom: string;
  paddingLeft: string;
  fontSize: string;
  lineHeight: string;
  letterSpacing: string;
  gap: string;
  parentGap: string;
  parentDisplay: string;
  parentFlexDirection: string;
}

export interface SelectedNode {
  nodeId: string;
  tagName: string;
  textContent: string;
  rect: NodeRect;
  className?: string;
  computedStyles?: ComputedSpacing;
  href?: string;
  target?: string;
}

export interface FigmaTextSegment {
  characters: string;
  fontSize: number;
  lineHeight: number | null;
  lineHeightUnit: string;
  letterSpacing: number;
  fontFamily: string;
  fontWeight: number;
}

export interface FigmaTextInfo {
  fontSize: number;
  lineHeight: number | null;
  lineHeightUnit: string;
  letterSpacing: number;
  letterSpacingUnit: string;
  paragraphSpacing: number;
  textAlignHorizontal: string;
  segments: FigmaTextSegment[];
}

export interface FigmaLayoutInfo {
  mode: string;
  gap: number;
  padding: { top: number; right: number; bottom: number; left: number };
  direction: string;
  primaryAxisAlign?: string;
  counterAxisAlign?: string;
}

export interface FigmaNodeProperties {
  text: FigmaTextInfo | null;
  layout: FigmaLayoutInfo;
  parentLayout: FigmaLayoutInfo | null;
  name: string;
  type: string;
}

export interface EditOperation {
  nodeId: string;
  field: "text" | "fontSize" | "padding" | "margin" | "css" | "link" | "ai-fix" | "position";
  oldValue: string;
  newValue: string;
  prevHtml: string;
  prevCss: string;
  timestamp: number;
}

export interface LayoutInfo {
  position: string;
  display: string;
  parentDisplay: string;
  parentFlexDirection: string;
  existingTransform: string;
  hasExistingLeft: boolean;
  hasExistingTop: boolean;
  computedLeft: number;
  computedTop: number;
}

export interface LayoutInfoResponseMessage {
  type: "layout-info-response";
  nodeId: string;
  rect: NodeRect;
  parentRect: NodeRect | null;
  layoutInfo: LayoutInfo;
}

export interface CssPatch {
  property: string;
  value: string;
}

export interface FixHistoryEntry {
  nodeId: string;
  prompt: string;
  timestamp: number;
  description: string;
}

export interface MicroFixResponse {
  html: string;
  css: string;
  changes_made: boolean;
  description: string;
}

export type WSMessageType = "progress" | "completed" | "error" | "log" | "ping";

export interface WSProgressMessage {
  type: "progress";
  jobId: string;
  timestamp: string;
  status: string;
  progress: number;
  step: string;
  detail: string | null;
}

export interface WSCompletedMessage {
  type: "completed";
  jobId: string;
  timestamp: string;
  result: JobResult;
}

export interface WSErrorMessage {
  type: "error";
  jobId: string;
  timestamp: string;
  error: string;
  code: string | null;
}

export interface WSLogMessage {
  type: "log";
  jobId: string;
  timestamp: string;
  level: string;
  message: string;
}

export interface WSPingMessage {
  type: "ping";
  jobId: string;
  timestamp: string;
}

export type WSMessage =
  | WSProgressMessage
  | WSCompletedMessage
  | WSErrorMessage
  | WSLogMessage
  | WSPingMessage;

export interface IframeNodeClickMessage {
  type: "node-click";
  nodeId: string;
  tagName: string;
  textContent: string;
  rect: NodeRect;
  className?: string;
  computedStyles?: ComputedSpacing;
  href?: string;
  target?: string;
  ctrlKey?: boolean;
  shiftKey?: boolean;
}

export interface EditorState {
  jobId: string | null;
  jobStatus: JobStatus | null;
  progress: number;
  currentStep: string;

  htmlContent: string;
  cssContent: string;
  originalHtml: string;
  originalCss: string;

  viewportWidth: number;
  viewportHeight: number;
  scale: number;

  selectedNodeId: string | null;
  selectedNode: SelectedNode | null;
  selectedNodes: SelectedNode[];
  isEditing: boolean;

  editHistory: EditOperation[];
  userModified: boolean;
  isDirty: boolean;
  isSaving: boolean;
  isLoading: boolean;

  spacingDraft: Record<string, string> | null;
  fixHistory: FixHistoryEntry[];
  isFixing: boolean;
  showAIFixModal: boolean;
  activeTab: "text" | "spacing" | "link" | "typography";

  isPositionMode: boolean;
  isDragging: boolean;
  dragStart: { x: number; y: number } | null;
  dragCurrent: { x: number; y: number } | null;
  originalRect: NodeRect | null;
  parentRect: NodeRect | null;
  layoutInfo: LayoutInfo | null;
  iframeContainerRect: NodeRect | null;

  loadJob: (jobId: string, html: string, css: string, status: JobStatus) => void;
  setHtml: (html: string) => void;
  setCss: (css: string) => void;
  setViewport: (width: number, height: number) => void;
  setScale: (scale: number) => void;
  selectNode: (node: SelectedNode) => void;
  toggleNodeSelection: (node: SelectedNode) => void;
  clearSelection: () => void;
  applyEdit: (op: EditOperation, newHtml: string, newCss?: string) => void;
  undo: () => void;
  markSaved: () => void;
  setProgress: (progress: number, step: string, status?: JobStatus) => void;
  setSaving: (saving: boolean) => void;
  setLoading: (loading: boolean) => void;
  setSpacingDraft: (draft: Record<string, string> | null) => void;
  setIsFixing: (fixing: boolean) => void;
  setShowAIFixModal: (show: boolean) => void;
  setActiveTab: (tab: "text" | "spacing" | "link" | "typography") => void;
  addFixHistory: (entry: FixHistoryEntry) => void;
  enterPositionMode: () => void;
  exitPositionMode: () => void;
  startDrag: (x: number, y: number) => void;
  updateDrag: (x: number, y: number) => void;
  endDrag: () => void;
  setLayoutInfo: (info: LayoutInfo, rect: NodeRect, parentRect: NodeRect | null) => void;
  setIframeContainerRect: (rect: NodeRect) => void;
  reset: () => void;
}
