import type { Job, MicroFixResponse } from "@/types/editor";

const API_URL =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    : "http://localhost:8000";

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, init);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

async function apiText(path: string): Promise<string> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.text();
}

export async function fetchJobs(): Promise<Job[]> {
  return apiFetch<Job[]>("/jobs");
}

export async function fetchJob(jobId: string): Promise<Job> {
  return apiFetch<Job>(`/jobs/${jobId}`);
}

export async function fetchHtml(jobId: string): Promise<string> {
  return apiText(`/jobs/${jobId}/html`);
}

export async function fetchCss(jobId: string): Promise<string> {
  return apiText(`/jobs/${jobId}/css`);
}

export async function updateJob(
  jobId: string,
  html: string,
  css: string
): Promise<void> {
  await apiFetch(`/jobs/${jobId}/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ html, css }),
  });
}

export function getDownloadUrl(jobId: string): string {
  return `${API_URL}/jobs/${jobId}/download`;
}

export async function microFix(
  jobId: string,
  nodeId: string,
  userPrompt: string,
  html: string,
  css: string
): Promise<MicroFixResponse> {
  return apiFetch<MicroFixResponse>(`/jobs/${jobId}/micro-fix`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nodeId, userPrompt, html, css }),
  });
}

export async function deleteJob(jobId: string): Promise<void> {
  await apiFetch(`/jobs/${jobId}`, { method: "DELETE" });
}

export function getAssetBaseUrl(jobId: string): string {
  return `${API_URL}/jobs/${jobId}`;
}
