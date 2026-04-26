import type { AnalysisResult, Finding, Project, WorkflowArtifact, WorkflowRun } from '../types';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(BASE + path);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  findings: {
    list: (params?: { project_id?: number; severity?: string; skip?: number; limit?: number }) =>
      get<Finding[]>('/findings', params as Record<string, string | number>),
    get: (id: number) => get<Finding>(`/findings/${id}`),
    explain: (id: number) => post<AnalysisResult>(`/findings/${id}/explain`),
  },
  projects: {
    list: () => get<Project[]>('/projects'),
    create: (name: string, github_url: string) =>
      post<Project>('/projects', { name, github_url }),
  },
  github: {
    runs: (branch = 'main', status = 'completed') =>
      get<WorkflowRun[]>('/github/runs', { branch, status }),
    artifacts: (runId: number) =>
      get<WorkflowArtifact[]>(`/github/runs/${runId}/artifacts`),
  },
  health: () => get<{ status: string }>('/health'),
};
