"use client";

import { useCallback } from "react";
import { useEditorStore } from "@/store/useEditorStore";
import { updateJob, getDownloadUrl } from "@/lib/api";
import DeviceSwitcher from "./DeviceSwitcher";

const STATUS_COLORS: Record<string, string> = {
  queued: "bg-gray-500",
  processing: "bg-yellow-500",
  verifying: "bg-purple-500",
  completed: "bg-green-500",
  failed: "bg-red-500",
};

export default function Toolbar() {
  const jobId = useEditorStore((s) => s.jobId);
  const jobStatus = useEditorStore((s) => s.jobStatus);
  const progress = useEditorStore((s) => s.progress);
  const currentStep = useEditorStore((s) => s.currentStep);
  const isDirty = useEditorStore((s) => s.isDirty);
  const isSaving = useEditorStore((s) => s.isSaving);
  const htmlContent = useEditorStore((s) => s.htmlContent);
  const cssContent = useEditorStore((s) => s.cssContent);
  const setSaving = useEditorStore((s) => s.setSaving);
  const markSaved = useEditorStore((s) => s.markSaved);
  const undo = useEditorStore((s) => s.undo);
  const editHistory = useEditorStore((s) => s.editHistory);

  const handleSave = useCallback(async () => {
    if (!jobId || !isDirty) return;
    setSaving(true);
    try {
      await updateJob(jobId, htmlContent, cssContent);
      markSaved();
    } catch (err) {
      console.error("Save failed:", err);
    } finally {
      setSaving(false);
    }
  }, [jobId, isDirty, htmlContent, cssContent, setSaving, markSaved]);

  const isProcessing = jobStatus === "processing" || jobStatus === "verifying";

  return (
    <div className="h-12 flex items-center justify-between px-4 bg-gray-900 border-b border-gray-700 shrink-0">
      <div className="flex items-center gap-3">
        <a
          href="/"
          className="text-gray-400 hover:text-white transition-colors"
          title="Back to jobs"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </a>

        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-white truncate max-w-[200px]">
            {jobId ? `Job ${jobId.slice(0, 8)}` : "No job"}
          </span>
          {jobStatus && (
            <span
              className={`px-2 py-0.5 text-[10px] uppercase font-semibold rounded-full text-white ${STATUS_COLORS[jobStatus] ?? "bg-gray-600"}`}
            >
              {jobStatus}
            </span>
          )}
        </div>

        {isProcessing && (
          <div className="flex items-center gap-2 ml-2">
            <div className="w-32 h-1.5 bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            <span className="text-xs text-gray-400 truncate max-w-[180px]">
              {currentStep}
            </span>
          </div>
        )}
      </div>

      <DeviceSwitcher />

      <div className="flex items-center gap-2">
        {editHistory.length > 0 && (
          <button
            onClick={undo}
            className="px-3 py-1.5 text-xs text-gray-300 bg-gray-800 rounded-md hover:bg-gray-700 transition-colors"
            title="Undo last edit"
          >
            Undo
          </button>
        )}

        <button
          onClick={handleSave}
          disabled={!isDirty || isSaving}
          className="px-4 py-1.5 text-xs font-medium rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed bg-blue-600 text-white hover:bg-blue-500"
        >
          {isSaving ? "Saving..." : isDirty ? "Save" : "Saved"}
        </button>

        {jobId && (
          <a
            href={getDownloadUrl(jobId)}
            download
            className="px-4 py-1.5 text-xs font-medium text-gray-300 bg-gray-800 rounded-md hover:bg-gray-700 transition-colors"
          >
            Download
          </a>
        )}
      </div>
    </div>
  );
}
