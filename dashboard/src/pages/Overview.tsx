import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { AreaTrend, Donut, Heatmap, Sparkline } from '../components/Charts';
import { Icon } from '../components/Icon';
import type { PageId } from '../components/Shell';
import type { Finding, WorkflowRun } from '../types';
import type { Project } from '../types';

interface Props {
  onNav: (id: PageId) => void;
  onOpenVuln?: (id: number) => void;
}

const TREND_28D = [12, 14, 11, 16, 18, 22, 19, 17, 21, 26, 24, 22, 25, 28, 31, 27, 24, 22, 19, 23, 26, 24, 21, 18, 16, 19, 22, 25];
const FIXED_28D = [8, 10, 7, 11, 14, 12, 15, 13, 11, 17, 18, 14, 16, 12, 19, 21, 18, 15, 12, 14, 16, 17, 19, 14, 12, 16, 18, 21];

const SPARKS = {
  new:  [3, 5, 4, 7, 6, 9, 11, 8, 10, 13, 12, 14],
  crit: [4, 5, 4, 6, 5, 7, 6, 5, 7, 6, 7, 7],
  fix:  [2, 4, 3, 5, 7, 6, 9, 8, 11, 10, 13, 15],
  pipe: [40, 42, 38, 45, 48, 44, 52, 50, 55, 53, 58, 60],
};

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

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function PageOverview({ onNav, onOpenVuln }: Props) {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [healthy, setHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    api.health().then(() => setHealthy(true)).catch(() => setHealthy(false));
    api.findings.list({ limit: 200 }).then(setFindings).catch(() => {});
    api.github.runs().then(setRuns).catch(() => {});
    api.projects.list().then(setProjects).catch(() => {});

    const id = setInterval(() => {
      api.health().then(() => setHealthy(true)).catch(() => setHealthy(false));
      api.findings.list({ limit: 200 }).then(setFindings).catch(() => {});
      api.github.runs().then(setRuns).catch(() => {});
    }, 60_000);
    return () => clearInterval(id);
  }, []);

  const counts = findings.reduce(
    (acc, f) => { acc[f.severity] = (acc[f.severity] || 0) + 1; return acc; },
    {} as Record<string, number>
  );
  const critHigh = (counts.critical || 0) + (counts.high || 0);
  const passRate = runs.length ? Math.round(runs.filter(r => r.conclusion === 'success').length / runs.length * 100) : 0;

  const recentCritHigh = findings
    .filter(f => f.severity === 'critical' || f.severity === 'high')
    .sort((a, b) => {
      if (a.severity !== b.severity) return a.severity === 'critical' ? -1 : 1;
      return b.id - a.id;
    })
    .slice(0, 5);

  const topRules = Object.entries(
    findings.reduce((acc, f) => { acc[f.rule_id] = (acc[f.rule_id] || 0) + 1; return acc; }, {} as Record<string, number>)
  ).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([rule, count]) => ({
    rule,
    count,
    sev: findings.find(f => f.rule_id === rule)?.severity ?? 'info',
  }));
  const maxRuleCount = Math.max(1, ...topRules.map(r => r.count));

  return (
    <div className="content">
      <div className="page-header">
        <div>
          <h1 className="h1">Security overview</h1>
          <div className="sub" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%', flexShrink: 0,
              background: healthy === true ? 'var(--sev-low-fg)' : healthy === false ? 'var(--sev-crit-fg)' : 'var(--fg-4)',
            }} />
            {projects.map(p => p.name).join(', ') || 'Loading…'} · auto-refresh every 60s
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn">
            <Icon name="download" /> Export
          </button>
          <button className="btn primary" onClick={() => onNav('chat')}>
            <Icon name="sparkle" /> Ask AI
          </button>
        </div>
      </div>

      <div className="kpi-grid">
        {[
          { label: 'Open findings', value: findings.length, delta: `${critHigh} critical/high`, cls: critHigh > 0 ? 'kpi-delta-up' : 'muted', spark: SPARKS.new },
          { label: 'Critical & High', value: critHigh, delta: critHigh > 0 ? 'Needs attention' : 'All clear', cls: critHigh > 0 ? 'kpi-delta-up' : 'kpi-delta-down', spark: SPARKS.crit },
          { label: 'AI analyzed', value: findings.filter(f => f.status === 'ai_analyzed').length, delta: `of ${findings.length} findings`, cls: 'muted', spark: SPARKS.fix },
          { label: 'Pipeline runs', value: runs.length, delta: `${passRate}% pass rate`, cls: passRate >= 80 ? 'kpi-delta-down' : 'kpi-delta-up', spark: SPARKS.pipe },
        ].map((k, i) => (
          <div className="kpi" key={i}>
            <div className="kpi-label">{k.label}</div>
            <div className="kpi-value">{k.value}</div>
            <div className="kpi-foot"><span className={k.cls}>{k.delta}</span></div>
            <div className="spark"><Sparkline values={k.spark} /></div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16, marginBottom: 20 }}>
        <div className="card">
          <div className="card-header">
            <div>
              <div className="h3">Findings trend</div>
              <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>Daily, last 28 days (estimated)</div>
            </div>
            <div style={{ display: 'flex', gap: 12, fontSize: 11.5 }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 10, height: 2, background: 'var(--accent)', display: 'inline-block' }} /> Introduced
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: 'var(--fg-3)' }}>
                <span style={{ width: 10, borderTop: '1.5px dashed var(--fg-4)', display: 'inline-block' }} /> Resolved
              </span>
            </div>
          </div>
          <div style={{ padding: 12 }}>
            <AreaTrend values={TREND_28D} values2={FIXED_28D} height={220} />
          </div>
        </div>

        <div className="card">
          <div className="card-header"><div className="h3">By severity</div></div>
          <div style={{ padding: 16, display: 'flex', alignItems: 'center', gap: 16 }}>
            <Donut counts={counts} size={130} />
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
              {[
                { k: 'critical', label: 'Critical', c: 'var(--sev-crit-fg)' },
                { k: 'high', label: 'High', c: 'var(--sev-high-fg)' },
                { k: 'medium', label: 'Medium', c: 'var(--sev-med-fg)' },
                { k: 'low', label: 'Low', c: 'var(--sev-low-fg)' },
              ].map(s => (
                <div key={s.k} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: s.c }} />
                  <span style={{ flex: 1 }}>{s.label}</span>
                  <span className="mono" style={{ color: 'var(--fg-3)' }}>{counts[s.k] || 0}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 16, marginBottom: 20 }}>
        <div className="card">
          <div className="card-header">
            <div className="h3">Pipeline activity</div>
            <div className="muted" style={{ fontSize: 11.5 }}>Last 4 days · hourly</div>
          </div>
          <div style={{ padding: 18 }}>
            <Heatmap rows={4} cols={24} />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, fontSize: 11, color: 'var(--fg-3)' }}>
              <span>{runs.length} runs · {passRate}% pass</span>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header">
            <div className="h3">Top rules triggered</div>
            <span className="muted" style={{ fontSize: 11.5 }}>All time</span>
          </div>
          <div style={{ padding: 12 }}>
            {topRules.length === 0 && <div className="empty">No findings yet</div>}
            {topRules.map(r => (
              <div key={r.rule} className="bar-row" title={r.rule}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flex: '0 0 220px', overflow: 'hidden' }}>
                  <span className={`sev-dot ${r.sev}`} />
                  <span className="mono" style={{ fontSize: 11, textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{r.rule}</span>
                </div>
                <div className="bar-track"><div className="bar-fill" style={{ width: `${(r.count / maxRuleCount) * 100}%` }} /></div>
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
              {runs.slice(0, 6).map(r => (
                <tr key={r.id} className="row-clickable" onClick={() => onNav('pipelines')}>
                  <td><span className={`chip dot ${statusClass(r.conclusion ?? '')}`}>{statusLabel(r)}</span></td>
                  <td className="mono">#{r.run_number}</td>
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

      <div className="card" style={{ marginTop: 20 }}>
        <div className="card-header">
          <div>
            <div className="h3">Recent critical &amp; high findings</div>
            <div className="muted" style={{ fontSize: 11.5, marginTop: 2 }}>Top priority — needs immediate attention</div>
          </div>
          <button className="btn ghost sm" onClick={() => onNav('vulns')}>
            View all <Icon name="arrow_right" size={12} />
          </button>
        </div>
        {recentCritHigh.length === 0 ? (
          <div className="empty" style={{ padding: '40px 20px' }}>
            <Icon name="shield" size={24} style={{ color: 'var(--sev-low-fg)', marginBottom: 8 }} />
            <div style={{ color: 'var(--sev-low-fg)', fontWeight: 500 }}>No critical or high findings</div>
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
              {recentCritHigh.map(f => (
                <tr key={f.id} className="row-clickable" onClick={() => { onNav('vulns'); onOpenVuln?.(f.id); }}>
                  <td><span className={`chip dot sev-${f.severity}`}>{f.severity}</span></td>
                  <td className="mono" style={{ fontSize: 11.5, maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={f.rule_id}>{f.rule_id}</td>
                  <td className="mono" style={{ fontSize: 11, color: 'var(--fg-3)' }}>
                    {f.file_path.split('/').pop()}{f.line_number ? `:${f.line_number}` : ''}
                  </td>
                  <td>
                    {f.status === 'APPROVED' && <span className="chip" style={{ background: 'rgba(67,160,71,0.15)', color: 'var(--sev-low-fg)', fontSize: 10 }}>Approved</span>}
                    {f.status === 'REVOKED'  && <span className="chip" style={{ background: 'rgba(229,57,53,0.15)', color: 'var(--sev-crit-fg)', fontSize: 10 }}>Revoked</span>}
                    {f.status === 'ai_analyzed' && <span className="chip" style={{ background: 'var(--accent-tint)', color: 'var(--accent-2)', fontSize: 10 }}>AI analyzed</span>}
                    {f.status === 'pending_review' && <span className="chip" style={{ fontSize: 10 }}>Pending</span>}
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
