"use client";

import { useCallback, useEffect, useState } from "react";
import { useEditorStore } from "@/store/useEditorStore";
import { updateTextContent } from "@/lib/codeMutator";
import SpacingPanel from "./SpacingPanel";
import LinkEditor from "./LinkEditor";
import type { EditOperation } from "@/types/editor";

const TABS = [
  { key: "text" as const, label: "Text", icon: "T" },
  { key: "spacing" as const, label: "Spacing", icon: "\u2194" },
  { key: "link" as const, label: "Link", icon: "\u{1F517}" },
];

export default function ElementEditor() {
  const selectedNode = useEditorStore((s) => s.selectedNode);
  const isEditing = useEditorStore((s) => s.isEditing);
  const htmlContent = useEditorStore((s) => s.htmlContent);
  const cssContent = useEditorStore((s) => s.cssContent);
  const clearSelection = useEditorStore((s) => s.clearSelection);
  const applyEdit = useEditorStore((s) => s.applyEdit);
  const setShowAIFixModal = useEditorStore((s) => s.setShowAIFixModal);
  const activeTab = useEditorStore((s) => s.activeTab);
  const setActiveTab = useEditorStore((s) => s.setActiveTab);

  const [editText, setEditText] = useState("");
  const [saveFlash, setSaveFlash] = useState(false);

  useEffect(() => {
    if (selectedNode) {
      setEditText(selectedNode.textContent);
    }
  }, [selectedNode]);

  const handleSaveText = useCallback(() => {
    if (!selectedNode || editText === selectedNode.textContent) return;

    const op: EditOperation = {
      nodeId: selectedNode.nodeId,
      field: "text",
      oldValue: selectedNode.textContent,
      newValue: editText,
      prevHtml: htmlContent,
      prevCss: cssContent,
      timestamp: Date.now(),
    };

    const newHtml = updateTextContent(htmlContent, selectedNode.nodeId, editText);
    applyEdit(op, newHtml);

    setSaveFlash(true);
    setTimeout(() => setSaveFlash(false), 2000);
  }, [selectedNode, editText, htmlContent, cssContent, applyEdit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") {
        clearSelection();
      } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        handleSaveText();
      }
    },
    [clearSelection, handleSaveText]
  );

  if (!isEditing || !selectedNode) return null;

  return (
    <div
      className="fixed right-4 top-16 z-50 w-80 bg-gray-800 border border-gray-600 rounded-lg shadow-2xl transition-all duration-200 animate-in fade-in slide-in-from-right-2"
      onKeyDown={handleKeyDown}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-700">
        <div className="flex-1 min-w-0">
          <p className="text-xs text-gray-400 truncate">
            <span className="text-blue-400 font-mono">&lt;{selectedNode.tagName}&gt;</span>
            <span className="text-gray-600 ml-1.5">{selectedNode.nodeId}</span>
          </p>
        </div>
        <div className="flex items-center gap-1 ml-2">
          <button
            onClick={() => setShowAIFixModal(true)}
            className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-purple-300 bg-purple-600/20 rounded hover:bg-purple-600/30 transition-colors"
            title="AI Fix This Area"
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            AI Fix
          </button>
          <button
            onClick={clearSelection}
            className="text-gray-400 hover:text-white p-1 rounded hover:bg-gray-700 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-700">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 px-3 py-2 text-xs font-medium transition-colors ${
              activeTab === tab.key
                ? "text-blue-400 border-b-2 border-blue-400 bg-gray-750"
                : "text-gray-400 hover:text-gray-200 hover:bg-gray-750"
            }`}
          >
            <span className="mr-1">{tab.icon}</span>
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="p-4 max-h-80 overflow-y-auto">
        {activeTab === "text" && (
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-400 mb-1">
                Text Content
              </label>
              <textarea
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                rows={3}
                placeholder="Empty -- type to add text"
                className="w-full px-3 py-2 text-sm bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500 resize-y"
                autoFocus
              />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-gray-500">
                {saveFlash
                  ? ""
                  : editText === selectedNode.textContent
                    ? "Edit text above to enable save"
                    : "Ctrl+Enter to save"}
              </span>
              {saveFlash ? (
                <span className="px-3 py-1.5 text-xs font-medium text-green-400">
                  Applied
                </span>
              ) : (
                <button
                  onClick={handleSaveText}
                  disabled={editText === selectedNode.textContent}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    editText === selectedNode.textContent
                      ? "bg-gray-700 text-gray-500 cursor-not-allowed"
                      : "bg-blue-600 text-white hover:bg-blue-500"
                  }`}
                >
                  Apply
                </button>
              )}
            </div>
          </div>
        )}

        {activeTab === "spacing" && <SpacingPanel />}

        {activeTab === "link" && <LinkEditor />}
      </div>
    </div>
  );
}
