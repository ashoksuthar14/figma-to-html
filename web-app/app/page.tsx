"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { fetchJobs, deleteJob } from "@/lib/api";
import type { Job, JobStatus } from "@/types/editor";

const STATUS_COLORS: Record<JobStatus, string> = {
  queued: "bg-gray-500",
  processing: "bg-yellow-500",
  verifying: "bg-purple-500",
  completed: "bg-green-500",
  failed: "bg-red-500",
};

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export default function HomePage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const loadJobs = useCallback(async () => {
    try {
      const data = await fetchJobs();
      setJobs(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, []);

  const handleDelete = useCallback(
    async (e: React.MouseEvent, jobId: string) => {
      e.preventDefault();
      e.stopPropagation();
      if (!confirm("Delete this design? This cannot be undone.")) return;
      setDeleting(jobId);
      try {
        await deleteJob(jobId);
        setJobs((prev) => prev.filter((j) => j.jobId !== jobId));
      } catch (err) {
        setError(err instanceof Error ? err.message : "Delete failed");
      } finally {
        setDeleting(null);
      }
    },
    []
  );

  useEffect(() => {
    loadJobs();
    const interval = setInterval(loadJobs, 10_000);
    return () => clearInterval(interval);
  }, [loadJobs]);

  return (
    <div className="min-h-screen bg-gray-950">
      <header className="border-b border-gray-800">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">
              Figma Preview Editor
            </h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Preview and edit generated HTML/CSS
            </p>
          </div>
          <button
            onClick={loadJobs}
            className="px-3 py-1.5 text-xs bg-gray-800 text-gray-300 rounded-md hover:bg-gray-700 transition-colors"
          >
            Refresh
          </button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 p-4 bg-red-900/30 border border-red-800 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div
                key={i}
                className="h-20 bg-gray-900 rounded-lg animate-pulse"
              />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <div className="text-center py-20">
            <div className="text-4xl mb-4">📐</div>
            <h2 className="text-lg font-medium text-gray-300 mb-2">
              No jobs yet
            </h2>
            <p className="text-sm text-gray-500 max-w-md mx-auto">
              Run the Figma plugin to create a conversion job. It will appear
              here automatically.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {jobs.map((job) => (
              <Link
                key={job.jobId}
                href={`/job/${job.jobId}`}
                className="block p-4 bg-gray-900 border border-gray-800 rounded-lg hover:border-gray-600 transition-colors group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span
                      className={`w-2.5 h-2.5 rounded-full ${STATUS_COLORS[job.status]}`}
                    />
                    <div>
                      <span className="text-sm font-medium text-white group-hover:text-blue-400 transition-colors">
                        {job.frameName || `Job ${job.jobId.slice(0, 8)}`}
                      </span>
                      <p className="text-xs text-gray-500 mt-0.5">
                        {formatTime(job.createdAt)}
                        <span className="ml-2 text-gray-600">{job.jobId.slice(0, 8)}</span>
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3">
                    <span className="text-xs uppercase font-medium text-gray-400">
                      {job.status}
                    </span>
                    {job.status === "processing" && (
                      <div className="w-20 h-1.5 bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full transition-all"
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                    )}
                    <button
                      onClick={(e) => handleDelete(e, job.jobId)}
                      disabled={deleting === job.jobId}
                      className="p-1.5 text-gray-600 hover:text-red-400 rounded-md hover:bg-red-400/10 transition-colors opacity-0 group-hover:opacity-100 disabled:opacity-50"
                      title="Delete design"
                    >
                      {deleting === job.jobId ? (
                        <div className="w-4 h-4 border-2 border-red-400/30 border-t-red-400 rounded-full animate-spin" />
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      )}
                    </button>
                    <svg
                      className="w-4 h-4 text-gray-600 group-hover:text-gray-400 transition-colors"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                  </div>
                </div>

                {job.currentStep && job.status !== "completed" && (
                  <p className="text-xs text-gray-500 mt-2 pl-5">
                    {job.currentStep}
                  </p>
                )}
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
