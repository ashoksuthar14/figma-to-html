"use client";

import { useMemo } from "react";
import { useEditorStore } from "@/store/useEditorStore";
import { useDrag } from "@/hooks/useDrag";

const MIN_SLACK_PX = 10;

export default function DragOverlay() {
  const isPositionMode = useEditorStore((s) => s.isPositionMode);
  const originalRect = useEditorStore((s) => s.originalRect);
  const parentRect = useEditorStore((s) => s.parentRect);
  const dragStart = useEditorStore((s) => s.dragStart);
  const dragCurrent = useEditorStore((s) => s.dragCurrent);
  const isDragging = useEditorStore((s) => s.isDragging);
  const scale = useEditorStore((s) => s.scale);
  const iframeContainerRect = useEditorStore((s) => s.iframeContainerRect);
  const vw = useEditorStore((s) => s.viewportWidth);
  const vh = useEditorStore((s) => s.viewportHeight);

  const startDrag = useEditorStore((s) => s.startDrag);
  const updateDrag = useEditorStore((s) => s.updateDrag);
  const endDrag = useEditorStore((s) => s.endDrag);

  const clampedDelta = useMemo(() => {
    if (!dragStart || !dragCurrent || !originalRect) {
      return { dx: 0, dy: 0 };
    }

    let rawDx = dragCurrent.x - dragStart.x;
    let rawDy = dragCurrent.y - dragStart.y;

    const useParentClamp = parentRect && (() => {
      const slackX = (parentRect.width - originalRect.width);
      const slackY = (parentRect.height - originalRect.height);
      return slackX >= MIN_SLACK_PX || slackY >= MIN_SLACK_PX;
    })();

    if (useParentClamp && parentRect) {
      const minDx = (parentRect.x - originalRect.x) * scale;
      const maxDx = (parentRect.x + parentRect.width - originalRect.x - originalRect.width) * scale;
      const minDy = (parentRect.y - originalRect.y) * scale;
      const maxDy = (parentRect.y + parentRect.height - originalRect.y - originalRect.height) * scale;

      rawDx = Math.max(minDx, Math.min(maxDx, rawDx));
      rawDy = Math.max(minDy, Math.min(maxDy, rawDy));
    } else {
      const minDx = -originalRect.x * scale;
      const maxDx = (vw - originalRect.x - originalRect.width) * scale;
      const minDy = -originalRect.y * scale;
      const maxDy = (vh - originalRect.y - originalRect.height) * scale;

      rawDx = Math.max(minDx, Math.min(maxDx, rawDx));
      rawDy = Math.max(minDy, Math.min(maxDy, rawDy));
    }

    return { dx: rawDx, dy: rawDy };
  }, [dragStart, dragCurrent, originalRect, parentRect, scale, vw, vh]);

  const { handlePointerDown } = useDrag({
    onStart: (x, y) => startDrag(x, y),
    onMove: (x, y) => updateDrag(x, y),
    onEnd: () => endDrag(),
  });

  if (!isPositionMode || !originalRect || !iframeContainerRect) return null;

  const screenX = iframeContainerRect.x + originalRect.x * scale;
  const screenY = iframeContainerRect.y + originalRect.y * scale;
  const screenW = originalRect.width * scale;
  const screenH = originalRect.height * scale;

  const iframeDeltaX = Math.abs(clampedDelta.dx) >= 0.5
    ? Math.round(clampedDelta.dx / scale)
    : 0;
  const iframeDeltaY = Math.abs(clampedDelta.dy) >= 0.5
    ? Math.round(clampedDelta.dy / scale)
    : 0;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        width: "100vw",
        height: "100vh",
        pointerEvents: "none",
        zIndex: 9999,
      }}
    >
      {parentRect && (
        <div
          style={{
            position: "absolute",
            left: iframeContainerRect.x + parentRect.x * scale,
            top: iframeContainerRect.y + parentRect.y * scale,
            width: parentRect.width * scale,
            height: parentRect.height * scale,
            border: "1px dashed rgba(99, 102, 241, 0.4)",
            borderRadius: 2,
            pointerEvents: "none",
          }}
        />
      )}

      <div
        onPointerDown={handlePointerDown}
        style={{
          position: "absolute",
          left: screenX,
          top: screenY,
          width: screenW,
          height: screenH,
          transform: `translate(${clampedDelta.dx}px, ${clampedDelta.dy}px)`,
          border: "2px solid rgba(59, 130, 246, 0.8)",
          borderRadius: 2,
          background: isDragging
            ? "rgba(59, 130, 246, 0.08)"
            : "rgba(59, 130, 246, 0.04)",
          cursor: "move",
          pointerEvents: "auto",
          boxShadow: isDragging
            ? "0 0 12px rgba(59, 130, 246, 0.3)"
            : "0 0 6px rgba(59, 130, 246, 0.15)",
          transition: isDragging ? "none" : "box-shadow 0.2s ease",
          willChange: "transform",
        }}
      />

      {(iframeDeltaX !== 0 || iframeDeltaY !== 0) && (
        <div
          style={{
            position: "absolute",
            left: screenX + clampedDelta.dx + screenW + 8,
            top: screenY + clampedDelta.dy - 4,
            background: "rgba(30, 41, 59, 0.95)",
            color: "#93c5fd",
            fontSize: 11,
            fontFamily: "monospace",
            padding: "2px 6px",
            borderRadius: 4,
            whiteSpace: "nowrap",
            pointerEvents: "none",
            border: "1px solid rgba(59, 130, 246, 0.3)",
          }}
        >
          {iframeDeltaX >= 0 ? "+" : ""}{iframeDeltaX}, {iframeDeltaY >= 0 ? "+" : ""}{iframeDeltaY}px
        </div>
      )}
    </div>
  );
}
