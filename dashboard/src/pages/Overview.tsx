import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { POLL_INTERVAL_MS } from '../lib/constants';
import { timeAgo } from '../lib/dateUtils';
import { Donut } from '../components/Charts';
import { OverviewAiSummary } from '../components/OverviewAiSummary';
import { DedupSummary } from '../components/DedupSummary';
import { Icon } from '../components/Icon';
import type { PageId } from '../components/Shell';
import { useActiveProjectParam } from '../contexts/ProjectContext';
import { useRuns } from '../features/pipelines/useRuns';
import { usePolling } from '../hooks/usePolling';
import type { CategoryStats, Finding, WorkflowRun } from '../types';
import type { Project } from '../types';
import { OWASP_LABELS } from '../types';

interface Props {
  onNav: (id: PageId) => void;
  onOpenVuln?: (id: number) => void;
}

// V3.2 BUG-2 — KPI cards used to render hard-coded sparkline arrays which
// looked like real history to a defense viewer. Drop them: cards now show
// numbers only. The trend panel (Findings trend) is removed entirely below
// because /stats has no per-day series; we'd need a new endpoint to bring
// it back honestly.

function statusClass(s: string) {
  if (s === 'success') return 'status-passed';
  if (s === 'failure') return 'status-failed';
  if (!s || s === 'in_progress') return 'status-running';
  return 'status-queued';
}

function statusLabel(run: WorkflowRun) {
  if (run.status === 'in_progress') return 'running';
  return run.conclusion ?? run.status;
}


