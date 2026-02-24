"use client";

import { useCallback, useEffect, useState } from "react";
import { useEditorStore } from "@/store/useEditorStore";
import { wrapWithLink, removeLink } from "@/lib/codeMutator";
import type { EditOperation } from "@/types/editor";

const SAFE_PROTOCOL_RE = /^(https?:|mailto:|tel:|\/|#)/i;

function isValidUrl(url: string): boolean {
  if (!url.trim()) return false;
  if (url.toLowerCase().startsWith("javascript:")) return false;
  return SAFE_PROTOCOL_RE.test(url);
}

export default function LinkEditor() {
  const selectedNode = useEditorStore((s) => s.selectedNode);
  const htmlContent = useEditorStore((s) => s.htmlContent);
  const cssContent = useEditorStore((s) => s.cssContent);
  const applyEdit = useEditorStore((s) => s.applyEdit);

  const [url, setUrl] = useState("");
  const [newTab, setNewTab] = useState(true);
  const [error, setError] = useState("");

  const hasExistingLink = !!(selectedNode?.href);

  useEffect(() => {
    if (selectedNode?.href) {
      setUrl(selectedNode.href);
      setNewTab(selectedNode.target === "_blank");
    } else {
      setUrl("");
      setNewTab(true);
    }
    setError("");
  }, [selectedNode]);

  const handleApply = useCallback(() => {
    if (!selectedNode) return;
    if (!isValidUrl(url)) {
      setError("Enter a valid URL (http, https, mailto, or tel)");
      return;
    }
    setError("");

    const newHtml = wrapWithLink(htmlContent, selectedNode.nodeId, url, newTab);
    const op: EditOperation = {
      nodeId: selectedNode.nodeId,
      field: "link",
      oldValue: selectedNode.href ?? "",
      newValue: url,
      prevHtml: htmlContent,
      prevCss: cssContent,
      timestamp: Date.now(),
    };
    applyEdit(op, newHtml);
  }, [selectedNode, url, newTab, htmlContent, cssContent, applyEdit]);

  const handleRemove = useCallback(() => {
    if (!selectedNode) return;
    const newHtml = removeLink(htmlContent, selectedNode.nodeId);
    const op: EditOperation = {
      nodeId: selectedNode.nodeId,
      field: "link",
      oldValue: selectedNode.href ?? "",
      newValue: "",
      prevHtml: htmlContent,
      prevCss: cssContent,
      timestamp: Date.now(),
    };
    applyEdit(op, newHtml);
  }, [selectedNode, htmlContent, cssContent, applyEdit]);

  if (!selectedNode) return null;

  return (
    <div className="space-y-3">
      <div>
        <label className="block text-xs text-gray-400 mb-1">URL</label>
        <input
          type="text"
          value={url}
          onChange={(e) => {
            setUrl(e.target.value);
            setError("");
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleApply();
          }}
          placeholder="https://example.com"
          className="w-full px-3 py-1.5 text-sm bg-gray-900 border border-gray-700 rounded-md text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
        />
        {error && (
          <p className="text-[10px] text-red-400 mt-1">{error}</p>
        )}
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={newTab}
          onChange={(e) => setNewTab(e.target.checked)}
          className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-900 text-blue-500 focus:ring-blue-500 focus:ring-offset-0"
        />
        <span className="text-xs text-gray-300">Open in new tab</span>
      </label>

      <div className="flex gap-2 pt-1">
        <button
          onClick={handleApply}
          disabled={!url.trim()}
          className="flex-1 px-3 py-1.5 text-xs font-medium text-white bg-blue-600 rounded-md hover:bg-blue-500 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {hasExistingLink ? "Update Link" : "Add Link"}
        </button>
        {hasExistingLink && (
          <button
            onClick={handleRemove}
            className="px-3 py-1.5 text-xs text-red-400 bg-gray-800 rounded-md hover:bg-gray-700 transition-colors"
          >
            Remove
          </button>
        )}
      </div>
    </div>
  );
}
