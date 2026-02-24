"use client";

import { useState } from "react";
import { useEditorStore } from "@/store/useEditorStore";
import { VIEWPORT_PRESETS } from "@/types/editor";

export default function DeviceSwitcher() {
  const vw = useEditorStore((s) => s.viewportWidth);
  const vh = useEditorStore((s) => s.viewportHeight);
  const scale = useEditorStore((s) => s.scale);
  const setViewport = useEditorStore((s) => s.setViewport);

  const [customW, setCustomW] = useState("");
  const [customH, setCustomH] = useState("");
  const [showCustom, setShowCustom] = useState(false);

  const activePreset = VIEWPORT_PRESETS.find(
    (p) => p.width === vw && p.height === vh
  );

  function applyCustom() {
    const w = parseInt(customW, 10);
    const h = parseInt(customH, 10);
    if (w > 0 && h > 0) {
      setViewport(w, h);
      setShowCustom(false);
    }
  }

  return (
    <div className="flex items-center gap-2">
      {VIEWPORT_PRESETS.map((preset) => (
        <button
          key={preset.name}
          onClick={() => setViewport(preset.width, preset.height)}
          className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
            activePreset?.name === preset.name
              ? "bg-blue-600 text-white"
              : "bg-gray-800 text-gray-300 hover:bg-gray-700"
          }`}
          title={`${preset.width}x${preset.height}`}
        >
          <span className="mr-1">{preset.icon}</span>
          {preset.name}
        </button>
      ))}

      {showCustom ? (
        <div className="flex items-center gap-1">
          <input
            type="number"
            value={customW}
            onChange={(e) => setCustomW(e.target.value)}
            placeholder="W"
            className="w-16 px-2 py-1 text-xs bg-gray-800 border border-gray-600 rounded text-white"
          />
          <span className="text-gray-500 text-xs">x</span>
          <input
            type="number"
            value={customH}
            onChange={(e) => setCustomH(e.target.value)}
            placeholder="H"
            className="w-16 px-2 py-1 text-xs bg-gray-800 border border-gray-600 rounded text-white"
          />
          <button
            onClick={applyCustom}
            className="px-2 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-500"
          >
            Set
          </button>
          <button
            onClick={() => setShowCustom(false)}
            className="px-2 py-1 text-xs text-gray-400 hover:text-white"
          >
            Cancel
          </button>
        </div>
      ) : (
        <button
          onClick={() => setShowCustom(true)}
          className="px-3 py-1.5 text-xs bg-gray-800 text-gray-300 rounded-md hover:bg-gray-700"
        >
          Custom
        </button>
      )}

      <span className="ml-2 text-xs text-gray-500">
        {vw}x{vh} ({Math.round(scale * 100)}%)
      </span>
    </div>
  );
}
