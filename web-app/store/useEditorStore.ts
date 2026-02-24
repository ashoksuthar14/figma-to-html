import { create } from "zustand";
import type {
  EditorState,
  EditOperation,
  FixHistoryEntry,
  JobStatus,
  LayoutInfo,
  NodeRect,
  SelectedNode,
} from "@/types/editor";

const initialState = {
  jobId: null as string | null,
  jobStatus: null as JobStatus | null,
  progress: 0,
  currentStep: "",

  htmlContent: "",
  cssContent: "",
  originalHtml: "",
  originalCss: "",

  viewportWidth: 1440,
  viewportHeight: 900,
  scale: 1,

  selectedNodeId: null as string | null,
  selectedNode: null as SelectedNode | null,
  isEditing: false,

  editHistory: [] as EditOperation[],
  userModified: false,
  isDirty: false,
  isSaving: false,
  isLoading: false,

  spacingDraft: null as Record<string, string> | null,
  fixHistory: [] as FixHistoryEntry[],
  isFixing: false,
  showAIFixModal: false,
  activeTab: "text" as "text" | "spacing" | "link",

  isPositionMode: false,
  isDragging: false,
  dragStart: null as { x: number; y: number } | null,
  dragCurrent: null as { x: number; y: number } | null,
  originalRect: null as NodeRect | null,
  parentRect: null as NodeRect | null,
  layoutInfo: null as LayoutInfo | null,
  iframeContainerRect: null as NodeRect | null,
};

export const useEditorStore = create<EditorState>((set, get) => ({
  ...initialState,

  loadJob: (jobId, html, css, status) =>
    set({
      jobId,
      htmlContent: html,
      cssContent: css,
      originalHtml: html,
      originalCss: css,
      jobStatus: status,
      isDirty: false,
      userModified: false,
      editHistory: [],
      selectedNodeId: null,
      selectedNode: null,
      isEditing: false,
      spacingDraft: null,
      fixHistory: [],
      isFixing: false,
      showAIFixModal: false,
      activeTab: "text",
      isLoading: false,
    }),

  setHtml: (html) =>
    set({ htmlContent: html, isDirty: true }),

  setCss: (css) =>
    set({ cssContent: css, isDirty: true }),

  setViewport: (width, height) =>
    set({ viewportWidth: width, viewportHeight: height }),

  setScale: (scale) =>
    set({ scale }),

  selectNode: (node) =>
    set({
      selectedNodeId: node.nodeId,
      selectedNode: node,
      isEditing: true,
      activeTab: "text",
    }),

  clearSelection: () =>
    set({
      selectedNodeId: null,
      selectedNode: null,
      isEditing: false,
      spacingDraft: null,
      showAIFixModal: false,
      isPositionMode: false,
      isDragging: false,
      dragStart: null,
      dragCurrent: null,
      originalRect: null,
      parentRect: null,
      layoutInfo: null,
    }),

  applyEdit: (op, newHtml, newCss?) =>
    set((state) => ({
      htmlContent: newHtml,
      cssContent: newCss ?? state.cssContent,
      editHistory: [...state.editHistory, op],
      isDirty: true,
      userModified: true,
    })),

  undo: () => {
    const { editHistory } = get();
    if (editHistory.length === 0) return;

    const lastOp = editHistory[editHistory.length - 1];
    const newHistory = editHistory.slice(0, -1);
    set({
      editHistory: newHistory,
      htmlContent: lastOp.prevHtml,
      cssContent: lastOp.prevCss,
      isDirty: newHistory.length > 0,
      userModified: newHistory.length > 0,
    });
  },

  markSaved: () =>
    set((state) => ({
      isDirty: false,
      originalHtml: state.htmlContent,
      originalCss: state.cssContent,
    })),

  setProgress: (progress, step, status) =>
    set((state) => ({
      progress,
      currentStep: step,
      jobStatus: status ?? state.jobStatus,
    })),

  setSaving: (saving) =>
    set({ isSaving: saving }),

  setLoading: (loading) =>
    set({ isLoading: loading }),

  setSpacingDraft: (draft) =>
    set({ spacingDraft: draft }),

  setIsFixing: (fixing) =>
    set({ isFixing: fixing }),

  setShowAIFixModal: (show) =>
    set({ showAIFixModal: show }),

  setActiveTab: (tab) =>
    set((state) => ({
      activeTab: tab,
      ...(tab !== "spacing" && state.isPositionMode
        ? {
            isPositionMode: false,
            isDragging: false,
            dragStart: null,
            dragCurrent: null,
            originalRect: null,
            parentRect: null,
            layoutInfo: null,
          }
        : {}),
    })),

  addFixHistory: (entry) =>
    set((state) => ({
      fixHistory: [...state.fixHistory, entry],
    })),

  enterPositionMode: () =>
    set((state) => ({
      isPositionMode: true,
      originalRect: state.selectedNode?.rect ?? null,
      isDragging: false,
      dragStart: null,
      dragCurrent: null,
    })),

  exitPositionMode: () =>
    set({
      isPositionMode: false,
      isDragging: false,
      dragStart: null,
      dragCurrent: null,
      originalRect: null,
      parentRect: null,
      layoutInfo: null,
    }),

  startDrag: (x, y) =>
    set({
      isDragging: true,
      dragStart: { x, y },
      dragCurrent: { x, y },
    }),

  updateDrag: (x, y) =>
    set({ dragCurrent: { x, y } }),

  endDrag: () =>
    set({ isDragging: false }),

  setLayoutInfo: (info, rect, parentRect) =>
    set({
      layoutInfo: info,
      originalRect: rect,
      parentRect: parentRect,
    }),

  setIframeContainerRect: (rect) =>
    set({ iframeContainerRect: rect }),

  reset: () => set(initialState),
}));
