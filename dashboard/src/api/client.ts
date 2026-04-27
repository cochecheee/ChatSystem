import type { AnalysisResult, CommandRequest, CommandResponse, Finding, Project, TokenResponse, WorkflowArtifact, WorkflowRun } from '../types';

const BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

let _token: string | null = localStorage.getItem('auth_token');

export function setAuthToken(token: string | null) {
  _token = token;
  if (token) localStorage.setItem('auth_token', token);
  else localStorage.removeItem('auth_token');
}

export function getAuthToken() { return _token; }

function authHeaders(): Record<string, string> {
  return _token ? { Authorization: `Bearer ${_token}` } : {};
}

async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(BASE + path);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  const res = await fetch(url.toString(), { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((detail as { detail?: string }).detail ?? `${res.status} ${res.statusText}`);
  }
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
    runs: (status = 'completed') =>
      get<WorkflowRun[]>('/github/runs', { status }),
    artifacts: (runId: number) =>
      get<WorkflowArtifact[]>(`/github/runs/${runId}/artifacts`),
    runFindings: (runId: number) =>
      get<Finding[]>(`/github/runs/${runId}/findings`),
    reprocessRun: (runId: number) =>
      post<{ status: string; run_id: number; deleted_artifacts: number }>(
        `/github/runs/${runId}/reprocess`,
      ),
  },
  chat: {
    login: (username: string, role: string) =>
      post<TokenResponse>('/api/chat/auth/token', { username, role }),
    command: (req: CommandRequest) =>
      post<CommandResponse>('/api/chat/command', req),
    message: (text: string, finding_id?: number) =>
      post<{ reply: string; suggested_command: string | null }>(
        '/api/chat/message',
        { text, finding_id },
      ),
    reportUrl: () => `${BASE}/api/chat/report`,
  },
  health: () => get<{ status: string }>('/health'),
};
