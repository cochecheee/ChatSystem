import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { AlertBanner } from '../components/AlertBanner';
import { Badge } from '../components/Badge';
import { Icon } from '../components/Icon';
import { ProjectMembers } from '../components/ProjectMembers';
import { ProjectSuppressions } from '../components/ProjectSuppressions';
import { StatusDot } from '../components/StatusDot';
import { useAppConfig } from '../features/config/useAppConfig';
import { useAuth } from '../features/auth/AuthContext';
import type { AiConfig, GatesConfig, SastToolsConfig } from '../features/config/useAppConfig';
import type { Project } from '../types';

interface IntegrationsInfo {
  github: {
    configured: boolean;
    owner: string | null;
    repo: string | null;
    polling_interval_seconds: number;
  };
  gemini: { configured: boolean; model: string };
  ci_ingest: { api_key_required: boolean; webhook_token_required: boolean };
}

interface ToggleRowProps {
  label: string;
  sub: string;
  on: boolean;
  onChange?: (next: boolean) => void;
  disabled?: boolean;
}

function ToggleRow({ label, sub, on, onChange, disabled }: ToggleRowProps) {
  const [checked, setChecked] = useState(on);
  // Sync khi parent thay đổi (config load xong sau mount).
  useEffect(() => {
    setChecked(on);
  }, [on]);
  const handleClick = () => {
    if (disabled) return;
    const next = !checked;
    setChecked(next);
    onChange?.(next);
  };
  return (
    <div
      className="toggle-row"
      style={disabled ? { opacity: 0.6, cursor: 'not-allowed' } : undefined}
    >
      <div>
        <div className="tog-label">{label}</div>
        <div className="tog-sub">{sub}</div>
      </div>
      <div className={`switch${checked ? ' on' : ''}`} onClick={handleClick} />
    </div>
  );
}

const SAST_TOOLS: { key: keyof SastToolsConfig; label: string; sub: string }[] = [
  { key: 'semgrep', label: 'Semgrep', sub: 'Static analysis — Java, JS/TS, Python' },
  { key: 'codeql', label: 'CodeQL', sub: 'Deep semantic analysis — Java, JS' },
  { key: 'spotbugs', label: 'SpotBugs', sub: 'Bytecode analysis — Java' },
  { key: 'eslint', label: 'ESLint SARIF', sub: 'Lint + security rules — JS/TS' },
  { key: 'dependency_check', label: 'OWASP Dep-Check', sub: 'Dependency vulnerabilities' },
  { key: 'trivy', label: 'Trivy', sub: 'Container & filesystem scan' },
];

const GATES: { key: keyof Omit<GatesConfig, 'min_cvss_score'>; label: string; sub: string }[] = [
  {
    key: 'block_on_critical',
    label: 'Block on critical',
    sub: 'Fail pipeline nếu có finding critical',
  },
  { key: 'block_on_high', label: 'Block on high', sub: 'Fail pipeline nếu có finding high' },
  {
    key: 'block_on_secrets',
    label: 'Block on secrets',
    sub: 'Fail nếu phát hiện secrets/credentials',
  },
  {
    key: 'require_ai_analysis',
    label: 'Require AI analysis',
    sub: 'Bắt buộc finding nghiêm trọng phải được AI phân tích trước khi merge',
  },
];

const AI_TOGGLES: {
  key: keyof Omit<AiConfig, 'model' | 'max_findings_per_run'>;
  label: string;
  sub: string;
}[] = [
  {
    key: 'auto_analyze_critical',
    label: 'Auto-analyze critical',
    sub: 'Tự động AI phân tích finding critical khi tạo',
  },
  {
    key: 'auto_analyze_high',
    label: 'Auto-analyze high',
    sub: 'Tự động AI phân tích finding high (tốn token nhiều hơn)',
  },
  {
    key: 'include_source_context',
    label: 'Include source context',
    sub: 'Fetch source code từ GitHub kèm vào prompt',
  },
];

