"use client";

import { useCallback, useEffect, useRef } from "react";
import { useParams } from "next/navigation";
import { useEditorStore } from "@/store/useEditorStore";
import { fetchJob, fetchHtml, fetchCss } from "@/lib/api";
import { createJobWebSocket } from "@/lib/websocket";
import Toolbar from "@/components/Toolbar";
import PreviewFrame from "@/components/PreviewFrame";
import CodePanel from "@/components/CodePanel";
import ElementEditor from "@/components/ElementEditor";
import AIFixModal from "@/components/AIFixModal";
import DragOverlay from "@/components/DragOverlay";
import ErrorBoundary from "@/components/ErrorBoundary";
import type { JobStatus } from "@/types/editor";

const PIPELINE_STEPS = [
  { key: "parsing", label: "Parsing Design" },
  { key: "layout", label: "Layout Strategy" },
  { key: "generation", label: "Generating Code" },
  { key: "verification", label: "Visual Verification" },
  { key: "fixing", label: "Applying Fixes" },
  { key: "complete", label: "Complete" },
];

function PipelineProgress({
  step,
  progress,
}: {
  step: string;
  progress: number;
}) {
  const stepLower = step.toLowerCase();
  const activeIdx = PIPELINE_STEPS.findIndex(
    (s) => stepLower.includes(s.key)
  );

  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="w-full max-w-lg p-8">
        <h2 className="text-lg font-semibold text-white text-center mb-6">
          Generating your code...
        </h2>
        <div className="space-y-3">
          {PIPELINE_STEPS.map((s, i) => {
            const isActive = i === activeIdx;
            const isDone = i < activeIdx;
            return (
              <div key={s.key} className="flex items-center gap-3">
                <div
                  className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                    isDone
                      ? "bg-green-600 text-white"
                      : isActive
                        ? "bg-blue-600 text-white animate-pulse"
                        : "bg-gray-800 text-gray-500"
                  }`}
                >
                  {isDone ? "✓" : i + 1}
                </div>
                <span
                  className={`text-sm ${
                    isDone
                      ? "text-green-400"
                      : isActive
                        ? "text-white font-medium"
                        : "text-gray-500"
                  }`}
                >
                  {s.label}
                </span>
              </div>
            );
          })}
        </div>
        <div className="mt-6">
          <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-700"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="text-xs text-gray-500 text-center mt-2">
            {progress}% complete
          </p>
        </div>
      </div>
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="flex-1 flex items-center justify-center p-8">
      <div className="text-center max-w-md">
        <div className="text-4xl mb-4">⚠️</div>
        <h2 className="text-lg font-medium text-red-400 mb-2">
          Job Failed
        </h2>
        <p className="text-sm text-gray-400">{message}</p>
        <a
          href="/"
          className="inline-block mt-4 px-4 py-2 text-sm bg-gray-800 text-gray-300 rounded-md hover:bg-gray-700"
        >
          Back to Jobs
        </a>
      </div>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        <span className="text-sm text-gray-400">Loading job...</span>
      </div>
    </div>
  );
}

export default function JobPage() {
  const params = useParams();
  const jobId = params.jobId as string;
  const wsRef = useRef<{ close: () => void } | null>(null);

  const loadJob = useEditorStore((s) => s.loadJob);
  const setProgress = useEditorStore((s) => s.setProgress);
  const setLoading = useEditorStore((s) => s.setLoading);
  const setHtml = useEditorStore((s) => s.setHtml);
  const setCss = useEditorStore((s) => s.setCss);
  const reset = useEditorStore((s) => s.reset);

  const isLoading = useEditorStore((s) => s.isLoading);
  const jobStatus = useEditorStore((s) => s.jobStatus);
  const storeJobId = useEditorStore((s) => s.jobId);
  const progress = useEditorStore((s) => s.progress);
  const currentStep = useEditorStore((s) => s.currentStep);
  const htmlContent = useEditorStore((s) => s.htmlContent);

  const loadJobData = useCallback(async () => {
    setLoading(true);
    try {
      const job = await fetchJob(jobId);
      const status = job.status as JobStatus;

      if (status === "completed") {
        const [html, css] = await Promise.all([
          fetchHtml(jobId),
          fetchCss(jobId),
        ]);
        loadJob(jobId, html, css, status);
      } else {
        loadJob(jobId, "", "", status);
        setProgress(job.progress, job.currentStep, status);
      }
    } catch (err) {
      console.error("Failed to load job:", err);
      loadJob(jobId, "", "", "failed");
    }
  }, [jobId, loadJob, setProgress, setLoading]);

  useEffect(() => {
    loadJobData();
    return () => reset();
  }, [loadJobData, reset]);

  useEffect(() => {
    if (!jobId) return;

    const ws = createJobWebSocket(jobId, {
      onProgress: (msg) => {
        setProgress(
          msg.progress,
          msg.step,
          msg.status as JobStatus
        );
      },
      onCompleted: async () => {
        try {
          const [html, css] = await Promise.all([
            fetchHtml(jobId),
            fetchCss(jobId),
          ]);
          loadJob(jobId, html, css, "completed");
        } catch (err) {
          console.error("Failed to load completed job:", err);
        }
      },
      onError: (msg) => {
        setProgress(0, msg.error, "failed");
      },
    });
    wsRef.current = ws;

    return () => ws.close();
  }, [jobId, loadJob, setProgress, setHtml, setCss]);

  if (isLoading) {
    return (
      <div className="h-screen flex flex-col">
        <Toolbar />
        <LoadingState />
      </div>
    );
  }

  if (jobStatus === "failed") {
    return (
      <div className="h-screen flex flex-col">
        <Toolbar />
        <ErrorState message={currentStep || "An unknown error occurred"} />
      </div>
    );
  }

  if (jobStatus && jobStatus !== "completed" && !htmlContent) {
    return (
      <div className="h-screen flex flex-col">
        <Toolbar />
        <PipelineProgress step={currentStep} progress={progress} />
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <ErrorBoundary>
        <Toolbar />
      </ErrorBoundary>
      <div className="flex-1 flex overflow-hidden">
        <ErrorBoundary>
          <PreviewFrame />
        </ErrorBoundary>
        <ErrorBoundary>
          <CodePanel />
        </ErrorBoundary>
      </div>
      <ElementEditor />
      <AIFixModal />
      <DragOverlay />
    </div>
  );
}
