import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
import type { Finding, WorkflowArtifact, WorkflowRun } from '../types';
import { SEVERITY_ORDER } from '../types';

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

const SEV_COLOR: Record<string, string> = {
  critical: 'var(--sev-crit-fg, #e53935)',
  high:     'var(--sev-high-fg, #f57c00)',
  medium:   'var(--sev-med-fg, #f9a825)',
  low:      'var(--sev-low-fg, #43a047)',
  info:     'var(--fg-3, #888)',
};

// ── Severity board cards ──────────────────────────────────────────────────────

function SeverityBoard({ findings }: { findings: Finding[] }) {
  const counts: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
  for (const f of findings) counts[f.severity] = (counts[f.severity] ?? 0) + 1;

  const items: [string, string][] = [
    ['critical', 'Critical'],
    ['high', 'High'],
    ['medium', 'Medium'],
    ['low', 'Low'],
    ['info', 'Info'],
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 10, marginBottom: 16 }}>
      {items.map(([sev, label]) => (
        <div key={sev} className="card card-pad" style={{ borderTop: `3px solid ${SEV_COLOR[sev]}` }}>
          <div style={{ fontSize: 10.5, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: SEV_COLOR[sev], marginTop: 4 }}>
            {counts[sev]}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Tool breakdown bar chart ──────────────────────────────────────────────────

function ToolBreakdown({ findings }: { findings: Finding[] }) {
  const byTool: Record<string, Record<string, number>> = {};
  for (const f of findings) {
    if (!byTool[f.tool]) byTool[f.tool] = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
    byTool[f.tool][f.severity] = (byTool[f.tool][f.severity] ?? 0) + 1;
  }

  const tools = Object.keys(byTool).sort();
  const totals = tools.map(t => Object.values(byTool[t]).reduce((a, b) => a + b, 0));
  const maxTotal = Math.max(...totals, 1);

  if (tools.length === 0) return null;

  return (
    <div className="card card-pad" style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--fg-3)', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        Findings by Tool
      </div>
      <div style={{ display: 'grid', gap: 10 }}>
        {tools.map((tool, idx) => {
          const total = totals[idx];
          const counts = byTool[tool];
          return (
            <div key={tool}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 600 }}>{tool}</span>
                <span className="muted" style={{ fontSize: 11.5 }}>
                  {total} {total === 1 ? 'finding' : 'findings'}
                </span>
              </div>
              <div style={{ display: 'flex', height: 8, borderRadius: 4, overflow: 'hidden', background: 'var(--surface-2)' }}>
                {(['critical', 'high', 'medium', 'low', 'info'] as const).map(sev => {
                  const c = counts[sev] ?? 0;
                  if (!c) return null;
                  const pct = (c / maxTotal) * 100;
                  return (
                    <div
                      key={sev}
                      title={`${c} ${sev}`}
                      style={{ width: `${pct}%`, background: SEV_COLOR[sev], minWidth: c > 0 ? 4 : 0 }}
                    />
                  );
                })}
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 4, fontSize: 10.5, color: 'var(--fg-3)' }}>
                {(['critical', 'high', 'medium', 'low'] as const).map(sev =>
                  counts[sev] ? (
                    <span key={sev}>
                      <span style={{ color: SEV_COLOR[sev] }}>●</span> {counts[sev]} {sev}
                    </span>
                  ) : null
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Top findings list ─────────────────────────────────────────────────────────

function TopFindings({ findings }: { findings: Finding[] }) {
  const top = [...findings]
    .sort((a, b) => {
      const sevDiff = (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9);
      if (sevDiff !== 0) return sevDiff;
      return (b.cvss_score ?? 0) - (a.cvss_score ?? 0);
    })
    .slice(0, 10);

  if (top.length === 0) return null;

  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div className="card-header">
        <div className="h3">Top Findings (by severity)</div>
        <span className="muted" style={{ fontSize: 11.5 }}>{top.length} của {findings.length}</span>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 90 }}>Severity</th>
            <th>Rule</th>
            <th>Tool</th>
            <th>File</th>
            <th className="num" style={{ width: 70 }}>CVSS</th>
          </tr>
        </thead>
        <tbody>
          {top.map(f => (
            <tr key={f.id}>
              <td><span className={`chip dot sev-${f.severity}`} style={{ fontSize: 10.5 }}>{f.severity}</span></td>
              <td>
                <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>{f.rule_id}</span>
                <div className="muted" style={{ fontSize: 11, marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 380 }}>
                  {f.message.split('\n')[0]}
                </div>
              </td>
              <td><span className="tool-tag">{f.tool}</span></td>
              <td className="mono" style={{ fontSize: 11, color: 'var(--fg-3)' }}>
                {f.file_path.split('/').pop()}{f.line_number ? `:${f.line_number}` : ''}
              </td>
              <td className="num">
                {f.cvss_score != null && (
                  <span className="mono" style={{
                    fontSize: 11,
                    fontWeight: 700,
                    color: f.cvss_score >= 7 ? SEV_COLOR.high : 'var(--fg-3)',
                  }}>
                    {f.cvss_score.toFixed(1)}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── RunDetail ─────────────────────────────────────────────────────────────────

function RunDetail({ run, onBack }: { run: WorkflowRun; onBack: () => void }) {
  const [artifacts, setArtifacts] = useState<WorkflowArtifact[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loadingA, setLoadingA] = useState(true);
  const [loadingF, setLoadingF] = useState(true);
  const [reprocessing, setReprocessing] = useState(false);

  const loadFindings = () => {
    setLoadingF(true);
    api.github.runFindings(run.id)
      .then(setFindings)
      .catch(() => setFindings([]))
      .finally(() => setLoadingF(false));
  };

  useEffect(() => {
    setLoadingA(true);
    api.github.artifacts(run.id)
      .then(setArtifacts)
      .catch(() => setArtifacts([]))
      .finally(() => setLoadingA(false));
    loadFindings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run.id]);

  const handleReprocess = async () => {
    if (!confirm(`Xoá findings cũ và xử lý lại run #${run.run_number}?`)) return;
    setReprocessing(true);
    try {
      await api.github.reprocessRun(run.id);
      // Backend returns 202 — poll for new findings after a short delay.
      setTimeout(loadFindings, 4000);
    } catch (e) {
      alert(`Lỗi reprocess: ${e}`);
    } finally {
      setReprocessing(false);
    }
  };

  const hasFindings = findings.length > 0;

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
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={handleReprocess} disabled={reprocessing}>
            <Icon name="refresh" size={13} /> {reprocessing ? 'Đang xử lý…' : 'Reprocess'}
          </button>
          {run.html_url && (
            <a href={run.html_url} target="_blank" rel="noreferrer" className="btn">
              <Icon name="external" size={13} /> View on GitHub
            </a>
          )}
        </div>
      </div>

      {/* Boards: only show when we have findings for this run */}
      {loadingF && <div className="empty">Đang tải kết quả scan…</div>}

      {!loadingF && !hasFindings && (
        <div className="card card-pad" style={{ marginBottom: 16 }}>
          <div className="empty" style={{ padding: '20px 0' }}>
            Chưa có finding nào được lưu cho run này. Có thể CI chưa hoàn tất hoặc webhook chưa gọi MCP Gateway.
          </div>
        </div>
      )}

      {!loadingF && hasFindings && (
        <>
          <SeverityBoard findings={findings} />
          <ToolBreakdown findings={findings} />
          <TopFindings findings={findings} />
        </>
      )}

      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-header">
          <div className="h3">Artifacts</div>
          <span className="muted" style={{ fontSize: 11.5 }}>{artifacts.length} artifacts</span>
        </div>
        {loadingA ? (
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
                const isSec = ['semgrep-report', 'codeql-report', 'dep-check-report', 'trivy-report', 'eslint-report', 'spotbugs-report'].includes(a.name)
                  || a.name.startsWith('trivy-image-scan-');
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

// ── Page ──────────────────────────────────────────────────────────────────────

export function PagePipelines() {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<WorkflowRun | null>(null);

  useEffect(() => {
    api.github.runs().then(r => { setRuns(r); setLoading(false); }).catch(() => setLoading(false));
    const id = setInterval(() => api.github.runs().then(setRuns).catch(() => {}), 30_000);
    return () => clearInterval(id);
  }, []);

  // Aggregate stats for the list view
  const stats = useMemo(() => {
    const total = runs.length;
    const passed = runs.filter(r => r.conclusion === 'success').length;
    const failed = runs.filter(r => r.conclusion === 'failure').length;
    const running = runs.filter(r => r.status === 'in_progress').length;
    return { total, passed, failed, running };
  }, [runs]);

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

      {!loading && runs.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 16 }}>
          <div className="card card-pad">
            <div style={{ fontSize: 10.5, color: 'var(--fg-3)', textTransform: 'uppercase' }}>Total</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{stats.total}</div>
          </div>
          <div className="card card-pad" style={{ borderTop: `3px solid ${SEV_COLOR.low}` }}>
            <div style={{ fontSize: 10.5, color: 'var(--fg-3)', textTransform: 'uppercase' }}>Passed</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: SEV_COLOR.low }}>{stats.passed}</div>
          </div>
          <div className="card card-pad" style={{ borderTop: `3px solid ${SEV_COLOR.critical}` }}>
            <div style={{ fontSize: 10.5, color: 'var(--fg-3)', textTransform: 'uppercase' }}>Failed</div>
            <div style={{ fontSize: 22, fontWeight: 700, color: SEV_COLOR.critical }}>{stats.failed}</div>
          </div>
          <div className="card card-pad">
            <div style={{ fontSize: 10.5, color: 'var(--fg-3)', textTransform: 'uppercase' }}>Running</div>
            <div style={{ fontSize: 22, fontWeight: 700 }}>{stats.running}</div>
          </div>
        </div>
      )}

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
