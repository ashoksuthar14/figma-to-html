"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useEditorStore } from "@/store/useEditorStore";
import { fetchDesignSpecNodes } from "@/lib/api";
import { updateTypographyProperty, updateParentGap } from "@/lib/codeMutator";
import type {
  EditOperation,
  FigmaNodeProperties,
  SelectedNode,
} from "@/types/editor";

function parsePx(val: string | undefined): number {
  if (!val || val === "normal" || val === "none") return 0;
  const n = parseFloat(val);
  return isNaN(n) ? 0 : Math.round(n * 100) / 100;
}

function formatPx(val: number): string {
  return `${Math.round(val)}px`;
}

interface PropertyRowProps {
  label: string;
  currentValue: number;
  figmaValue: number | null;
  unit?: string;
  onApply: (value: number) => void;
}

function PropertyRow({
  label,
  currentValue,
  figmaValue,
  unit = "px",
  onApply,
}: PropertyRowProps) {
  const [manualValue, setManualValue] = useState<string>("");
  const hasMismatch =
    figmaValue !== null && Math.abs(currentValue - figmaValue) >= 0.5;

  const handleFix = useCallback(() => {
    if (manualValue !== "") {
      const parsed = parseFloat(manualValue);
      if (!isNaN(parsed)) onApply(parsed);
    } else if (figmaValue !== null) {
      onApply(figmaValue);
    }
  }, [manualValue, figmaValue, onApply]);

  return (
    <div className="flex items-center gap-2 py-1.5">
      <span className="text-[11px] text-gray-400 w-24 shrink-0">{label}</span>

      <div className="flex items-center gap-1.5 flex-1 min-w-0">
        {/* Current value badge */}
        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-700 text-gray-300 shrink-0">
          {Math.round(currentValue)}
          {unit}
        </span>

        {figmaValue !== null && (
          <>
            <span className="text-[10px] text-gray-600">→</span>
            {/* Figma value badge */}
            <span
              className={`text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0 ${
                hasMismatch
                  ? "bg-red-900/40 text-red-300 ring-1 ring-red-500/30"
                  : "bg-green-900/40 text-green-300 ring-1 ring-green-500/30"
              }`}
            >
              {Math.round(figmaValue)}
              {unit}
            </span>

            {hasMismatch && (
              <span className="text-[10px] text-red-400 font-mono shrink-0">
                ({figmaValue - currentValue > 0 ? "+" : ""}
                {Math.round(figmaValue - currentValue)})
              </span>
            )}
          </>
        )}
      </div>

      <div className="flex items-center gap-1 shrink-0">
        <input
          type="number"
          value={manualValue}
          onChange={(e) => setManualValue(e.target.value)}
          placeholder={figmaValue !== null ? String(Math.round(figmaValue)) : ""}
          className="w-12 text-center text-[10px] bg-gray-900 border border-gray-700 rounded py-0.5 text-white placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
        <button
          type="button"
          onClick={handleFix}
          disabled={figmaValue === null && manualValue === ""}
          className="px-1.5 py-0.5 text-[10px] font-medium rounded bg-blue-600 text-white hover:bg-blue-500 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed transition-colors"
        >
          Fix
        </button>
      </div>
    </div>
  );
}

interface NodeSectionProps {
  node: SelectedNode;
  figma: FigmaNodeProperties | null;
  onApplyProperty: (
    nodeId: string,
    property: string,
    value: number
  ) => void;
}

function NodeSection({ node, figma, onApplyProperty }: NodeSectionProps) {
  const cs = node.computedStyles;
  const text = figma?.text ?? null;

  const currentFontSize = parsePx(cs?.fontSize);
  const currentLineHeight = parsePx(cs?.lineHeight);
  const currentLetterSpacing = parsePx(cs?.letterSpacing);

  const figmaFontSize = text?.fontSize ?? null;
  const figmaLineHeight =
    text?.lineHeight !== null && text?.lineHeight !== undefined
      ? text.lineHeight
      : null;
  const figmaLetterSpacing = text?.letterSpacing ?? null;

  return (
    <div className="space-y-0.5">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] font-mono text-blue-400 truncate max-w-[180px]">
          {figma?.name || node.nodeId}
        </span>
        {figma?.type === "TEXT" && (
          <span className="text-[9px] px-1 py-0.5 rounded bg-purple-900/40 text-purple-300">
            TEXT
          </span>
        )}
      </div>

      <PropertyRow
        label="Font Size"
        currentValue={currentFontSize}
        figmaValue={figmaFontSize}
        onApply={(v) => onApplyProperty(node.nodeId, "font-size", v)}
      />
      <PropertyRow
        label="Line Height"
        currentValue={currentLineHeight}
        figmaValue={figmaLineHeight}
        onApply={(v) => onApplyProperty(node.nodeId, "line-height", v)}
      />
      <PropertyRow
        label="Letter Spacing"
        currentValue={currentLetterSpacing}
        figmaValue={figmaLetterSpacing}
        onApply={(v) => onApplyProperty(node.nodeId, "letter-spacing", v)}
      />
    </div>
  );
}

