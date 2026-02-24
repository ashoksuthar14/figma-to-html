"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useEditorStore } from "@/store/useEditorStore";
import { updateSpacing, applyPositionDelta } from "@/lib/codeMutator";
import { computePositionDelta } from "@/lib/positionCalculator";
import type { EditOperation } from "@/types/editor";

const MARGIN_SIDES = [
  { key: "margin-top", label: "T" },
  { key: "margin-right", label: "R" },
  { key: "margin-bottom", label: "B" },
  { key: "margin-left", label: "L" },
] as const;

const PADDING_SIDES = [
  { key: "padding-top", label: "T" },
  { key: "padding-right", label: "R" },
  { key: "padding-bottom", label: "B" },
  { key: "padding-left", label: "L" },
] as const;

function parsePx(val: string | undefined): number {
  if (!val) return 0;
  const n = parseFloat(val);
  return isNaN(n) ? 0 : Math.round(n);
}

interface SpacingInputProps {
  label: string;
  value: number;
  onChange: (val: number) => void;
}

function SpacingInput({ label, value, onChange }: SpacingInputProps) {
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "ArrowUp") {
        e.preventDefault();
        onChange(value + 1);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        onChange(Math.max(0, value - 1));
      }
    },
    [value, onChange]
  );

  return (
    <div className="flex items-center gap-1">
      <span className="text-[10px] text-gray-500 w-3 text-center font-mono">
        {label}
      </span>
      <div className="flex items-center bg-gray-900 border border-gray-700 rounded">
        <button
          type="button"
          onClick={() => onChange(Math.max(0, value - 1))}
          className="px-1 py-0.5 text-[10px] text-gray-400 hover:text-white hover:bg-gray-700 rounded-l transition-colors"
          tabIndex={-1}
        >
          -
        </button>
        <input
          type="number"
          value={value}
          onChange={(e) => onChange(Math.max(0, parseInt(e.target.value) || 0))}
          onKeyDown={handleKeyDown}
          className="w-10 text-center text-xs bg-transparent text-white border-x border-gray-700 py-0.5 focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
        <button
          type="button"
          onClick={() => onChange(value + 1)}
          className="px-1 py-0.5 text-[10px] text-gray-400 hover:text-white hover:bg-gray-700 rounded-r transition-colors"
          tabIndex={-1}
        >
          +
        </button>
      </div>
    </div>
  );
}

