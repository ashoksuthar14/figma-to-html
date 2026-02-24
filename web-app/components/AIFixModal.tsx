"use client";

import { useCallback, useState } from "react";
import { useEditorStore } from "@/store/useEditorStore";
import { microFix } from "@/lib/api";
import type { EditOperation } from "@/types/editor";

const PRESET_CHIPS = [
  "Fix text overlap",
  "Fix text cutoff",
  "Fix spacing issue",
  "Fix overflow hidden",
  "Fix alignment",
];

export default function AIFixModal() {
  const selectedNode = useEditorStore((s) => s.selectedNode);
  const jobId = useEditorStore((s) => s.jobId);
  const htmlContent = useEditorStore((s) => s.htmlContent);
  const cssContent = useEditorStore((s) => s.cssContent);
  const isFixing = useEditorStore((s) => s.isFixing);
  const showAIFixModal = useEditorStore((s) => s.showAIFixModal);
  const setShowAIFixModal = useEditorStore((s) => s.setShowAIFixModal);
  const setIsFixing = useEditorStore((s) => s.setIsFixing);
  const applyEdit = useEditorStore((s) => s.applyEdit);
  const addFixHistory = useEditorStore((s) => s.addFixHistory);

  const [prompt, setPrompt] = useState("");
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleClose = useCallback(() => {
    setShowAIFixModal(false);
    setPrompt("");
    setResultMsg(null);
    setError(null);
  }, [setShowAIFixModal]);

  const handleFix = useCallback(async () => {
    if (!selectedNode || !jobId || !prompt.trim()) return;

    setIsFixing(true);
    setError(null);
    setResultMsg(null);

    try {
      const result = await microFix(
        jobId,
        selectedNode.nodeId,
        prompt.trim(),
        htmlContent,
        cssContent
      );

      if (result.changes_made) {
        const op: EditOperation = {
          nodeId: selectedNode.nodeId,
          field: "ai-fix",
          oldValue: prompt.trim(),
          newValue: result.description,
          prevHtml: htmlContent,
          prevCss: cssContent,
          timestamp: Date.now(),
        };
        applyEdit(op, result.html, result.css);
        addFixHistory({
          nodeId: selectedNode.nodeId,
          prompt: prompt.trim(),
          timestamp: Date.now(),
          description: result.description,
        });
        setResultMsg(result.description || "Fix applied successfully.");
      } else {
        setResultMsg("No changes were needed for this area.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Fix failed. Please try again.");
    } finally {
      setIsFixing(false);
    }
  }, [selectedNode, jobId, prompt, htmlContent, cssContent, applyEdit, addFixHistory, setIsFixing]);

  if (!showAIFixModal || !selectedNode) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isFixing) handleClose();
      }}
    >
      <div className="bg-gray-800 border border-gray-600 rounded-lg shadow-2xl w-full max-w-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 rounded-full bg-purple-600/20 flex items-center justify-center">
              <svg className="w-3.5 h-3.5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-white">AI Fix This Area</h3>
              <p className="text-[10px] text-gray-400">
                <span className="text-blue-400">&lt;{selectedNode.tagName}&gt;</span>
                {" "}node: {selectedNode.nodeId}
              </p>
            </div>
          </div>
          <button
            onClick={handleClose}
            disabled={isFixing}
            className="text-gray-400 hover:text-white p-1 disabled:opacity-40"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-3">
          <div className="flex flex-wrap gap-1.5">
            {PRESET_CHIPS.map((chip) => (
              <button
                key={chip}
                onClick={() => setPrompt(chip)}
                disabled={isFixing}
                className="px-2.5 py-1 text-[11px] bg-gray-700 text-gray-300 rounded-full hover:bg-gray-600 hover:text-white transition-colors disabled:opacity-40"
              >
                {chip}
              </button>
            ))}
          </div>

          <div>
            <label className="block text-xs text-gray-400 mb-1">
              Describe the issue
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={3}
              disabled={isFixing}
              placeholder="e.g., The text is overlapping with the section below..."
              className="w-full px-3 py-2 text-sm bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-purple-500 focus:border-purple-500 resize-y disabled:opacity-60"
              autoFocus
            />
          </div>

          {resultMsg && (
            <div className="px-3 py-2 bg-green-900/30 border border-green-700/50 rounded-md">
              <p className="text-xs text-green-300">{resultMsg}</p>
            </div>
          )}

          {error && (
            <div className="px-3 py-2 bg-red-900/30 border border-red-700/50 rounded-md">
              <p className="text-xs text-red-300">{error}</p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-700">
          <span className="text-[10px] text-gray-500">
            Only the selected area will be modified
          </span>
          <div className="flex gap-2">
            <button
              onClick={handleClose}
              disabled={isFixing}
              className="px-3 py-1.5 text-xs text-gray-300 bg-gray-700 rounded-md hover:bg-gray-600 transition-colors disabled:opacity-40"
            >
              {resultMsg ? "Done" : "Cancel"}
            </button>
            {!resultMsg && (
              <button
                onClick={handleFix}
                disabled={isFixing || !prompt.trim()}
                className="px-4 py-1.5 text-xs font-medium text-white bg-purple-600 rounded-md hover:bg-purple-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
              >
                {isFixing ? (
                  <>
                    <div className="w-3 h-3 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Fixing...
                  </>
                ) : (
                  "Apply Fix"
                )}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
