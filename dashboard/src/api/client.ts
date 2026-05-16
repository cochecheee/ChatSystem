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

// V3.3 — global 401 handler. App registers a callback at mount time; any
// fetch that sees 401 invokes it so the LoginModal can pop up without each
// page wiring its own auth-error path.
type AuthChallengeHandler = () => void;
let _onAuthChallenge: AuthChallengeHandler | null = null;
export function setAuthChallengeHandler(fn: AuthChallengeHandler | null) {
  _onAuthChallenge = fn;
}

function handle401(status: number) {
  if (status === 401 && _onAuthChallenge) _onAuthChallenge();
}

async function get<T>(path: string, params?: Record<string, string | number>): Promise<T> {
  const url = new URL(BASE + path);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, String(v)));
  const res = await fetch(url.toString(), { headers: authHeaders() });
  if (!res.ok) {
    handle401(res.status);
    throw new Error(`${res.status} ${res.statusText}`);
  }
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
  if (!res.ok) {
    handle401(res.status);
    throw new Error(`${res.status} ${res.statusText}`);
  }
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
    handle401(res.status);
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
    triage: (params: {
      project_id?: number;
      run_id?: number;
      confidence_threshold?: number;
      dry_run?: boolean;
      limit?: number;
    }) => {
      const q = new URLSearchParams();
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) q.set(k, String(v));
      }
      return post<{
        total: number;
        classified?: number;
        classifications?: Record<string, number>;
        auto_revoked: number;
        batches?: number;
        confidence_threshold?: number;
        dry_run: boolean;
        items: {
          finding_id: number;
          classification: string;
          confidence: number;
          reason: string;
          applied: boolean;
        }[];
      }>(`/findings/triage${q.toString() ? '?' + q.toString() : ''}`);
    },
    aiSummary: (params: {
      project_id?: number;
      run_id?: number;
      force_refresh?: boolean;
    }) => {
      const q = new URLSearchParams();
      for (const [k, v] of Object.entries(params)) {
        if (v !== undefined && v !== null) q.set(k, String(v));
      }
      return get<{
        project_id: number | null;
        run_id: number | null;
        generated_at: string;
        cached: boolean;
        cache_ttl_remaining: number;
        model: string;
        overview_md: string;
        top_risks: {
          severity: 'critical' | 'high' | 'medium';
          rule_id: string;
          file_path: string;
          one_line_reason: string;
          finding_id: number;
        }[];
        recommendations_md: string;
        pipeline_health: {
          runs_total: number;
          runs_passed: number;
          pass_rate_pct: number;
          trend: 'improving' | 'stable' | 'degrading';
        };
      }>(`/findings/ai-summary${q.toString() ? '?' + q.toString() : ''}`);
    },
    gateCount: (params: { project_id?: number; run_id?: number }) => {
      const q = new URLSearchParams();
      if (params.project_id !== undefined) q.set('project_id', String(params.project_id));
      if (params.run_id !== undefined) q.set('run_id', String(params.run_id));
      return get<{
        project_id: number | null;
        run_id: number | null;
        exclude_revoked: boolean;
        critical: number;
        high: number;
        medium: number;
        low: number;
      }>(`/findings/gate-count${q.toString() ? '?' + q.toString() : ''}`);
    },
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
    listMembers: (projectId: number) =>
      get<{ username: string; role: string; created_at: string }[]>(
        `/projects/${projectId}/members`,
      ),
    addMember: (projectId: number, username: string, role: string) =>
      post<{ username: string; role: string }>(
        `/projects/${projectId}/members`,
        { username, role },
      ),
    removeMember: (projectId: number, username: string) =>
      fetch(`${BASE}/projects/${projectId}/members/${encodeURIComponent(username)}`, {
        method: 'DELETE',
        headers: authHeaders(),
      }).then(res => {
        if (!res.ok && res.status !== 204) throw new Error(`${res.status} ${res.statusText}`);
      }),
    listSuppressions: (projectId: number) =>
      get<{
        id: number;
        rule_id: string | null;
        file_glob: string | null;
        tool: string | null;
        severity_max: string | null;
        reason: string;
        created_by: string;
        created_at: string;
        expires_at: string | null;
      }[]>(`/projects/${projectId}/suppressions`),
    addSuppression: (projectId: number, body: {
      reason: string;
      rule_id?: string | null;
      file_glob?: string | null;
      tool?: string | null;
      severity_max?: string | null;
      expires_in_days?: number | null;
    }) => post<{ id: number; reason: string; expires_at: string | null }>(
      `/projects/${projectId}/suppressions`, body,
    ),
    deleteSuppression: (projectId: number, ruleId: number) =>
      fetch(`${BASE}/projects/${projectId}/suppressions/${ruleId}`, {
        method: 'DELETE',
        headers: authHeaders(),
      }).then(res => {
        if (!res.ok && res.status !== 204) throw new Error(`${res.status} ${res.statusText}`);
      }),
    create: (body: {
      name: string;
      github_url: string;
      github_owner?: string;
      github_repo?: string;
      github_token?: string;
      gemini_api_key?: string;
      gemini_model?: string;
      polling_workflow_name?: string;
      polling_branch?: string;
      active?: boolean;
    }) => post<Project>('/projects', body),
    delete: (id: number) =>
      fetch(`${BASE}/projects/${id}`, { method: 'DELETE', headers: authHeaders() }).then(res => {
        if (!res.ok && res.status !== 204) throw new Error(`${res.status} ${res.statusText}`);
      }),
  },
  stats: {
    overview: (params?: { project_id?: number }) => get<{
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
    }>('/stats/overview', params as Record<string, string | number> | undefined),
    latestScan: (params?: { project_id?: number }) => get<{
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
    }>('/stats/latest-scan', params as Record<string, string | number> | undefined),
    runs: (days = 30) => get<{
      days: number;
      total: number;
      pass_rate: number;
      by_conclusion: Record<string, number>;
      by_day: Record<string, Record<string, number>>;
    }>('/stats/runs', { days }),
  },
  github: {
    runs: (branch?: string, project_id?: number) => {
      const params: Record<string, string | number> = {};
      if (branch) params.branch = branch;
      if (project_id !== undefined) params.project_id = project_id;
      return get<WorkflowRun[]>('/github/runs', Object.keys(params).length ? params : undefined);
    },
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
