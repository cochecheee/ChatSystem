import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import { SeverityBar } from '../components/Charts';
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

function formatDuration(run: WorkflowRun): string {
  if (!run.updated_at || !run.created_at) return '—';
  const ms = new Date(run.updated_at).getTime() - new Date(run.created_at).getTime();
  const s = Math.floor(ms / 1000);
  const m = Math.floor(s / 60);
  const h = Math.floor(m / 60);
  if (h > 0) return `${h}h ${m % 60}m`;
  return `${m}m ${s % 60}s`;
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

const SAST_NAMES = new Set([
  'semgrep-report', 'codeql-report', 'dep-check-report',
  'trivy-report', 'eslint-report', 'spotbugs-report',
]);

function isSastArtifact(name: string) {
  return SAST_NAMES.has(name) || name.startsWith('trivy-image-scan-');
}

// ── CI/CD categorisation ──────────────────────────────────────────────────────

const CD_KEYWORDS = ['cd', 'deploy', 'release', 'publish', 'staging', 'production', 'prod'];

function categorizeRun(run: WorkflowRun): 'ci' | 'cd' {
  const n = (run.name ?? '').toLowerCase();
  // Tokenize on non-alphanumeric so 'cd' matches 'CD' but not 'codeql' or 'cdn'
  const tokens = n.split(/[^a-z0-9]+/).filter(Boolean);
  for (const kw of CD_KEYWORDS) {
    if (tokens.includes(kw)) return 'cd';
  }
  // Fallback substring check for compound names like "deploy-prod"
  if (CD_KEYWORDS.some(kw => kw.length >= 4 && n.includes(kw))) return 'cd';
  return 'ci';
}

// ── Section header (sticky within scrollable sidebar) ─────────────────────────

function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <div style={{
      padding: '10px 14px 6px',
      fontSize: 'var(--ts-xs)',
      fontWeight: 700,
      color: 'var(--fg-3)',
      textTransform: 'uppercase',
      letterSpacing: '0.08em',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      borderBottom: '1px solid var(--line)',
      background: 'var(--bg-elev)',
      position: 'sticky',
      top: 0,
      zIndex: 1,
    }}>
      <span>{label}</span>
      <span style={{ fontVariantNumeric: 'tabular-nums', color: 'var(--fg-4)', fontWeight: 600 }}>{count}</span>
    </div>
  );
}

// ── Severity board cards ──────────────────────────────────────────────────────

