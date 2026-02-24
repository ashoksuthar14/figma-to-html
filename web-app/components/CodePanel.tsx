"use client";

import { useEffect, useRef, useState } from "react";
import { useEditorStore } from "@/store/useEditorStore";
import { getDownloadUrl } from "@/lib/api";

type Tab = "html" | "css";

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function highlightHtml(code: string): string {
  return escapeHtml(code)
    .replace(
      /(&lt;\/?)([\w-]+)/g,
      '$1<span class="text-red-400">$2</span>'
    )
    .replace(
      /([\w-]+)(=)/g,
      '<span class="text-yellow-300">$1</span>$2'
    )
    .replace(
      /(&quot;[^&]*&quot;)/g,
      '<span class="text-green-400">$1</span>'
    );
}

function highlightCss(code: string): string {
  return escapeHtml(code)
    .replace(
      /(\.[\w-]+)/g,
      '<span class="text-yellow-300">$1</span>'
    )
    .replace(
      /([\w-]+)(\s*:)/g,
      '<span class="text-blue-300">$1</span>$2'
    );
}

export default function CodePanel() {
  const [activeTab, setActiveTab] = useState<Tab>("html");
  const [copied, setCopied] = useState(false);
  const codeRef = useRef<HTMLPreElement>(null);

  const html = useEditorStore((s) => s.htmlContent);
  const css = useEditorStore((s) => s.cssContent);
  const jobId = useEditorStore((s) => s.jobId);
  const userModified = useEditorStore((s) => s.userModified);

  const code = activeTab === "html" ? html : css;
  const highlighted =
    activeTab === "html" ? highlightHtml(code) : highlightCss(code);

  useEffect(() => {
    setCopied(false);
  }, [activeTab]);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard not available
    }
  }

  return (
    <div className="w-[400px] min-w-[300px] flex flex-col bg-gray-900 border-l border-gray-700">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-700">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setActiveTab("html")}
            className={`px-3 py-1 text-xs rounded-md transition-colors ${
              activeTab === "html"
                ? "bg-gray-700 text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            index.html
          </button>
          <button
            onClick={() => setActiveTab("css")}
            className={`px-3 py-1 text-xs rounded-md transition-colors ${
              activeTab === "css"
                ? "bg-gray-700 text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            styles.css
          </button>
          {userModified && (
            <span className="ml-2 px-1.5 py-0.5 text-[10px] bg-amber-600/20 text-amber-400 rounded">
              Modified
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={handleCopy}
            className="p-1.5 text-gray-400 hover:text-white rounded transition-colors"
            title="Copy to clipboard"
          >
            {copied ? (
              <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
            )}
          </button>
          {jobId && (
            <a
              href={getDownloadUrl(jobId)}
              download
              className="p-1.5 text-gray-400 hover:text-white rounded transition-colors"
              title="Download ZIP"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            </a>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <pre
          ref={codeRef}
          className="p-4 text-xs leading-5 font-mono text-gray-300 whitespace-pre-wrap break-words"
          dangerouslySetInnerHTML={{ __html: highlighted }}
        />
      </div>
    </div>
  );
}