function AddProjectForm({ onAdded }: { onAdded: (p: Project) => void }) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [staging, setStaging] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);

  const handleSubmit = async () => {
    if (!name.trim() || !url.trim()) {
      setError('Điền đầy đủ tên và GitHub URL');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const p = await api.projects.create({
        name: name.trim(),
        github_url: url.trim(),
        staging_url: staging.trim() || undefined,
      });
      onAdded(p);
      setName('');
      setUrl('');
      setStaging('');
      setOpen(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  if (!open) {
    return (
      <button
        className="btn ghost sm"
        style={{ margin: '8px 16px 12px' }}
        onClick={() => setOpen(true)}
      >
        <Icon name="plus" size={12} /> Add project
      </button>
    );
  }

  return (
    <div style={{ padding: '8px 16px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <input
        style={{
          padding: '6px 10px',
          background: 'var(--surface-2)',
          border: '1px solid var(--line)',
          borderRadius: 6,
          color: 'var(--fg)',
          fontSize: 12,
          outline: 'none',
        }}
        placeholder="Project name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <input
        className="mono"
        style={{
          padding: '6px 10px',
          background: 'var(--surface-2)',
          border: '1px solid var(--line)',
          borderRadius: 6,
          color: 'var(--fg)',
          fontSize: 12,
          outline: 'none',
        }}
        placeholder="https://github.com/owner/repo"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSubmit();
        }}
      />
      <input
        className="mono"
        style={{
          padding: '6px 10px',
          background: 'var(--surface-2)',
          border: '1px solid var(--line)',
          borderRadius: 6,
          color: 'var(--fg)',
          fontSize: 12,
          outline: 'none',
        }}
        placeholder="Staging URL để giám sát uptime (tuỳ chọn) — vd https://app.onrender.com/health"
        value={staging}
        onChange={(e) => setStaging(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') handleSubmit();
        }}
      />
      {error && <AlertBanner type="error" message={error} onDismiss={() => setError('')} />}
      <div style={{ display: 'flex', gap: 6 }}>
        <button className="btn primary sm" onClick={handleSubmit} disabled={loading}>
          {loading ? 'Đang lưu…' : 'Save'}
        </button>
        <button
          className="btn ghost sm"
          onClick={() => {
            setOpen(false);
            setError('');
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

// V3.7 — inline editor cho per-project uptime Monitor target (staging_url).
// Monitor loop tự ping mọi project active có staging_url → generic, không cần env.
function MonitorTargetEditor({
  project,
  onSaved,
}: {
  project: Project;
  onSaved: (stagingUrl: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(project.staging_url ?? '');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const save = async () => {
    setBusy(true);
    setErr('');
    try {
      const res = await api.projects.setMonitorTarget(project.id, val.trim());
      onSaved(res.staging_url);
      setEditing(false);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const inputStyle = {
    flex: 1,
    minWidth: 220,
    padding: '4px 8px',
    background: 'var(--surface-2)',
    border: '1px solid var(--line)',
    borderRadius: 6,
    color: 'var(--fg)',
    fontSize: 11,
    outline: 'none',
  } as const;

  if (!editing) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, paddingLeft: 24 }}>
        <Icon name="bell" size={11} style={{ color: 'var(--fg-3)', flexShrink: 0 }} />
        {project.staging_url ? (
          <span className="mono muted" style={{ fontSize: 10.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            Monitor: {project.staging_url}
          </span>
        ) : (
          <span className="muted" style={{ fontSize: 10.5 }}>Chưa giám sát uptime</span>
        )}
        <button
          className="btn ghost sm"
          style={{ padding: '2px 8px', fontSize: 10 }}
          onClick={() => {
            setVal(project.staging_url ?? '');
            setEditing(true);
          }}
        >
          {project.staging_url ? 'Sửa' : 'Thêm monitor'}
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingLeft: 24, flexWrap: 'wrap' }}>
      <input
        className="mono"
        style={inputStyle}
        placeholder="https://app.onrender.com/health (rỗng = tắt monitor)"
        value={val}
        onChange={(e) => setVal(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') save();
        }}
      />
      <button className="btn primary sm" style={{ padding: '4px 10px', fontSize: 11 }} onClick={save} disabled={busy}>
        {busy ? '…' : 'Lưu'}
      </button>
      <button className="btn ghost sm" style={{ padding: '4px 10px', fontSize: 11 }} onClick={() => setEditing(false)}>
        Huỷ
      </button>
      {err && <span style={{ color: 'var(--danger)', fontSize: 10 }}>{err}</span>}
    </div>
  );
}

export function PageSettings() {
  const [health, setHealth] = useState<'ok' | 'error' | 'checking'>('checking');
  const [projects, setProjects] = useState<Project[]>([]);
  const { config, update } = useAppConfig();
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [configError, setConfigError] = useState<string>('');

  useEffect(() => {
    api
      .health()
      .then(() => setHealth('ok'))
      .catch(() => setHealth('error'));
    api.projects
      .list()
      .then(setProjects)
      .catch(() => {});
  }, []);

  const requireAdmin = () => {
    if (!isAdmin) {
      setConfigError('Chỉ admin mới được sửa config — đăng nhập với role admin ở Chat tab.');
      return false;
    }
    return true;
  };

  const toggleTool = async (key: keyof SastToolsConfig, next: boolean) => {
    if (!requireAdmin()) return;
    try {
      const current = config.sast_tools ?? ({} as SastToolsConfig);
      await update('sast_tools', { ...current, [key]: next });
      setConfigError('');
    } catch (e) {
      setConfigError(`Lưu thất bại: ${e}`);
    }
  };

  const toggleGate = async (key: keyof GatesConfig, next: boolean) => {
    if (!requireAdmin()) return;
    try {
      const current = config.gates ?? ({} as GatesConfig);
      await update('gates', { ...current, [key]: next });
      setConfigError('');
    } catch (e) {
      setConfigError(`Lưu thất bại: ${e}`);
    }
  };

  const toggleAi = async (key: keyof AiConfig, next: boolean) => {
    if (!requireAdmin()) return;
    try {
      const current = config.ai ?? ({} as AiConfig);
      await update('ai', { ...current, [key]: next });
      setConfigError('');
    } catch (e) {
      setConfigError(`Lưu thất bại: ${e}`);
    }
  };

  const handleDeleteProject = async (id: number, name: string) => {
    if (!confirm(`Xoá project "${name}"? Tất cả artifacts và findings sẽ mất.`)) return;
    try {
      await api.projects.delete(id);
      setProjects((prev) => prev.filter((p) => p.id !== id));
    } catch (e) {
      setConfigError(`Xoá thất bại: ${e}`);
    }
  };

  const [integrations, setIntegrations] = useState<IntegrationsInfo | null>(null);
  useEffect(() => {
    api.config
      .integrations()
      .then(setIntegrations)
      .catch(() => {});
  }, []);

  const refreshHealth = () => {
    setHealth('checking');
    api
      .health()
      .then(() => setHealth('ok'))
      .catch(() => setHealth('error'));
  };

  return (
    <div className="content">
      <div className="page-header">
        <div>
          <h1 className="h1">Settings</h1>
          <div className="sub">Cấu hình scan policies, notifications và integrations</div>
        </div>
        <button className="btn ghost sm" onClick={refreshHealth}>
          <Icon name="refresh" size={13} /> Refresh
        </button>
      </div>

      {/* Backend health banner */}
      <div
        className="card"
        style={{
          marginBottom: 20,
          padding: '12px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <StatusDot status={health === 'ok' ? 'ok' : health === 'error' ? 'error' : 'info'} />
        <div>
          <div style={{ fontSize: 13, fontWeight: 500 }}>Backend API — GET /health</div>
          <div className="muted" style={{ fontSize: 11 }}>
            {health === 'checking'
              ? 'Đang kiểm tra…'
              : health === 'ok'
                ? 'Connected — healthy'
                : 'Unreachable — kiểm tra server'}
            {' · '}
            <span className="mono">{import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}</span>
          </div>
        </div>
        <span style={{ marginLeft: 'auto' }}>
          <Badge variant={health === 'ok' ? 'passed' : health === 'error' ? 'failed' : 'running'}>
            {health}
          </Badge>
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div>
          <div className="card" style={{ marginBottom: 20 }}>
            <div className="card-header">
              <div className="h3">SAST Tools</div>
              {!isAdmin && (
                <span className="muted" style={{ fontSize: 11 }}>
                  read-only · admin login required
                </span>
              )}
            </div>
            {configError && (
              <div style={{ padding: '0 16px 8px' }}>
                <AlertBanner
                  type="error"
                  message={configError}
                  onDismiss={() => setConfigError('')}
                />
              </div>
            )}
            {SAST_TOOLS.map((t) => (
              <ToggleRow
                key={t.key}
                label={t.label}
                sub={t.sub}
                on={config.sast_tools?.[t.key] ?? true}
                onChange={(next) => toggleTool(t.key, next)}
                disabled={!isAdmin}
              />
            ))}
          </div>

          <div className="card">
            <div className="card-header">
              <div className="h3">Security Gates</div>
              {!isAdmin && (
                <span className="muted" style={{ fontSize: 11 }}>
                  read-only
                </span>
              )}
            </div>
            {GATES.map((g) => (
              <ToggleRow
                key={g.key}
                label={g.label}
                sub={g.sub}
                on={config.gates?.[g.key] ?? false}
                onChange={(next) => toggleGate(g.key, next)}
                disabled={!isAdmin}
              />
            ))}
            <div style={{ padding: '12px 16px', borderTop: '1px solid var(--line)' }}>
              <div className="tog-label" style={{ marginBottom: 4 }}>
                Min CVSS score gate
              </div>
              <input
                type="number"
                min={0}
                max={10}
                step={0.1}
                disabled={!isAdmin}
                value={config.gates?.min_cvss_score ?? 7.0}
                onChange={async (e) => {
                  if (!requireAdmin()) return;
                  const v = parseFloat(e.target.value);
                  if (isNaN(v)) return;
                  try {
                    const current = config.gates ?? ({} as GatesConfig);
                    await update('gates', { ...current, min_cvss_score: v });
                  } catch (err) {
                    setConfigError(`Lưu thất bại: ${err}`);
                  }
                }}
                style={{
                  width: 80,
                  padding: '4px 8px',
                  background: 'var(--surface-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 4,
                  color: 'var(--fg)',
                  fontSize: 12,
                  outline: 'none',
                  fontFamily: 'inherit',
                }}
              />
              <span className="muted" style={{ fontSize: 11, marginLeft: 8 }}>
                fail nếu CVSS ≥ giá trị này
              </span>
            </div>
          </div>
        </div>

        <div>
          <div className="card" style={{ marginBottom: 20 }}>
            <div className="card-header">
              <div className="h3">AI Analysis</div>
              {!isAdmin && (
                <span className="muted" style={{ fontSize: 11 }}>
                  read-only
                </span>
              )}
            </div>
            {AI_TOGGLES.map((t) => (
              <ToggleRow
                key={t.key}
                label={t.label}
                sub={t.sub}
                on={config.ai?.[t.key] ?? false}
                onChange={(next) => toggleAi(t.key, next)}
                disabled={!isAdmin}
              />
            ))}
            <div style={{ padding: '12px 16px', borderTop: '1px solid var(--line)' }}>
              <div className="tog-label" style={{ marginBottom: 4 }}>
                Gemini Model
              </div>
              <div className="tool-tag">{config.ai?.model ?? 'gemini-3.1-pro-preview'}</div>
              <div className="muted" style={{ fontSize: 11, marginTop: 6 }}>
                Cấu hình qua env <span className="mono">GEMINI_MODEL</span>
              </div>
            </div>
            <div style={{ padding: '0 16px 12px' }}>
              <div className="tog-label" style={{ marginBottom: 4 }}>
                Max findings per run
              </div>
              <input
                type="number"
                min={1}
                max={500}
                disabled={!isAdmin}
                value={config.ai?.max_findings_per_run ?? 50}
                onChange={async (e) => {
                  if (!requireAdmin()) return;
                  const v = parseInt(e.target.value, 10);
                  if (isNaN(v)) return;
                  try {
                    const current = config.ai ?? ({} as AiConfig);
                    await update('ai', { ...current, max_findings_per_run: v });
                  } catch (err) {
                    setConfigError(`Lưu thất bại: ${err}`);
                  }
                }}
                style={{
                  width: 80,
                  padding: '4px 8px',
                  background: 'var(--surface-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 4,
                  color: 'var(--fg)',
                  fontSize: 12,
                  outline: 'none',
                  fontFamily: 'inherit',
                }}
              />
            </div>
          </div>

          {/* Projects — live from GET /projects + POST /projects */}
          <div className="card" style={{ marginBottom: 20 }}>
            <div className="card-header">
              <div className="h3">Projects</div>
              <span className="muted" style={{ fontSize: 11 }}>
                {projects.length} registered
              </span>
            </div>
            {projects.length === 0 ? (
              <div className="empty" style={{ padding: '12px 16px', fontSize: 12 }}>
                No projects — add one below
              </div>
            ) : (
              projects.map((p) => (
                <div
                  key={p.id}
                  style={{
                    padding: '10px 16px',
                    borderBottom: '1px solid var(--line)',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 6,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <Icon name="github" size={14} style={{ color: 'var(--fg-3)', flexShrink: 0 }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 500 }}>{p.name}</div>
                      <div
                        className="mono muted"
                        style={{
                          fontSize: 10.5,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {p.github_url}
                      </div>
                      {p.last_processed_run_id != null && (
                        <div className="muted" style={{ fontSize: 10.5 }}>
                          Last run: #{p.last_processed_run_id}
                        </div>
                      )}
                    </div>
                    <span className="chip dot status-passed" style={{ fontSize: 10 }}>
                      active
                    </span>
                    <ProjectMembers projectId={p.id} />
                    <ProjectSuppressions projectId={p.id} />
                    <button
                      className="btn ghost sm"
                      style={{ padding: '4px 8px', fontSize: 11 }}
                      onClick={() => handleDeleteProject(p.id, p.name)}
                      title="Xoá project (cascade artifacts/findings)"
                    >
                      <Icon name="trash" size={12} />
                    </button>
                  </div>
                  <MonitorTargetEditor
                    project={p}
                    onSaved={(stagingUrl) =>
                      setProjects((prev) =>
                        prev.map((x) => (x.id === p.id ? { ...x, staging_url: stagingUrl } : x))
                      )
                    }
                  />
                </div>
              ))
            )}
            <AddProjectForm onAdded={(p) => setProjects((prev) => [...prev, p])} />
          </div>

          <div className="card">
            <div className="card-header">
              <div className="h3">Integrations</div>
            </div>
            <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {/* MCP Gateway */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Icon name="link" size={14} style={{ color: 'var(--fg-3)' }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>MCP Gateway</div>
                  <div className="mono" style={{ fontSize: 12 }}>
                    {import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}
                  </div>
                </div>
                <span
                  className={`chip dot ${health === 'ok' ? 'status-passed' : 'status-failed'}`}
                  style={{ fontSize: 10 }}
                >
                  {health === 'ok' ? 'active' : 'down'}
                </span>
              </div>
              {/* GitHub */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Icon name="github" size={14} style={{ color: 'var(--fg-3)' }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>GitHub</div>
                  <div className="mono" style={{ fontSize: 12 }}>
                    {integrations?.github.configured
                      ? `${integrations.github.owner}/${integrations.github.repo} · poll ${integrations.github.polling_interval_seconds}s`
                      : 'not configured'}
                  </div>
                </div>
                <span
                  className={`chip dot ${integrations?.github.configured ? 'status-passed' : 'status-failed'}`}
                  style={{ fontSize: 10 }}
                >
                  {integrations?.github.configured ? 'active' : 'missing'}
                </span>
              </div>
              {/* Gemini */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Icon name="brain" size={14} style={{ color: 'var(--fg-3)' }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>Gemini AI</div>
                  <div className="mono" style={{ fontSize: 12 }}>
                    {integrations?.gemini.configured ? integrations.gemini.model : 'no API key'}
                  </div>
                </div>
                <span
                  className={`chip dot ${integrations?.gemini.configured ? 'status-passed' : 'status-failed'}`}
                  style={{ fontSize: 10 }}
                >
                  {integrations?.gemini.configured ? 'active' : 'missing'}
                </span>
              </div>
              {/* CI ingest */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Icon name="branch" size={14} style={{ color: 'var(--fg-3)' }} />
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>
                    CI Ingest (webhook + artifact)
                  </div>
                  <div className="mono" style={{ fontSize: 12 }}>
                    {integrations
                      ? `webhook auth: ${integrations.ci_ingest.webhook_token_required ? 'on' : 'off'} · api-key: ${integrations.ci_ingest.api_key_required ? 'on' : 'off'}`
                      : '—'}
                  </div>
                </div>
                <span className="chip dot status-info" style={{ fontSize: 10 }}>
                  configured
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
