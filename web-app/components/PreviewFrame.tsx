"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { useEditorStore } from "@/store/useEditorStore";
import { buildSrcdoc } from "@/lib/domMapper";
import { getAssetBaseUrl } from "@/lib/api";
import type {
  IframeNodeClickMessage,
  LayoutInfoResponseMessage,
  SelectedNode,
} from "@/types/editor";

export default function PreviewFrame() {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const jobId = useEditorStore((s) => s.jobId);
  const html = useEditorStore((s) => s.htmlContent);
  const css = useEditorStore((s) => s.cssContent);
  const vw = useEditorStore((s) => s.viewportWidth);
  const vh = useEditorStore((s) => s.viewportHeight);
  const scale = useEditorStore((s) => s.scale);
  const selectNode = useEditorStore((s) => s.selectNode);
  const toggleNodeSelection = useEditorStore((s) => s.toggleNodeSelection);
  const selectedNodes = useEditorStore((s) => s.selectedNodes);
  const setScale = useEditorStore((s) => s.setScale);
  const setLayoutInfo = useEditorStore((s) => s.setLayoutInfo);
  const setIframeContainerRect = useEditorStore((s) => s.setIframeContainerRect);

  const assetBase = useMemo(
    () => (jobId ? getAssetBaseUrl(jobId) : ""),
    [jobId]
  );

  const srcdoc = useMemo(() => {
    if (!html) return "";
    return buildSrcdoc(html, css, assetBase);
  }, [html, css, assetBase]);

  const handleMessage = useCallback(
    (event: MessageEvent) => {
      const data = event.data;
      if (!data?.type) return;

      if (data.type === "node-click" && data.nodeId) {
        const msg = data as IframeNodeClickMessage;
        const node: SelectedNode = {
          nodeId: msg.nodeId,
          tagName: msg.tagName,
          textContent: msg.textContent,
          rect: msg.rect,
          className: msg.className,
          computedStyles: msg.computedStyles,
          href: msg.href,
          target: msg.target,
        };
        if (msg.ctrlKey || msg.shiftKey) {
          toggleNodeSelection(node);
        } else {
          selectNode(node);
        }
        return;
      }

      if (data.type === "layout-info-response" && data.nodeId) {
        const msg = data as LayoutInfoResponseMessage;
        setLayoutInfo(msg.layoutInfo, msg.rect, msg.parentRect);
      }
    },
    [selectNode, toggleNodeSelection, setLayoutInfo]
  );

  useEffect(() => {
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [handleMessage]);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe?.contentWindow) return;
    iframe.contentWindow.postMessage(
      { type: "highlight-nodes", nodeIds: selectedNodes.map((n) => n.nodeId) },
      "*"
    );
  }, [selectedNodes]);

  useEffect(() => {
    if (!containerRef.current) return;
    const container = containerRef.current.parentElement;
    if (!container) return;

    const cw = container.clientWidth - 48;
    const ch = container.clientHeight - 48;
    const sw = cw / vw;
    const sh = ch / vh;
    const newScale = Math.min(sw, sh, 1);
    setScale(newScale);
  }, [vw, vh, setScale]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const updateRect = () => {
      const r = el.getBoundingClientRect();
      setIframeContainerRect({ x: r.x, y: r.y, width: r.width, height: r.height });
    };

    updateRect();
    const ro = new ResizeObserver(updateRect);
    ro.observe(el);
    window.addEventListener("scroll", updateRect, true);

    return () => {
      ro.disconnect();
      window.removeEventListener("scroll", updateRect, true);
    };
  }, [setIframeContainerRect]);

  return (
    <div className="flex-1 overflow-auto flex items-start justify-center p-6 bg-gray-900/50">
      <div ref={containerRef} className="relative">
        <div
          style={{
            width: vw,
            height: vh,
            transform: `scale(${scale})`,
            transformOrigin: "top left",
          }}
        >
          <iframe
            ref={iframeRef}
            srcDoc={srcdoc}
            sandbox="allow-scripts"
            className="w-full h-full border border-gray-700 bg-white"
            title="Preview"
          />
        </div>
      </div>
    </div>
  );
}
