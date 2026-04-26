import { useEffect, useState } from 'react';
import { api, getAuthToken } from '../api/client';
import { SeverityBar } from '../components/Charts';
import { Icon } from '../components/Icon';
import type { Finding, Project } from '../types';
import { SEVERITY_ORDER } from '../types';

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export function PageReports() {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | 'all'>('all');
  const [sevFilter, setSevFilter] = useState('all');
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState('');

  useEffect(() => {
    api.projects.list().then(setProjects).catch(() => {});
  }, []);

  useEffect(() => {
    const params: Parameters<typeof api.findings.list>[0] = { limit: 500 };
    if (projectId !== 'all') params.project_id = projectId as number;
    if (sevFilter !== 'all') params.severity = sevFilter;
    api.findings.list(params).then(setFindings).catch(() => {});
  }, [projectId, sevFilter]);

  const counts = findings.reduce(
    (acc, f) => { acc[f.severity] = (acc[f.severity] || 0) + 1; return acc; },
    {} as Record<string, number>
  );
  const byTool = Object.entries(
    findings.reduce((acc, f) => { acc[f.tool] = (acc[f.tool] || 0) + 1; return acc; }, {} as Record<string, number>)
  ).sort((a, b) => b[1] - a[1]);

  const topFindings = [...findings]
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9))
    .slice(0, 20);

  const handleExport = async () => {
    setDownloading(true);
    setDownloadError('');
    try {
      const token = getAuthToken();
      if (!token) {
        setDownloadError('Cần đăng nhập — vào trang Chat để login trước.');
        setDownloading(false);
        return;
      }
      const res = await fetch(api.chat.reportUrl(), {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'security-report.html';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setDownloadError(String(e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="content">
      <div className="page-header">
        <div>
          <h1 className="h1">Reports</h1>
          <div className="sub">Security posture — {findings.length} findings</div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {/* Project filter — GET /projects */}
          <select
            style={{
              padding: '6px 10px', background: 'var(--surface-2)', border: '1px solid var(--line)',
              borderRadius: 6, color: 'var(--fg)', fontSize: 12, outline: 'none',
            }}
            value={projectId}
            onChange={e => setProjectId(e.target.value === 'all' ? 'all' : Number(e.target.value))}
          >
            <option value="all">All projects</option>
            {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          {/* Severity filter — GET /findings?severity= */}
          <select
            style={{
              padding: '6px 10px', background: 'var(--surface-2)', border: '1px solid var(--line)',
              borderRadius: 6, color: 'var(--fg)', fontSize: 12, outline: 'none',
            }}
            value={sevFilter}
            onChange={e => setSevFilter(e.target.value)}
          >
            <option value="all">All severities</option>
            {['critical', 'high', 'medium', 'low', 'info'].map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          {/* Export HTML — GET /api/chat/report */}
          <button className="btn primary" onClick={handleExport} disabled={downloading}>
            <Icon name="download" /> {downloading ? 'Đang tạo…' : 'Export HTML'}
          </button>
        </div>
      </div>

      {downloadError && (
        <div style={{
          background: 'rgba(229,57,53,0.1)', border: '1px solid var(--sev-crit-fg)',
          borderRadius: 6, padding: '8px 12px', marginBottom: 16, fontSize: 12, color: 'var(--sev-crit-fg)',
        }}>
          {downloadError}
        </div>
      )}

      <div className="kpi-grid" style={{ marginBottom: 20 }}>
        {[
          { label: 'Critical', value: counts.critical || 0, cls: 'sev-critical' },
          { label: 'High', value: counts.high || 0, cls: 'sev-high' },
          { label: 'Medium', value: counts.medium || 0, cls: 'sev-medium' },
          { label: 'Low', value: counts.low || 0, cls: 'sev-low' },
        ].map(k => (
          <div key={k.label} className="kpi">
            <div className="kpi-label">{k.label}</div>
            <div className="kpi-value">{k.value}</div>
            <div style={{ marginTop: 8 }}>
              <span className={`chip ${k.cls}`}>{k.label}</span>
            </div>
          </div>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
        <div className="card">
          <div className="card-header"><div className="h3">Severity breakdown</div></div>
          <div style={{ padding: 16 }}>
            <SeverityBar counts={counts} height={10} />
            <div style={{ display: 'flex', gap: 12, marginTop: 12, fontSize: 11.5 }}>
              {[
                { k: 'critical', c: 'var(--sev-crit-fg)' },
                { k: 'high', c: 'var(--sev-high-fg)' },
                { k: 'medium', c: 'var(--sev-med-fg)' },
                { k: 'low', c: 'var(--sev-low-fg)' },
              ].map(s => (
                <span key={s.k} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: s.c }} />
                  {s.k} ({counts[s.k] || 0})
                </span>
              ))}
            </div>
          </div>
        </div>

        <div className="card">
          <div className="card-header"><div className="h3">By tool</div></div>
          <div style={{ padding: 12 }}>
            {byTool.length === 0 ? <div className="empty">No data</div> : byTool.map(([tool, n]) => (
              <div key={tool} className="bar-row">
                <div style={{ flex: '0 0 140px' }}><span className="tool-tag">{tool}</span></div>
                <div className="bar-track"><div className="bar-fill" style={{ width: `${(n / byTool[0][1]) * 100}%` }} /></div>
                <div className="bar-value">{n}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Top findings table — GET /findings with project_id + severity filters */}
      <div className="card">
        <div className="card-header">
          <div className="h3">Top findings</div>
          <span className="muted" style={{ fontSize: 11 }}>sorted by severity · {topFindings.length} shown</span>
        </div>
        {topFindings.length === 0 ? (
          <div className="empty">No findings for selected filters</div>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Tool</th>
                <th>Rule</th>
                <th>File</th>
                <th>Status</th>
                <th className="num">Found</th>
              </tr>
            </thead>
            <tbody>
              {topFindings.map(f => (
                <tr key={f.id}>
                  <td><span className={`chip dot sev-${f.severity}`}>{f.severity}</span></td>
                  <td><span className="tool-tag">{f.tool}</span></td>
                  <td className="mono" style={{ fontSize: 11, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {f.rule_id}
                  </td>
                  <td className="mono" style={{ fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {f.file_path.split('/').pop()}{f.line_number ? `:${f.line_number}` : ''}
                  </td>
                  <td>
                    <span className={`chip ${f.status === 'APPROVED' ? 'status-passed' : f.status === 'REVOKED' ? 'status-failed' : ''}`} style={{ fontSize: 10 }}>
                      {f.status}
                    </span>
                  </td>
                  <td className="num muted" style={{ fontSize: 11 }}>
                    {f.normalized_at ? timeAgo(f.normalized_at) : '—'}
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
