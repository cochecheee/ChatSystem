import { Icon } from '../components/Icon';

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

import { useState } from 'react';

export function PageSettings() {
  return (
    <div className="content">
      <div className="page-header">
        <div>
          <h1 className="h1">Settings</h1>
          <div className="sub">Cấu hình scan policies, notifications và integrations</div>
        </div>
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

          <div className="card">
            <div className="card-header"><div className="h3">Integration</div></div>
            <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
              {[
                { k: 'MCP Gateway', v: import.meta.env.VITE_API_URL ?? 'http://localhost:8000', icon: 'link' },
                { k: 'GitHub Repo', v: 'cochecheee/SAST_CICD', icon: 'github' },
                { k: 'Webhook', v: '/webhook/pipeline-complete', icon: 'branch' },
              ].map(r => (
                <div key={r.k} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <Icon name={r.icon} size={14} style={{ color: 'var(--fg-3)' }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{r.k}</div>
                    <div className="mono" style={{ fontSize: 12 }}>{r.v}</div>
                  </div>
                  <span className="chip dot status-passed" style={{ fontSize: 10 }}>active</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
