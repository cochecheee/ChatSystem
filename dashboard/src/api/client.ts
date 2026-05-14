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

/**
 * Like `get` but also reads `X-Total-Count` header. Trả về `{ data, total }`.
 * Dùng cho `/findings` để biết tổng số match filter (server-side pagination).
 */
async function getWithTotal<T>(
  path: string,
  params?: Record<string, string | number>,
): Promise<{ data: T; total: number }> {
  const url = new URL(BASE + path);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  const res = await fetch(url.toString(), { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const data = (await res.json()) as T;
  const totalHeader = res.headers.get('X-Total-Count');
  const total = totalHeader ? parseInt(totalHeader, 10) : Array.isArray(data) ? data.length : 0;
  return { data, total };
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

export interface FindingListParams {
  project_id?: number;
  severity?: string;
  tool?: string;
  status?: string;
  category?: 'sast' | 'deps' | 'dast';
  q?: string;
  skip?: number;
  limit?: number;
}

async function getRaw<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export interface UptimeCheck {
  id: number;
  project_id: number;
  target_url: string;
  checked_at: string;
  http_status: number;
  response_time_ms: number | null;
  is_up: boolean;
  error_message: string | null;
}

export interface UptimeSummary {
  hours: number;
  targets: {
    target_url: string;
    checks: number;
    up: number;
    down: number;
    uptime_pct: number;
    avg_latency_ms: number | null;
  }[];
}

export interface AlertItem {
  id: number;
  project_id: number | null;
  kind: string;
  severity: string;
  title: string;
  detail: string | null;
  extra: Record<string, unknown> | null;
  raised_at: string;
  notified_at: string | null;
  acknowledged_at: string | null;
}

export const api = {
  findings: {
    list: (params?: FindingListParams) =>
      get<Finding[]>('/findings', params as Record<string, string | number>),
    /** Like list nhưng kèm X-Total-Count header → cho server-side pagination. */
    listWithTotal: (params?: FindingListParams) =>
      getWithTotal<Finding[]>('/findings', params as Record<string, string | number>),
    get: (id: number) => get<Finding>(`/findings/${id}`),
    explain: (id: number) => post<AnalysisResult>(`/findings/${id}/explain`),
  },
  monitor: {
    summary: (hours = 24) =>
      getRaw<UptimeSummary>(`/monitor/summary?hours=${hours}`),
    uptime: (hours = 24) =>
      getRaw<{ count: number; hours: number; items: UptimeCheck[] }>(`/monitor/uptime?hours=${hours}`),
    alerts: (params?: { only_open?: boolean; kind?: string }) => {
      const q = new URLSearchParams();
      if (params?.only_open) q.set('only_open', 'true');
      if (params?.kind) q.set('kind', params.kind);
      return getRaw<AlertItem[]>(`/monitor/alerts${q.toString() ? '?' + q : ''}`);
    },
    ack: (alertId: number) =>
      fetch(`${BASE}/monitor/alerts/${alertId}/ack`, {
        method: 'POST',
        headers: authHeaders(),
      }).then(res => {
        if (!res.ok && res.status !== 204) throw new Error(`${res.status}`);
      }),
    ping: () =>
      fetch(`${BASE}/monitor/ping`, {
        method: 'POST',
        headers: authHeaders(),
      }).then(res => res.json() as Promise<{ checks_executed: number }>),
  },
  projects: {
    list: () => get<Project[]>('/projects'),
    create: (name: string, github_url: string) =>
      post<Project>('/projects', { name, github_url }),
    delete: (id: number) =>
      fetch(`${BASE}/projects/${id}`, { method: 'DELETE', headers: authHeaders() }).then(res => {
        if (!res.ok && res.status !== 204) throw new Error(`${res.status} ${res.statusText}`);
      }),
  },
  stats: {
    overview: () => get<{
      total: number;
      critical_high: number;
      ai_analyzed: number;
      ai_analyzed_pct: number;
      by_severity: Record<string, number>;
      by_status: Record<string, number>;
      by_tool: Record<string, number>;
      open: number;
      sast_open: number;
      deps_open: number;
      sast_critical_high: number;
      deps_critical_high: number;
      dast_open?: number;
      dast_critical_high?: number;
      approved: number;
      revoked: number;
      pending: number;
    }>('/stats/overview'),
    latestScan: () => get<{
      run_id: number | null;
      run_number: number | null;
      head_branch: string | null;
      created_at: string | null;
      scanned_at: string | null;
      total: number;
      critical_high: number;
      ai_analyzed: number;
      ai_analyzed_pct: number;
      by_severity: Record<string, number>;
      by_status: Record<string, number>;
      by_tool: Record<string, number>;
    }>('/stats/latest-scan'),
    runs: (days = 30) => get<{
      days: number;
      total: number;
      pass_rate: number;
      by_conclusion: Record<string, number>;
      by_day: Record<string, Record<string, number>>;
    }>('/stats/runs', { days }),
  },
  github: {
    runs: (branch?: string) =>
      get<WorkflowRun[]>('/github/runs', branch ? { branch } : {}),
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
    me: () => get<{ username: string; role: string }>('/api/chat/auth/me'),
    command: (req: CommandRequest) =>
      post<CommandResponse>('/api/chat/command', req),
    message: (text: string, finding_id?: number) =>
      post<{ reply: string; suggested_command: string | null }>(
        '/api/chat/message',
        { text, finding_id },
      ),
    reportUrl: (params?: { project_id?: number; severity?: string }) => {
      const url = new URL(`${BASE}/api/chat/report`);
      if (params?.project_id !== undefined) url.searchParams.set('project_id', String(params.project_id));
      if (params?.severity) url.searchParams.set('severity', params.severity);
      return url.toString();
    },
  },
  config: {
    list: () => get<Record<string, Record<string, unknown>>>('/config'),
    get: (key: string) => get<Record<string, unknown>>(`/config/${key}`),
    update: (key: string, value: Record<string, unknown>) =>
      fetch(`${BASE}/config/${key}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify(value),
      }).then(async res => {
        if (!res.ok) {
          const detail = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error((detail as { detail?: string }).detail ?? `${res.status}`);
        }
        return res.json() as Promise<Record<string, unknown>>;
      }),
    integrations: () => get<{
      github: { configured: boolean; owner: string | null; repo: string | null; polling_interval_seconds: number };
      gemini: { configured: boolean; model: string };
      ci_ingest: { api_key_required: boolean; webhook_token_required: boolean };
    }>('/config/integrations'),
  },
  health: () => get<{ status: string }>('/health'),
};