export function PageOverview({ onNav, onOpenVuln }: Props) {
  const { runs } = useRuns(undefined, POLL_INTERVAL_MS);
  const [projects, setProjects] = useState<Project[]>([]);
  const [healthy, setHealthy] = useState<boolean | null>(null);

  // Latest scan stats từ BE — pick run mới nhất CÓ findings trong DB (không phải latest GitHub run).
  const [latestStats, setLatestStats] = useState<{
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
  } | null>(null);
  const [latestFindings, setLatestFindings] = useState<Finding[]>([]);
  const [loadingFindings, setLoadingFindings] = useState(false);
  const [overviewStats, setOverviewStats] =
    useState<Awaited<ReturnType<typeof api.stats.overview>> | null>(null);
  const [catStats, setCatStats] = useState<CategoryStats | null>(null);

  const { project_id } = useActiveProjectParam();
  const allProjects = project_id === undefined;

  // 1 project → KPI/donut lấy theo LẦN QUÉT MỚI NHẤT (1 run). Poll 15s.
  useEffect(() => {
    if (project_id === undefined) {
      setLatestStats(null);
      return;
    }
    const fetch = () => {
      api.stats
        .latestScan({ project_id })
        .then(setLatestStats)
        .catch(() => {});
    };
    fetch();
    const id = setInterval(fetch, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [project_id]);

  // All projects → KPI/donut lấy từ /stats/overview (current-state = run mới
  // nhất MỖI project), khớp với thẻ AI và các trang Vulns/SCA/DAST. Tránh lệch
  // "board (1 run) vs list (mọi project)" khi xem tổng nhiều dự án.
  useEffect(() => {
    if (project_id !== undefined) {
      setOverviewStats(null);
      return;
    }
    const fetch = () => {
      api.stats
        .overview()
        .then(setOverviewStats)
        .catch(() => {});
    };
    fetch();
    const id = setInterval(fetch, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [project_id]);

  // V4.4 — OWASP-class distribution (single project or scoped all-projects).
  useEffect(() => {
    const fetchCat = () => {
      api.findings
        .categoryStats({ project_id })
        .then(setCatStats)
        .catch(() => {});
    };
    fetchCat();
    const id = setInterval(fetchCat, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [project_id]);

  // Findings cho Recent crit/high + Top rules.
  //  - 1 project: theo run mới nhất (run_id của latest-scan).
  //  - All projects: gộp run mới nhất MỖI project (khớp KPI overview + lists).
  useEffect(() => {
    if (project_id === undefined) {
      setLoadingFindings(true);
      api.findings
        .list({ latest_run_only: true, exclude_revoked: true, limit: 1000 })
        .then((f) => {
          setLatestFindings(f);
          setLoadingFindings(false);
        })
        .catch(() => setLoadingFindings(false));
      return;
    }
    if (!latestStats?.run_id) {
      setLatestFindings([]);
      return;
    }
    setLoadingFindings(true);
    api.github
      .runFindings(latestStats.run_id, true) // exclude REVOKED — đã triage thì không hiện lại
      .then((f) => {
        setLatestFindings(f);
        setLoadingFindings(false);
      })
      .catch(() => setLoadingFindings(false));
  }, [project_id, latestStats?.run_id]);

  usePolling(() => {
    api
      .health()
      .then(() => setHealthy(true))
      .catch(() => setHealthy(false));
  }, POLL_INTERVAL_MS);

  useEffect(() => {
    api.projects
      .list()
      .then(setProjects)
      .catch(() => {});
  }, []);

  // KPI source: latest-scan (1 run) khi chọn 1 project; overview
  // (per-project-latest, active = total − revoked) khi xem All projects — để
  // KPI/donut khớp thẻ AI và các trang Vulns/SCA/DAST.
  const counts = allProjects
    ? (overviewStats?.by_severity ?? {})
    : (latestStats?.by_severity ?? {});
  const total = allProjects
    ? overviewStats
      ? overviewStats.total - overviewStats.revoked
      : 0
    : (latestStats?.total ?? 0);
  const critHigh = allProjects
    ? (overviewStats?.critical_high ?? 0)
    : (latestStats?.critical_high ?? 0);
  const aiAnalyzed = allProjects
    ? (overviewStats?.ai_analyzed ?? 0)
    : (latestStats?.ai_analyzed ?? 0);
  const aiAnalyzedPct = allProjects
    ? (overviewStats?.ai_analyzed_pct ?? 0)
    : (latestStats?.ai_analyzed_pct ?? 0);
  const passRate = runs.length
    ? Math.round((runs.filter((r) => r.conclusion === 'success').length / runs.length) * 100)
    : 0;

  const recentCritHigh = latestFindings
    .filter((f) => (f.severity === 'critical' || f.severity === 'high') && f.status !== 'REVOKED')
    .sort((a, b) => {
      if (a.severity !== b.severity) return a.severity === 'critical' ? -1 : 1;
      return b.id - a.id;
    })
    .slice(0, 5);

  const topRules = Object.entries(
    latestFindings.reduce(
      (acc, f) => {
        acc[f.rule_id] = (acc[f.rule_id] || 0) + 1;
        return acc;
      },
      {} as Record<string, number>
    )
  )
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([rule, count]) => ({
      rule,
      count,
      sev: latestFindings.find((f) => f.rule_id === rule)?.severity ?? 'info',
    }));
  const maxRuleCount = Math.max(1, ...topRules.map((r) => r.count));

  return (
    <div className="content">
      <div className="page-header">
        <div>
          <h1 className="h1">Security overview</h1>
          <div className="sub" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span
              style={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                flexShrink: 0,
                background:
                  healthy === true
                    ? 'var(--sev-low-fg)'
                    : healthy === false
                      ? 'var(--sev-crit-fg)'
                      : 'var(--fg-4)',
              }}
            />
            {projects.length > 0 ? projects.map((p) => p.name).join(', ') : 'No projects connected'}
            {!allProjects && latestStats?.run_id && (
              <>
                <span className="muted">·</span>
                <span>
                  Latest scan:{' '}
                  {latestStats.run_number ? (
                    <>
                      <span className="mono">#{latestStats.run_number}</span>
                      {latestStats.head_branch && (
                        <>
                          {' '}
                          on <span className="mono">{latestStats.head_branch}</span>
                        </>
                      )}
                      {latestStats.created_at && <> ({timeAgo(latestStats.created_at)})</>}
                    </>
                  ) : latestStats.scanned_at ? (
                    <>
                      <span className="mono">run {latestStats.run_id}</span> (
                      {timeAgo(latestStats.scanned_at)})
                    </>
                  ) : (
                    <span className="mono">run {latestStats.run_id}</span>
                  )}
                </span>
              </>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn" onClick={() => onNav('reports')}>
            <Icon name="download" /> Export
          </button>
          <button className="btn primary" onClick={() => onNav('chat')}>
            <Icon name="sparkle" /> Ask AI
          </button>
        </div>
      </div>

      <OverviewAiSummary projectId={project_id} onOpenFinding={onOpenVuln} />

      <DedupSummary projectId={project_id} onOpenFinding={onOpenVuln} />

      <div className="kpi-grid">
        {[
          {
            label: allProjects ? 'Findings (current state)' : 'Findings (latest scan)',
            value: loadingFindings ? '…' : total,
            delta: `${critHigh} critical/high`,
            cls: critHigh > 0 ? 'kpi-delta-up' : 'muted',
          },
          {
            label: 'Critical & High',
            value: critHigh,
            delta: critHigh > 0 ? 'Needs attention' : 'All clear',
            cls: critHigh > 0 ? 'kpi-delta-up' : 'kpi-delta-down',
          },
          {
            label: 'AI analyzed',
            value: aiAnalyzed,
            delta: total > 0 ? `${aiAnalyzedPct}% of ${total}` : '—',
            cls: 'muted',
          },
          {
            label: 'Pipeline runs',
            value: runs.length,
            delta: `${passRate}% pass rate`,
            cls: passRate >= 80 ? 'kpi-delta-down' : 'kpi-delta-up',
          },
        ].map((k, i) => (
          <div className="kpi" key={i}>
            <div className="kpi-label">{k.label}</div>
            <div className="kpi-value">{k.value}</div>
            <div className="kpi-foot">
              <span className={k.cls}>{k.delta}</span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16, marginBottom: 20 }}>
        <div className="card">
          <div className="card-header">
            <div className="h3">By severity</div>
          </div>
          <div style={{ padding: 16, display: 'flex', alignItems: 'center', gap: 16 }}>
            <Donut counts={counts} size={130} />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { k: 'critical', label: 'Critical', c: 'var(--sev-crit-fg)' },
                { k: 'high', label: 'High', c: 'var(--sev-high-fg)' },
                { k: 'medium', label: 'Medium', c: 'var(--sev-med-fg)' },
                { k: 'low', label: 'Low', c: 'var(--sev-low-fg)' },
              ].map((s) => (
                <div
                  key={s.k}
                  style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}
                >
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: s.c }} />
                  <span style={{ flex: 1 }}>{s.label}</span>
                  <span className="mono" style={{ color: 'var(--fg-3)' }}>
                    {counts[s.k] || 0}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* V4.4 — OWASP Top-10 class distribution (bar-list; not the severity donut). */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16, marginBottom: 20 }}>
        <div className="card">
          <div className="card-header">
            <div className="h3">Theo nhóm OWASP Top 10</div>
            {catStats && (
              <span className="muted" style={{ fontSize: 11.5 }}>
                {catStats.with_class}/{catStats.total} đã phân loại
              </span>
            )}
          </div>
          <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {(() => {
              const by = catStats?.by_class ?? {};
              const entries = Object.entries(by).sort((a, b) => b[1] - a[1]);
              if (entries.length === 0)
                return (
                  <span className="muted" style={{ fontSize: 12 }}>
                    Chưa có dữ liệu phân loại — hãy quét lại để phân loại.
                  </span>
                );
              const max = Math.max(...entries.map(([, n]) => n), 1);
              return entries.map(([code, n]) => (
                <div
                  key={code}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12 }}
                >
                  <span style={{ width: 240, color: 'var(--fg-2)' }}>
                    {OWASP_LABELS[code] || code}
                  </span>
                  <div
                    style={{
                      flex: 1,
                      height: 8,
                      borderRadius: 3,
                      background: 'var(--surface-2, rgba(128,128,128,0.15))',
                    }}
                  >
                    <div
                      style={{
                        width: `${(n / max) * 100}%`,
                        height: '100%',
                        borderRadius: 3,
                        background: 'var(--accent)',
                        transition: 'width .3s',
                      }}
                    />
                  </div>
                  <span
                    className="mono"
                    style={{ color: 'var(--fg-3)', width: 32, textAlign: 'right' }}
                  >
                    {n}
                  </span>
                </div>
              ));
            })()}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 16, marginBottom: 20 }}>
        <div className="card">
          <div className="card-header">
            <div className="h3">Top rules triggered</div>
            <span className="muted" style={{ fontSize: 11.5 }}>
              All time
            </span>
          </div>
          <div style={{ padding: 12 }}>
            {topRules.length === 0 && <div className="empty">No findings yet</div>}
            {topRules.map((r) => (
              <div key={r.rule} className="bar-row" title={r.rule}>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    flex: '0 0 220px',
                    overflow: 'hidden',
                  }}
                >
                  <span className={`sev-dot ${r.sev}`} />
                  <span
                    className="mono"
                    style={{
                      fontSize: 11,
                      textOverflow: 'ellipsis',
                      overflow: 'hidden',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {r.rule}
                  </span>
                </div>
                <div className="bar-track">
                  <div
                    className="bar-fill"
                    style={{ width: `${(r.count / maxRuleCount) * 100}%` }}
                  />
                </div>
                <div className="bar-value">{r.count}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-header">
          <div className="h3">Recent pipeline runs</div>
          <button className="btn ghost sm" onClick={() => onNav('pipelines')}>
            View all <Icon name="arrow_right" size={12} />
          </button>
        </div>
        {runs.length === 0 ? (
          <div className="empty">No recent runs — check server connection</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Run #</th>
                <th>Branch</th>
                <th>SHA</th>
                <th className="num">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 6).map((r) => (
                <tr key={r.id} className="row-clickable" onClick={() => onNav('pipelines')}>
                  <td>
                    <span className={`chip dot ${statusClass(r.conclusion ?? '')}`}>
                      {statusLabel(r)}
                    </span>
                  </td>
                  <td className="mono">#{r.run_number}</td>
                  <td>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <Icon name="branch" size={11} style={{ color: 'var(--fg-3)' }} />
                      <span className="mono" style={{ fontSize: 11.5 }}>
                        {r.head_branch}
                      </span>
                    </span>
                  </td>
                  <td className="mono" style={{ fontSize: 11, color: 'var(--fg-3)' }}>
                    {r.head_sha?.slice(0, 7)}
                  </td>
                  <td className="num muted" style={{ fontSize: 11.5 }}>
                    {timeAgo(r.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">
          <div>
            <div className="h3">Recent critical &amp; high findings</div>
            <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>
              Top priority — needs immediate attention
            </div>
          </div>
          <button className="btn ghost sm" onClick={() => onNav('vulns')}>
            View all <Icon name="arrow_right" size={12} />
          </button>
        </div>
        {recentCritHigh.length === 0 ? (
          <div className="empty" style={{ padding: '40px 20px' }}>
            <Icon name="shield" size={24} style={{ color: 'var(--sev-low-fg)', marginBottom: 8 }} />
            <div style={{ color: 'var(--sev-low-fg)', fontWeight: 500 }}>
              No critical or high findings
            </div>
          </div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Rule</th>
                <th>File</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recentCritHigh.map((f) => (
                <tr
                  key={f.id}
                  className="row-clickable"
                  onClick={() => {
                    onNav('vulns');
                    onOpenVuln?.(f.id);
                  }}
                >
                  <td>
                    <span className={`chip dot sev-${f.severity}`}>{f.severity}</span>
                  </td>
                  <td
                    className="mono"
                    style={{
                      fontSize: 11.5,
                      maxWidth: 260,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                    title={f.rule_id}
                  >
                    {f.rule_id}
                  </td>
                  <td className="mono" style={{ fontSize: 11, color: 'var(--fg-3)' }}>
                    {f.file_path.split('/').pop()}
                    {f.line_number ? `:${f.line_number}` : ''}
                  </td>
                  <td>
                    {f.status === 'APPROVED' && (
                      <span
                        className="chip"
                        style={{
                          background: 'rgba(67,160,71,0.15)',
                          color: 'var(--sev-low-fg)',
                          fontSize: 10,
                        }}
                      >
                        Approved
                      </span>
                    )}
                    {f.status === 'REVOKED' && (
                      <span
                        className="chip"
                        style={{
                          background: 'rgba(229,57,53,0.15)',
                          color: 'var(--sev-crit-fg)',
                          fontSize: 10,
                        }}
                      >
                        Revoked
                      </span>
                    )}
                    {f.status === 'ai_analyzed' && (
                      <span
                        className="chip"
                        style={{
                          background: 'var(--accent-tint)',
                          color: 'var(--accent-2)',
                          fontSize: 10,
                        }}
                      >
                        AI analyzed
                      </span>
                    )}
                    {f.status === 'pending_review' && (
                      <span className="chip" style={{ fontSize: 10 }}>
                        Pending
                      </span>
                    )}
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
