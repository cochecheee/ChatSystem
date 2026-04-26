import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { SeverityBar } from '../components/Charts';
import { Icon } from '../components/Icon';
import type { Finding } from '../types';

export function PageReports() {
  const [findings, setFindings] = useState<Finding[]>([]);

  useEffect(() => {
    api.findings.list({ limit: 200 }).then(setFindings).catch(() => {});
  }, []);

  const counts = findings.reduce(
    (acc, f) => { acc[f.severity] = (acc[f.severity] || 0) + 1; return acc; },
    {} as Record<string, number>
  );
  const byTool = Object.entries(
    findings.reduce((acc, f) => { acc[f.tool] = (acc[f.tool] || 0) + 1; return acc; }, {} as Record<string, number>)
  ).sort((a, b) => b[1] - a[1]);

  return (
    <div className="content">
      <div className="page-header">
        <div>
          <h1 className="h1">Reports</h1>
          <div className="sub">Security posture summary — {findings.length} total findings</div>
        </div>
        <button className="btn">
          <Icon name="download" /> Export PDF
        </button>
      </div>

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

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
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
    </div>
  );
}
