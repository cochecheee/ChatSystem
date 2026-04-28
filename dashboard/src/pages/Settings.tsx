import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { AlertBanner } from '../components/AlertBanner';
import { Badge } from '../components/Badge';
import { Icon } from '../components/Icon';
import { StatusDot } from '../components/StatusDot';
import type { Project } from '../types';

function ToggleRow({ label, sub, on }: { label: string; sub: string; on: boolean }) {
  const [checked, setChecked] = useState(on);
  return (
    <div className="toggle-row">
      <div>
        <div className="tog-label">{label}</div>
        <div className="tog-sub">{sub}</div>
      </div>
      <div className={`switch${checked ? ' on' : ''}`} onClick={() => setChecked(c => !c)} />
    </div>
  );
}

function AddProjectForm({ onAdded }: { onAdded: (p: Project) => void }) {
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);

  const handleSubmit = async () => {
    if (!name.trim() || !url.trim()) { setError('Điền đầy đủ tên và GitHub URL'); return; }
    setLoading(true);
    setError('');
    try {
      const p = await api.projects.create(name.trim(), url.trim());
      onAdded(p);
      setName('');
      setUrl('');
      setOpen(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  if (!open) {
    return (
      <button className="btn ghost sm" style={{ margin: '8px 16px 12px' }} onClick={() => setOpen(true)}>
        <Icon name="plus" size={12} /> Add project
      </button>
    );
  }

  return (
    <div style={{ padding: '8px 16px 12px', display: 'flex', flexDirection: 'column', gap: 8 }}>
      <input
        style={{
          padding: '6px 10px', background: 'var(--surface-2)', border: '1px solid var(--line)',
          borderRadius: 6, color: 'var(--fg)', fontSize: 12, outline: 'none',
        }}
        placeholder="Project name"
        value={name}
        onChange={e => setName(e.target.value)}
      />
      <input
        className="mono"
        style={{
          padding: '6px 10px', background: 'var(--surface-2)', border: '1px solid var(--line)',
          borderRadius: 6, color: 'var(--fg)', fontSize: 12, outline: 'none',
        }}
        placeholder="https://github.com/owner/repo"
        value={url}
        onChange={e => setUrl(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') handleSubmit(); }}
      />
      {error && <AlertBanner type="error" message={error} onDismiss={() => setError('')} />}
      <div style={{ display: 'flex', gap: 6 }}>
        <button className="btn primary sm" onClick={handleSubmit} disabled={loading}>
          {loading ? 'Đang lưu…' : 'Save'}
        </button>
        <button className="btn ghost sm" onClick={() => { setOpen(false); setError(''); }}>Cancel</button>
      </div>
    </div>
  );
}

export function PageSettings() {
  const [health, setHealth] = useState<'ok' | 'error' | 'checking'>('checking');
  const [projects, setProjects] = useState<Project[]>([]);

  useEffect(() => {
    api.health()
      .then(() => setHealth('ok'))
      .catch(() => setHealth('error'));
    api.projects.list()
      .then(setProjects)
      .catch(() => {});
  }, []);

  const refreshHealth = () => {
    setHealth('checking');
    api.health().then(() => setHealth('ok')).catch(() => setHealth('error'));
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
      <div className="card" style={{ marginBottom: 20, padding: '12px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <StatusDot status={health === 'ok' ? 'ok' : health === 'error' ? 'error' : 'info'} />
        <div>
          <div style={{ fontSize: 13, fontWeight: 500 }}>Backend API — GET /health</div>
          <div className="muted" style={{ fontSize: 11 }}>
            {health === 'checking' ? 'Đang kiểm tra…' : health === 'ok' ? 'Connected — healthy' : 'Unreachable — kiểm tra server'}
            {' · '}<span className="mono">{import.meta.env.VITE_API_URL ?? 'http://localhost:8000'}</span>
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
            <div className="card-header"><div className="h3">SAST Tools</div></div>
            {[
              { label: 'Semgrep', sub: 'Static analysis — Java, JS/TS, Python' },
              { label: 'CodeQL', sub: 'Deep semantic analysis — Java, JS' },
              { label: 'SpotBugs', sub: 'Bytecode analysis — Java' },
              { label: 'ESLint SARIF', sub: 'Lint + security rules — JS/TS' },
              { label: 'OWASP Dep-Check', sub: 'Dependency vulnerabilities' },
              { label: 'Trivy', sub: 'Container & filesystem scan' },
            ].map(t => <ToggleRow key={t.label} label={t.label} sub={t.sub} on={true} />)}
          </div>

          <div className="card">
            <div className="card-header"><div className="h3">Security Gates</div></div>
            {[
              { label: 'Gate 1 — SARIF threshold', sub: 'Fail if critical > 0 or high > 3' },
              { label: 'Gate 2 — SonarCloud QG', sub: 'Quality gate must pass' },
              { label: 'Gate 3 — Branch protection', sub: 'Require all status checks' },
            ].map(t => <ToggleRow key={t.label} label={t.label} sub={t.sub} on={true} />)}
          </div>
        </div>

        <div>
          <div className="card" style={{ marginBottom: 20 }}>
            <div className="card-header"><div className="h3">AI Analysis</div></div>
            {[
              { label: 'Auto-analyze on webhook', sub: 'Analyze new findings automatically' },
              { label: 'Vietnamese responses', sub: 'Explanation & remediation in Vietnamese' },
              { label: 'Remediation diff', sub: 'Generate unified diff for each finding' },
            ].map(t => <ToggleRow key={t.label} label={t.label} sub={t.sub} on={true} />)}
            <div style={{ padding: '12px 16px' }}>
              <div className="tog-label" style={{ marginBottom: 4 }}>Gemini Model</div>
              <div className="tool-tag">gemini-2.5-flash</div>
            </div>
          </div>

          {/* Projects — live from GET /projects + POST /projects */}
          <div className="card" style={{ marginBottom: 20 }}>
            <div className="card-header">
              <div className="h3">Projects</div>
              <span className="muted" style={{ fontSize: 11 }}>{projects.length} registered</span>
            </div>
            {projects.length === 0 ? (
              <div className="empty" style={{ padding: '12px 16px', fontSize: 12 }}>No projects — add one below</div>
            ) : (
              projects.map(p => (
                <div key={p.id} style={{ padding: '10px 16px', borderBottom: '1px solid var(--line)', display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Icon name="github" size={14} style={{ color: 'var(--fg-3)', flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{p.name}</div>
                    <div className="mono muted" style={{ fontSize: 10.5, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {p.github_url}
                    </div>
                    {p.last_processed_run_id != null && (
                      <div className="muted" style={{ fontSize: 10.5 }}>Last run: #{p.last_processed_run_id}</div>
                    )}
                  </div>
                  <span className="chip dot status-passed" style={{ fontSize: 10 }}>active</span>
                </div>
              ))
            )}
            <AddProjectForm onAdded={p => setProjects(prev => [...prev, p])} />
          </div>

          <div className="card">
            <div className="card-header"><div className="h3">Integration</div></div>
            <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {[
                { k: 'MCP Gateway', v: import.meta.env.VITE_API_URL ?? 'http://localhost:8000', icon: 'link' },
                { k: 'GitHub Repo', v: projects[0]?.github_url?.replace('https://github.com/', '') ?? '—', icon: 'github' },
                { k: 'Webhook', v: '/webhook/pipeline-complete', icon: 'branch' },
              ].map(r => (
                <div key={r.k} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Icon name={r.icon} size={14} style={{ color: 'var(--fg-3)' }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{r.k}</div>
                    <div className="mono" style={{ fontSize: 12 }}>{r.v}</div>
                  </div>
                  <span className={`chip dot ${health === 'ok' ? 'status-passed' : 'status-failed'}`} style={{ fontSize: 10 }}>
                    {health === 'ok' ? 'active' : 'down'}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