export default function TextSpacingPanel() {
  const selectedNodes = useEditorStore((s) => s.selectedNodes);
  const selectedNode = useEditorStore((s) => s.selectedNode);
  const htmlContent = useEditorStore((s) => s.htmlContent);
  const cssContent = useEditorStore((s) => s.cssContent);
  const applyEdit = useEditorStore((s) => s.applyEdit);
  const jobId = useEditorStore((s) => s.jobId);

  const [figmaData, setFigmaData] = useState<
    Record<string, FigmaNodeProperties>
  >({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fetchedRef = useRef<string>("");

  const nodes = useMemo(
    () =>
      selectedNodes.length > 0
        ? selectedNodes
        : selectedNode
          ? [selectedNode]
          : [],
    [selectedNodes, selectedNode]
  );

  const nodeIdsCacheKey = useMemo(
    () => nodes.map((n) => n.nodeId).sort().join(","),
    [nodes]
  );

  useEffect(() => {
    if (!jobId || nodeIdsCacheKey === "") {
      setFigmaData({});
      fetchedRef.current = "";
      return;
    }

    if (nodeIdsCacheKey === fetchedRef.current) return;
    fetchedRef.current = nodeIdsCacheKey;

    setLoading(true);
    setError(null);

    fetchDesignSpecNodes(jobId, nodes.map((n) => n.nodeId))
      .then((data) => {
        setFigmaData(data);
        setLoading(false);
      })
      .catch((err) => {
        console.warn("[TextSpacingPanel] Failed to fetch Figma data:", err);
        setError("Could not load Figma values");
        setLoading(false);
      });
  }, [jobId, nodeIdsCacheKey, nodes]);

  const handleApplyProperty = useCallback(
    (nodeId: string, property: string, value: number) => {
      const { html: newHtml, css: newCss } = updateTypographyProperty(
        htmlContent,
        cssContent,
        nodeId,
        property,
        formatPx(value)
      );

      const op: EditOperation = {
        nodeId,
        field: "css",
        oldValue: "",
        newValue: `${property}: ${formatPx(value)}`,
        prevHtml: htmlContent,
        prevCss: cssContent,
        timestamp: Date.now(),
      };
      applyEdit(op, newHtml, newCss);
    },
    [htmlContent, cssContent, applyEdit]
  );

  const handleApplyParentGap = useCallback(
    (nodeId: string, value: number) => {
      const { html: newHtml, css: newCss } = updateParentGap(
        htmlContent,
        cssContent,
        nodeId,
        formatPx(value)
      );

      const op: EditOperation = {
        nodeId,
        field: "css",
        oldValue: "",
        newValue: `parent gap: ${formatPx(value)}`,
        prevHtml: htmlContent,
        prevCss: cssContent,
        timestamp: Date.now(),
      };
      applyEdit(op, newHtml, newCss);
    },
    [htmlContent, cssContent, applyEdit]
  );

  const handleFixAll = useCallback(() => {
    let currentHtml = htmlContent;
    let currentCss = cssContent;
    const ops: string[] = [];

    for (const node of nodes) {
      const figma = figmaData[node.nodeId];
      if (!figma?.text) continue;

      const cs = node.computedStyles;
      const text = figma.text;

      const fixes: [string, number, number][] = [];
      const curFs = parsePx(cs?.fontSize);
      if (text.fontSize && Math.abs(curFs - text.fontSize) >= 0.5) {
        fixes.push(["font-size", curFs, text.fontSize]);
      }
      if (
        text.lineHeight !== null &&
        text.lineHeight !== undefined
      ) {
        const curLh = parsePx(cs?.lineHeight);
        if (Math.abs(curLh - text.lineHeight) >= 0.5) {
          fixes.push(["line-height", curLh, text.lineHeight]);
        }
      }
      if (text.letterSpacing !== undefined) {
        const curLs = parsePx(cs?.letterSpacing);
        if (Math.abs(curLs - text.letterSpacing) >= 0.5) {
          fixes.push(["letter-spacing", curLs, text.letterSpacing]);
        }
      }

      for (const [prop, , val] of fixes) {
        const result = updateTypographyProperty(
          currentHtml,
          currentCss,
          node.nodeId,
          prop,
          formatPx(val)
        );
        currentHtml = result.html;
        currentCss = result.css;
        ops.push(`${node.nodeId}: ${prop}=${formatPx(val)}`);
      }
    }

    // Also fix parent gap if mismatched
    if (nodes.length > 0) {
      const firstNode = nodes[0];
      const figma = figmaData[firstNode.nodeId];
      if (figma?.parentLayout) {
        const currentGap = parsePx(firstNode.computedStyles?.parentGap);
        const figmaGap = figma.parentLayout.gap;
        if (figmaGap > 0 && Math.abs(currentGap - figmaGap) >= 0.5) {
          const result = updateParentGap(
            currentHtml,
            currentCss,
            firstNode.nodeId,
            formatPx(figmaGap)
          );
          currentHtml = result.html;
          currentCss = result.css;
          ops.push(`parent gap=${formatPx(figmaGap)}`);
        }
      }
    }

    if (ops.length === 0) return;

    const op: EditOperation = {
      nodeId: nodes[0]?.nodeId ?? "",
      field: "css",
      oldValue: "",
      newValue: `Fix all: ${ops.join("; ")}`,
      prevHtml: htmlContent,
      prevCss: cssContent,
      timestamp: Date.now(),
    };
    applyEdit(op, currentHtml, currentCss);
  }, [htmlContent, cssContent, nodes, figmaData, applyEdit]);

  if (nodes.length === 0) {
    return (
      <p className="text-xs text-gray-500 text-center py-4">
        Select a node in the preview to inspect typography
      </p>
    );
  }

  const hasMismatches = nodes.some((node) => {
    const figma = figmaData[node.nodeId];
    if (!figma?.text) return false;
    const cs = node.computedStyles;
    const text = figma.text;
    if (text.fontSize && Math.abs(parsePx(cs?.fontSize) - text.fontSize) >= 0.5) return true;
    if (text.lineHeight !== null && Math.abs(parsePx(cs?.lineHeight) - text.lineHeight) >= 0.5) return true;
    if (text.letterSpacing && Math.abs(parsePx(cs?.letterSpacing) - text.letterSpacing) >= 0.5) return true;
    return false;
  });

  const firstNode = nodes[0];
  const firstFigma = figmaData[firstNode.nodeId];
  const parentGapCurrent = parsePx(firstNode.computedStyles?.parentGap);
  const parentGapFigma = firstFigma?.parentLayout?.gap ?? null;

  return (
    <div className="space-y-3">
      {loading && (
        <div className="flex items-center gap-2 py-2">
          <div className="w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
          <span className="text-[11px] text-gray-400">
            Loading Figma values...
          </span>
        </div>
      )}

      {error && (
        <p className="text-[11px] text-amber-400 bg-amber-900/20 px-2 py-1.5 rounded">
          {error}
        </p>
      )}

      {/* Per-node typography properties */}
      {nodes.map((node, idx) => (
        <div key={node.nodeId}>
          {idx > 0 && <div className="border-t border-gray-700 my-2" />}
          <NodeSection
            node={node}
            figma={figmaData[node.nodeId] ?? null}
            onApplyProperty={handleApplyProperty}
          />
        </div>
      ))}

      {/* Parent container gap section */}
      {(parentGapFigma !== null || parentGapCurrent > 0) && (
        <div className="border-t border-gray-700 pt-3">
          <span className="text-[11px] font-medium text-gray-300 block mb-1.5">
            Container Gap (between siblings)
          </span>
          <PropertyRow
            label="Gap"
            currentValue={parentGapCurrent}
            figmaValue={parentGapFigma}
            onApply={(v) => handleApplyParentGap(firstNode.nodeId, v)}
          />
        </div>
      )}

      {/* Fix All button */}
      {hasMismatches && (
        <div className="border-t border-gray-700 pt-3">
          <button
            type="button"
            onClick={handleFixAll}
            className="w-full px-3 py-2 text-xs font-medium rounded bg-blue-600 text-white hover:bg-blue-500 transition-colors flex items-center justify-center gap-1.5"
          >
            <svg
              className="w-3.5 h-3.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M5 13l4 4L19 7"
              />
            </svg>
            Fix All Mismatches
          </button>
          <p className="text-[10px] text-gray-500 text-center mt-1">
            Apply all Figma values to selected nodes
          </p>
        </div>
      )}

      {/* Helper text for multi-select */}
      {nodes.length === 1 && (
        <p className="text-[10px] text-gray-600 text-center pt-1">
          Ctrl/Shift+Click more nodes to compare multiple
        </p>
      )}
    </div>
  );
}