export default function SpacingPanel() {
  const selectedNode = useEditorStore((s) => s.selectedNode);
  const htmlContent = useEditorStore((s) => s.htmlContent);
  const cssContent = useEditorStore((s) => s.cssContent);
  const applyEdit = useEditorStore((s) => s.applyEdit);
  const scale = useEditorStore((s) => s.scale);

  const isPositionMode = useEditorStore((s) => s.isPositionMode);
  const dragStart = useEditorStore((s) => s.dragStart);
  const dragCurrent = useEditorStore((s) => s.dragCurrent);
  const layoutInfo = useEditorStore((s) => s.layoutInfo);
  const originalRect = useEditorStore((s) => s.originalRect);
  const parentRect = useEditorStore((s) => s.parentRect);
  const enterPositionMode = useEditorStore((s) => s.enterPositionMode);
  const exitPositionMode = useEditorStore((s) => s.exitPositionMode);

  const [values, setValues] = useState<Record<string, number>>({});
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (!selectedNode?.computedStyles) {
      setValues({});
      initializedRef.current = false;
      return;
    }
    const cs = selectedNode.computedStyles;
    setValues({
      "margin-top": parsePx(cs.marginTop),
      "margin-right": parsePx(cs.marginRight),
      "margin-bottom": parsePx(cs.marginBottom),
      "margin-left": parsePx(cs.marginLeft),
      "padding-top": parsePx(cs.paddingTop),
      "padding-right": parsePx(cs.paddingRight),
      "padding-bottom": parsePx(cs.paddingBottom),
      "padding-left": parsePx(cs.paddingLeft),
    });
    initializedRef.current = true;
  }, [selectedNode]);

  const handleChange = useCallback(
    (property: string, newVal: number) => {
      setValues((prev) => ({ ...prev, [property]: newVal }));

      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        if (!selectedNode) return;
        const { html: newHtml, css: newCss } = updateSpacing(
          htmlContent,
          cssContent,
          selectedNode.nodeId,
          property,
          `${newVal}px`
        );

        const op: EditOperation = {
          nodeId: selectedNode.nodeId,
          field: property.startsWith("margin") ? "margin" : "padding",
          oldValue: `${values[property] ?? 0}px`,
          newValue: `${newVal}px`,
          prevHtml: htmlContent,
          prevCss: cssContent,
          timestamp: Date.now(),
        };
        applyEdit(op, newHtml, newCss);
      }, 150);
    },
    [selectedNode, htmlContent, cssContent, applyEdit, values]
  );

  const handleEnterPositionMode = useCallback(() => {
    if (!selectedNode) return;
    enterPositionMode();
    const iframe = document.querySelector("iframe");
    if (iframe?.contentWindow) {
      iframe.contentWindow.postMessage(
        { type: "get-layout-info", nodeId: selectedNode.nodeId },
        "*"
      );
    }
  }, [selectedNode, enterPositionMode]);

  const handleSavePosition = useCallback(() => {
    if (!selectedNode || !dragStart || !dragCurrent || !layoutInfo) {
      exitPositionMode();
      return;
    }

    const rawDx = dragCurrent.x - dragStart.x;
    const rawDy = dragCurrent.y - dragStart.y;

    const deltaX = rawDx / scale;
    const deltaY = rawDy / scale;

    if (Math.abs(deltaX) < 0.5 && Math.abs(deltaY) < 0.5) {
      exitPositionMode();
      return;
    }

    const computedStyles = selectedNode.computedStyles ?? {
      marginTop: "0px", marginRight: "0px", marginBottom: "0px", marginLeft: "0px",
      paddingTop: "0px", paddingRight: "0px", paddingBottom: "0px", paddingLeft: "0px",
    };

    const patches = computePositionDelta(deltaX, deltaY, layoutInfo, computedStyles);
    if (patches.length === 0) {
      exitPositionMode();
      return;
    }

    const { html: newHtml, css: newCss } = applyPositionDelta(
      htmlContent, cssContent, selectedNode.nodeId, patches
    );

    const description = patches.map((p) => `${p.property}: ${p.value}`).join(", ");
    const op: EditOperation = {
      nodeId: selectedNode.nodeId,
      field: "position",
      oldValue: "",
      newValue: description,
      prevHtml: htmlContent,
      prevCss: cssContent,
      timestamp: Date.now(),
    };
    applyEdit(op, newHtml, newCss);
    exitPositionMode();
  }, [
    selectedNode, dragStart, dragCurrent, layoutInfo,
    scale, htmlContent, cssContent, applyEdit, exitPositionMode,
  ]);

  if (!selectedNode) return null;

  return (
    <div className="space-y-3">
      {isPositionMode ? (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={handleSavePosition}
            className="flex-1 px-3 py-1.5 text-xs font-medium rounded bg-blue-600 text-white hover:bg-blue-500 transition-colors"
          >
            Save Position
          </button>
          <button
            type="button"
            onClick={() => exitPositionMode()}
            className="flex-1 px-3 py-1.5 text-xs font-medium rounded bg-gray-700 text-gray-300 hover:bg-gray-600 transition-colors"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={handleEnterPositionMode}
          className="w-full px-3 py-1.5 text-xs font-medium rounded border border-blue-500/40 text-blue-400 hover:bg-blue-500/10 transition-colors flex items-center justify-center gap-1.5"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M5 9l-3 3 3 3" /><path d="M9 5l3-3 3 3" /><path d="M15 19l-3 3-3-3" /><path d="M19 9l3 3-3 3" /><line x1="2" y1="12" x2="22" y2="12" /><line x1="12" y1="2" x2="12" y2="22" />
          </svg>
          Drag to Position
        </button>
      )}

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-medium text-gray-300">Margin</span>
          <span className="text-[10px] text-gray-500">px</span>
        </div>
        <div className="grid grid-cols-4 gap-1">
          {MARGIN_SIDES.map((side) => (
            <SpacingInput
              key={side.key}
              label={side.label}
              value={values[side.key] ?? 0}
              onChange={(val) => handleChange(side.key, val)}
            />
          ))}
        </div>
      </div>

      <div className="border-t border-gray-700 pt-3">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs font-medium text-gray-300">Padding</span>
          <span className="text-[10px] text-gray-500">px</span>
        </div>
        <div className="grid grid-cols-4 gap-1">
          {PADDING_SIDES.map((side) => (
            <SpacingInput
              key={side.key}
              label={side.label}
              value={values[side.key] ?? 0}
              onChange={(val) => handleChange(side.key, val)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