function SeverityBoard({ findings }: { findings: Finding[] }) {
  const counts: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
  for (const f of findings) counts[f.severity] = (counts[f.severity] ?? 0) + 1;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8, marginBottom: 14 }}>
      {(['critical', 'high', 'medium', 'low', 'info'] as const).map(sev => (
        <div key={sev} className="card card-pad" style={{ borderTop: `3px solid ${SEV_COLOR[sev]}`, padding: '10px 12px' }}>
          <div style={{ fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{sev}</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: SEV_COLOR[sev], marginTop: 2 }}>
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
    <div className="card card-pad" style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 10.5, fontWeight: 600, color: 'var(--fg-3)', marginBottom: 10, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        Findings by Tool
      </div>
      <div style={{ display: 'grid', gap: 10 }}>
        {tools.map((tool, idx) => {
          const total = totals[idx];
          const counts = byTool[tool];
          return (
            <div key={tool}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                <span className="tool-tag">{tool}</span>
                <span className="muted" style={{ fontSize: 11 }}>{total}</span>
              </div>
              <div style={{ display: 'flex', height: 6, borderRadius: 3, overflow: 'hidden', background: 'var(--surface-2)' }}>
                {(['critical', 'high', 'medium', 'low', 'info'] as const).map(sev => {
                  const c = counts[sev] ?? 0;
                  if (!c) return null;
                  return (
                    <div key={sev} title={`${c} ${sev}`}
                      style={{ width: `${(c / maxTotal) * 100}%`, background: SEV_COLOR[sev], minWidth: 4 }} />
                  );
                })}
              </div>
              <div style={{ display: 'flex', gap: 6, marginTop: 3, fontSize: 10, color: 'var(--fg-3)' }}>
                {(['critical', 'high', 'medium', 'low'] as const).map(sev =>
                  counts[sev] ? (
                    <span key={sev}><span style={{ color: SEV_COLOR[sev] }}>●</span> {counts[sev]} {sev}</span>
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

// ── Top findings ──────────────────────────────────────────────────────────────

function TopFindings({ findings }: { findings: Finding[] }) {
  const top = [...findings]
    .sort((a, b) => {
      const d = (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9);
      return d !== 0 ? d : (b.cvss_score ?? 0) - (a.cvss_score ?? 0);
    })
    .slice(0, 10);

  if (top.length === 0) return null;

  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <div className="card-header">
        <div className="h3">Top Findings</div>
        <span className="muted" style={{ fontSize: 11 }}>{top.length} / {findings.length}</span>
      </div>
      <table className="table">
        <thead>
          <tr>
            <th style={{ width: 80 }}>Severity</th>
            <th>Rule</th>
            <th>Tool</th>
            <th>File</th>
            <th className="num" style={{ width: 60 }}>CVSS</th>
          </tr>
        </thead>
        <tbody>
          {top.map(f => (
            <tr key={f.id}>
              <td><span className={`chip dot sev-${f.severity}`} style={{ fontSize: 10 }}>{f.severity}</span></td>
              <td>
                <span className="mono" style={{ fontSize: 11, fontWeight: 600 }}>{f.rule_id}</span>
                <div className="muted" style={{ fontSize: 10, marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 340 }}>
                  {f.message.split('\n')[0]}
                </div>
              </td>
              <td><span className="tool-tag" style={{ fontSize: 10 }}>{f.tool}</span></td>
              <td className="mono" style={{ fontSize: 10, color: 'var(--fg-3)' }}>
                {f.file_path.split('/').pop()}{f.line_number ? `:${f.line_number}` : ''}
              </td>
              <td className="num">
                {f.cvss_score != null && (
                  <span className="mono" style={{ fontSize: 10.5, fontWeight: 700, color: f.cvss_score >= 7 ? SEV_COLOR.high : 'var(--fg-3)' }}>
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

// ── Run detail panel ──────────────────────────────────────────────────────────

function RunPanel({ run }: { run: WorkflowRun }) {
  const [artifacts, setArtifacts] = useState<WorkflowArtifact[]>([]);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loadingF, setLoadingF] = useState(true);
  const [loadingA, setLoadingA] = useState(true);
  const [reprocessing, setReprocessing] = useState(false);
  const [reprocessMsg, setReprocessMsg] = useState('');

  const loadFindings = (runId: number) => {
    setLoadingF(true);
    api.github.runFindings(runId)
      .then(setFindings)
      .catch(() => setFindings([]))
      .finally(() => setLoadingF(false));
  };

  useEffect(() => {
    setFindings([]);
    setArtifacts([]);
    setReprocessMsg('');
    loadFindings(run.id);
    setLoadingA(true);
    api.github.artifacts(run.id)
      .then(setArtifacts)
      .catch(() => setArtifacts([]))
      .finally(() => setLoadingA(false));
  }, [run.id]);

  const handleReprocess = async () => {
    if (!confirm(`Xoá findings cũ và xử lý lại run #${run.run_number}?`)) return;
    setReprocessing(true);
    setReprocessMsg('');
    try {
      const res = await api.github.reprocessRun(run.id);
      setReprocessMsg(`Đang xử lý ${res.deleted_artifacts} artifact cũ — kết quả sẽ cập nhật sau ~10s…`);
      setTimeout(() => loadFindings(run.id), 10_000);
    } catch (e) {
      setReprocessMsg(`Lỗi: ${e}`);
    } finally {
      setReprocessing(false);
    }
  };

  return (
    <div style={{ padding: '20px 24px', overflowY: 'auto', height: '100%' }}>
      {/* Run header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
        <div>
          <h2 className="h2" style={{ marginBottom: 4 }}>{run.name} <span className="muted">#{run.run_number}</span></h2>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <span className={`chip dot ${conclusionClass(run)}`} style={{ fontSize: 10.5 }}>{conclusionLabel(run)}</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12 }}>
              <Icon name="branch" size={11} style={{ color: 'var(--fg-3)' }} />{run.head_branch}
            </span>
            <span className="mono" style={{ fontSize: 11, color: 'var(--fg-3)' }}>{run.head_sha?.slice(0, 7)}</span>
            <span className="muted" style={{ fontSize: 11 }}>{timeAgo(run.created_at)}</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <button className="btn ghost sm" onClick={handleReprocess} disabled={reprocessing}>
            <Icon name="refresh" size={12} /> {reprocessing ? 'Đang xử lý…' : 'Reprocess'}
          </button>
          {run.html_url && (
            <a href={run.html_url} target="_blank" rel="noreferrer" className="btn ghost sm">
              <Icon name="external" size={12} /> GitHub
            </a>
          )}
        </div>
      </div>

      {reprocessMsg && (
        <div style={{ background: 'var(--accent-tint)', border: '1px solid var(--accent)', borderRadius: 6, padding: '8px 12px', marginBottom: 14, fontSize: 12 }}>
          {reprocessMsg}
        </div>
      )}

      {/* Boards */}
      {loadingF && <div className="empty" style={{ padding: '32px 0' }}>Đang tải kết quả scan…</div>}

      {!loadingF && findings.length === 0 && (
        <div className="card card-pad" style={{ marginBottom: 14 }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10, padding: '20px 0' }}>
            <Icon name="alert" size={22} style={{ color: 'var(--fg-4)' }} />
            <div className="muted" style={{ fontSize: 13, textAlign: 'center' }}>
              Chưa có findings cho run này.<br />
              Có thể artifacts đã hết hạn (retention-days: 1) hoặc CI chưa kích hoạt webhook.
            </div>
            <button className="btn sm" onClick={handleReprocess} disabled={reprocessing}>
              <Icon name="refresh" size={12} /> Thử Reprocess
            </button>
          </div>
        </div>
      )}

      {!loadingF && findings.length > 0 && (
        <>
          <SeverityBoard findings={findings} />
          <ToolBreakdown findings={findings} />
          <TopFindings findings={findings} />
        </>
      )}

      {/* Artifacts */}
      <div className="card">
        <div className="card-header">
          <div className="h3">Artifacts</div>
          <span className="muted" style={{ fontSize: 11 }}>{loadingA ? '…' : `${artifacts.length} total`}</span>
        </div>
        {loadingA ? (
          <div className="empty">Loading…</div>
        ) : artifacts.length === 0 ? (
          <div className="empty">No artifacts</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th className="num">Size</th>
                <th>Type</th>
              </tr>
            </thead>
            <tbody>
              {artifacts.map(a => (
                <tr key={a.id}>
                  <td><span className="tool-tag">{a.name}</span></td>
                  <td className="num mono" style={{ fontSize: 11, color: 'var(--fg-3)' }}>
                    {(a.size_in_bytes / 1024).toFixed(1)} KB
                  </td>
                  <td>
                    {isSastArtifact(a.name)
                      ? <span className="chip sev-high" style={{ fontSize: 10 }}>SAST</span>
                      : <span className="chip" style={{ fontSize: 10 }}>—</span>}
                  </td>
                </tr>
              ))}
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
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  // PIPE-02: branch filter state
  const [branch, setBranch] = useState<string>('all');

  const refresh = () => {
    setLoading(true);
    setFetchError(null);
    setRuns([]);  // clear stale list so tab activation never shows stale "No runs"
    api.github.runs()
      .then(arr => {
        setRuns(arr);
        setLoading(false);
        // Auto-select latest CI run; keep current selection if it still exists
        setSelectedId(prev => {
          if (prev != null && arr.some(r => r.id === prev)) return prev;
          const latestCi = arr.find(r => categorizeRun(r) === 'ci');
          const latestCd = arr.find(r => categorizeRun(r) === 'cd');
          return latestCi?.id ?? latestCd?.id ?? arr[0]?.id ?? null;
        });
      })
      .catch(e => {
        console.error('[Pipelines] fetch error:', e);
        setFetchError(String(e));
        setLoading(false);
      });
  };

  useEffect(() => {
    // On mount (fires on every tab activation since pages remount via App.tsx switch),
    // fetch runs and auto-select latest CI run. setRuns([]) + setLoading are called only
    // in callbacks to avoid the react-hooks/set-state-in-effect lint rule.
    api.github.runs()
      .then(arr => {
        setRuns(arr);
        setLoading(false);
        setSelectedId(prev => {
          if (prev != null && arr.some(r => r.id === prev)) return prev;
          const latestCi = arr.find(r => categorizeRun(r) === 'ci');
          const latestCd = arr.find(r => categorizeRun(r) === 'cd');
          return latestCi?.id ?? latestCd?.id ?? arr[0]?.id ?? null;
        });
      })
      .catch(e => {
        console.error('[Pipelines] fetch error:', e);
        setFetchError(String(e));
        setLoading(false);
      });
    const id = setInterval(() => {
      api.github.runs()
        .then(arr => setRuns(arr))
        .catch(() => {});
    }, 30_000);
    return () => clearInterval(id);
  }, []);

  const selected = runs.find(r => r.id === selectedId) ?? null;

  const stats = useMemo(() => ({
    total: runs.length,
    passed: runs.filter(r => r.conclusion === 'success').length,
    failed: runs.filter(r => r.conclusion === 'failure').length,
    running: runs.filter(r => r.status === 'in_progress').length,
  }), [runs]);

  const branchOptions = useMemo(
    () => [...new Set(runs.map(r => r.head_branch))].sort(),
    [runs],
  );

  const filteredRuns = useMemo(() => {
    if (branch === 'all') return runs;
    return runs.filter(r => r.head_branch === branch);
  }, [runs, branch]);

  // Split runs into CI and CD buckets (from filteredRuns for PIPE-02)
  const { ciRuns, cdRuns } = useMemo(() => {
    const ci: WorkflowRun[] = [];
    const cd: WorkflowRun[] = [];
    for (const r of filteredRuns) {
      (categorizeRun(r) === 'cd' ? cd : ci).push(r);
    }
    return { ciRuns: ci, cdRuns: cd };
  }, [filteredRuns]);

  // Inline run-row renderer used in both CI and CD sections
  const renderRunRow = (r: WorkflowRun, isLatest: boolean) => (
    <div
      key={r.id}
      className={`vuln-row${r.id === selectedId ? ' active' : ''}`}
      style={{ cursor: 'pointer', padding: '10px 14px' }}
      onClick={() => setSelectedId(r.id)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
        <span className={`chip dot ${conclusionClass(r)}`} style={{ fontSize: 10 }}>{conclusionLabel(r)}</span>
        <span className="mono" style={{ fontSize: 11.5, fontWeight: 600 }}>#{r.run_number}</span>
        {isLatest && (
          <span className="chip" style={{ fontSize: 9.5, marginLeft: 'auto' }}>latest</span>
        )}
      </div>
      <div className="muted" style={{ fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {r.name}
      </div>
      <div style={{ display: 'flex', gap: 8, marginTop: 3, fontSize: 10.5, color: 'var(--fg-3)' }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <Icon name="branch" size={10} />{r.head_branch}
        </span>
        <span>{timeAgo(r.created_at)}</span>
      </div>
      {r.id === selectedId && (
        <>
          <div style={{ borderTop: '1px solid var(--line)', margin: '6px 0' }} />
          <SeverityBar counts={{ critical: 0, high: 0, medium: 0, low: 0 }} height={4} />
          <div style={{
            display: 'flex', gap: 8, marginTop: 4,
            fontSize: 'var(--ts-xs)', color: 'var(--fg-3)', alignItems: 'center'
          }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <Icon name="clock" size={10} />
              <span className="mono">{formatDuration(r)}</span>
            </span>
          </div>
        </>
      )}
    </div>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 52px)', overflow: 'hidden' }}>
      {/* Header + KPI row */}
      <div style={{ padding: '16px 24px 12px', flexShrink: 0, borderBottom: '1px solid var(--line)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <div>
            <h1 className="h1">Pipelines</h1>
            <div className="sub">
              GitHub Actions ·{' '}
              {branch === 'all'
                ? `${runs.length} recent runs`
                : `${filteredRuns.length} of ${runs.length} runs`}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Icon name="branch" size={11} style={{ color: 'var(--fg-3)' }} />
              <select
                className="filter-toolbar select"
                style={{ maxWidth: 140 }}
                value={branch}
                onChange={e => setBranch(e.target.value)}
              >
                <option value="all">All branches</option>
                {branchOptions.map(b => <option key={b} value={b}>{b}</option>)}
              </select>
            </div>
            <button className="btn ghost sm" onClick={refresh}>
              <Icon name="refresh" size={13} /> Refresh
            </button>
          </div>
        </div>

        {!loading && runs.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
            <div className="card card-pad" style={{ padding: '8px 12px' }}>
              <div style={{ fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase' }}>Total</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{stats.total}</div>
            </div>
            <div className="card card-pad" style={{ padding: '8px 12px', borderTop: `2px solid ${SEV_COLOR.low}` }}>
              <div style={{ fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase' }}>Passed</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: SEV_COLOR.low }}>{stats.passed}</div>
            </div>
            <div className="card card-pad" style={{ padding: '8px 12px', borderTop: `2px solid ${SEV_COLOR.critical}` }}>
              <div style={{ fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase' }}>Failed</div>
              <div style={{ fontSize: 18, fontWeight: 600, color: SEV_COLOR.critical }}>{stats.failed}</div>
            </div>
            <div className="card card-pad" style={{ padding: '8px 12px' }}>
              <div style={{ fontSize: 10, color: 'var(--fg-3)', textTransform: 'uppercase' }}>Running</div>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{stats.running}</div>
            </div>
          </div>
        )}
      </div>

      {/* Split: left = run list, right = detail panel */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>

        {/* Left: run list split into CI / CD sections */}
        <div style={{ width: 280, flexShrink: 0, borderRight: '1px solid var(--line)', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
          {loading && <div className="empty">Loading runs…</div>}
          {!loading && fetchError && (
            <div className="empty" style={{ color: 'var(--err-fg)', padding: 12, fontSize: 11, wordBreak: 'break-all' }}>
              Error: {fetchError}
            </div>
          )}
          {!loading && !fetchError && runs.length === 0 && (
            <div className="empty" style={{ fontSize: 12 }}>No runs — check GITHUB_TOKEN</div>
          )}

          {!loading && !fetchError && runs.length > 0 && (
            <>
              <SectionHeader label="CI" count={ciRuns.length} />
              {ciRuns.length === 0
                ? <div className="empty" style={{ padding: '8px 12px', fontSize: 11 }}>No CI runs</div>
                : ciRuns.map((r, idx) => renderRunRow(r, idx === 0))}

              <SectionHeader label="CD" count={cdRuns.length} />
              {cdRuns.length === 0
                ? <div className="empty" style={{ padding: '8px 12px', fontSize: 11 }}>No CD runs</div>
                : cdRuns.map((r, idx) => renderRunRow(r, idx === 0))}
            </>
          )}
        </div>

        {/* Right: detail panel */}
        <div style={{ flex: 1, minWidth: 0, overflowY: 'auto' }}>
          {selected ? (
            <RunPanel key={selected.id} run={selected} />
          ) : (
            <div className="empty" style={{ marginTop: 80 }}>
              {loading ? 'Đang tải…' : 'Chọn một pipeline run để xem kết quả'}
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
