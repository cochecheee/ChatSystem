import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
import type { WorkflowArtifact, WorkflowRun } from '../types';

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function conclusionClass(r: WorkflowRun) {
  if (r.status === 'in_progress') return 'status-running';
  if (r.conclusion === 'success') return 'status-passed';
  if (r.conclusion === 'failure') return 'status-failed';
  return 'status-queued';
}

function conclusionLabel(r: WorkflowRun) {
  if (r.status === 'in_progress') return 'running';
  return r.conclusion ?? r.status;
}

function RunDetail({ run, onBack }: { run: WorkflowRun; onBack: () => void }) {
  const [artifacts, setArtifacts] = useState<WorkflowArtifact[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.github.artifacts(run.id)
      .then(setArtifacts)
      .catch(() => setArtifacts([]))
      .finally(() => setLoading(false));
  }, [run.id]);

  return (
    <div className="content">
      <div className="page-header">
        <div>
          <button className="btn ghost" onClick={onBack} style={{ marginBottom: 8 }}>
            <Icon name="arrow_right" size={13} style={{ transform: 'rotate(180deg)' }} /> Back
          </button>
          <h1 className="h1">{run.name} #{run.run_number}</h1>
          <div className="sub" style={{ display: 'flex', gap: 12, marginTop: 4 }}>
            <span className={`chip dot ${conclusionClass(run)}`}>{conclusionLabel(run)}</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <Icon name="branch" size={11} />{run.head_branch}
            </span>
            <span className="mono">{run.head_sha?.slice(0, 7)}</span>
            <span>{timeAgo(run.created_at)}</span>
          </div>
        </div>
        {run.html_url && (
          <a href={run.html_url} target="_blank" rel="noreferrer" className="btn">
            <Icon name="external" size={13} /> View on GitHub
          </a>
        )}
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <div className="h3">Artifacts</div>
          <span className="muted" style={{ fontSize: 11.5 }}>{artifacts.length} artifacts</span>
        </div>
        {loading ? (
          <div className="empty">Loading artifacts…</div>
        ) : artifacts.length === 0 ? (
          <div className="empty">No artifacts found</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th className="num">Size</th>
                <th>Security</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map(a => {
                const isSec = ['semgrep-report', 'codeql-report', 'dep-check-report', 'trivy-report', 'eslint-report', 'spotbugs-report'].includes(a.name);
                return (
                  <tr key={a.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className="tool-tag">{a.name}</span>
                      </div>
                    </td>
                    <td className="num mono" style={{ fontSize: 11.5, color: 'var(--fg-3)' }}>
                      {(a.size_in_bytes / 1024).toFixed(1)} KB
                    </td>
                    <td>
                      {isSec ? (
                        <span className="chip sev-high" style={{ fontSize: 10.5 }}>SAST</span>
                      ) : (
                        <span className="chip" style={{ fontSize: 10.5 }}>—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export function PagePipelines() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<WorkflowRun | null>(null);

  useEffect(() => {
    api.github.runs().then(r => { setRuns(r); setLoading(false); }).catch(() => setLoading(false));
    const id = setInterval(() => api.github.runs().then(setRuns).catch(() => {}), 30_000);
    return () => clearInterval(id);
  }, []);

  if (selected) return <RunDetail run={selected} onBack={() => setSelected(null)} />;

  return (
    <div className="content">
      <div className="page-header">
        <div>
          <h1 className="h1">Pipelines</h1>
          <div className="sub">CI/CD runs from GitHub Actions · {runs.length} recent</div>
        </div>
        <button className="btn" onClick={() => { setLoading(true); api.github.runs().then(r => { setRuns(r); setLoading(false); }).catch(() => setLoading(false)); }}>
          <Icon name="refresh" /> Refresh
        </button>
      </div>

      <div className="card">
        {loading ? (
          <div className="empty">Loading runs…</div>
        ) : runs.length === 0 ? (
          <div className="empty">No completed runs found — check GITHUB_TOKEN and repo config</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Run</th>
                <th>Branch</th>
                <th>SHA</th>
                <th className="num">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.map(r => (
                <tr key={r.id} className="row-clickable" onClick={() => setSelected(r)}>
                  <td><span className={`chip dot ${conclusionClass(r)}`}>{conclusionLabel(r)}</span></td>
                  <td>
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span className="mono" style={{ fontSize: 12 }}>#{r.run_number}</span>
                      <span className="muted" style={{ fontSize: 11 }}>{r.name}</span>
                    </div>
                  </td>
                  <td>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Icon name="branch" size={11} style={{ color: 'var(--fg-3)' }} />
                      <span className="mono" style={{ fontSize: 11.5 }}>{r.head_branch}</span>
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: 11, color: 'var(--fg-3)' }}>{r.head_sha?.slice(0, 7)}</td>
                  <td className="num muted" style={{ fontSize: 11.5 }}>{timeAgo(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
