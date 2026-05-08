import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { FindingListParams } from '../api/client';
import { Badge } from '../components/Badge';
import { Icon } from '../components/Icon';
import type { Finding, Project } from '../types';

const PAGE_SIZE = 100;

function pkgMeta(f: Finding) {
  const d = f.raw_data ?? {};
  const name = (d.PkgName ?? d.pkg_name ?? d.package_name ?? d.packageName ?? d.component ?? '') as string;
  const current = (d.InstalledVersion ?? d.installed_version ?? d.current_version ?? d.version ?? '') as string;
  const fixed = (d.FixedVersion ?? d.fixed_version ?? d.fix_version ?? d.patchedVersions ?? '') as string;
  const cveId = (d.VulnerabilityID ?? d.vulnerability_id ?? '') as string
    || (f.rule_id.match(/^(CVE|GHSA|PRISMA|SNYK)-/i) ? f.rule_id : '');
  return { name, current, fixed, cveId };
}

function upgradeCmd(f: Finding): string | null {
  const { name, fixed } = pkgMeta(f);
  if (!name || !fixed) return null;
  const manifest = f.file_path.split('/').pop() ?? '';
  if (manifest.includes('package.json') || manifest.includes('package-lock')) {
    return `npm install ${name}@${fixed}`;
  }
  if (manifest.includes('requirements') || manifest.includes('Pipfile') || manifest.endsWith('.txt')) {
    return `pip install ${name}==${fixed}`;
  }
  if (manifest.endsWith('.gradle') || manifest.endsWith('pom.xml') || manifest.endsWith('.jar')) {
    return `# Update ${name} to ${fixed} in your build file`;
  }
  return `# Upgrade ${name} to ${fixed}`;
}

function SevChip({ sev }: { sev: string }) {
  return <Badge variant={sev as 'critical' | 'high' | 'medium' | 'low' | 'info'} dot>{sev}</Badge>;
}

function CveSummaryPanel({ findings }: { findings: Finding[] }) {
  const total = findings.length;
  const bySev = findings.reduce(
    (acc, f) => { acc[f.severity] = (acc[f.severity] ?? 0) + 1; return acc; },
    {} as Record<string, number>,
  );

  const pkgCounts: Record<string, number> = {};
  for (const f of findings) {
    const { name } = pkgMeta(f);
    if (name) pkgCounts[name] = (pkgCounts[name] ?? 0) + 1;
  }
  const top10 = Object.entries(pkgCounts).sort(([, a], [, b]) => b - a).slice(0, 10);

  return (
    <div style={{
      background: 'var(--bg-muted)', border: '1px solid var(--line)',
      borderRadius: 6, padding: '10px 14px', margin: '10px 12px',
    }}>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
        {total} {total === 1 ? 'vulnerability' : 'vulnerabilities'} found
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: top10.length > 0 ? 8 : 0 }}>
        {(['critical', 'high', 'medium', 'low'] as const).flatMap(sev => {
          const cnt = bySev[sev] ?? 0;
          if (cnt === 0) return [];
          return [
            <SevChip key={sev} sev={sev} />,
            <span key={`cnt-${sev}`} style={{ fontSize: 11, alignSelf: 'center', color: 'var(--fg-2)' }}>
              {cnt}
            </span>,
          ];
        })}
      </div>
      {top10.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)', marginBottom: 4 }}>Top affected packages</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {top10.map(([pkg, count]) => (
              <span key={pkg} className="chip" style={{ fontSize: 10 }} title={`${count} CVE${count > 1 ? 's' : ''}`}>
                {pkg} ({count})
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function DepDetail({ finding }: { finding: Finding }) {
  const { name, current, fixed, cveId } = pkgMeta(finding);
  const manifest = finding.file_path.split('/').pop() ?? finding.file_path;
  const cmd = upgradeCmd(finding);
  const owasp = finding.raw_data?.owasp_category as string | undefined;

  return (
    <div style={{ overflowY: 'auto', padding: '20px 28px 40px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <SevChip sev={finding.severity} />
        <span className="tool-tag">{finding.tool}</span>
        {finding.cvss_score != null && (
          <span className="chip" style={{ fontSize: 11 }}>CVSS {finding.cvss_score}</span>
        )}
      </div>
      <h2 className="h2" style={{ lineHeight: 1.4, marginBottom: 16 }}>{finding.message}</h2>

      <div className="cve-update-card">
        <div className="cve-update-header">
          <Icon name="download" size={11} /> Dependency update required
        </div>
        <div className="cve-pkg-row">
          <span className="cve-pkg-name">{name || manifest}</span>
          {current && <span className="cve-version current">{current}</span>}
          {(current || fixed) && <span className="cve-arrow">→</span>}
          {fixed
            ? <span className="cve-version fixed">{fixed}</span>
            : <span className="cve-version unknown">check latest</span>}
        </div>
        {(cveId || finding.cwe_id) && (
          <div className="cve-id-row">
            {cveId && <span className="cve-id-badge">{cveId}</span>}
            {finding.cwe_id && cveId !== finding.cwe_id && (
              <span className="cve-id-badge">{finding.cwe_id}</span>
            )}
          </div>
        )}
      </div>

      {cmd && (
        <div className="code-block" style={{ marginTop: 16 }}>
          <div className="code-block-header">
            <span>Upgrade command</span>
            <button className="btn ghost sm" onClick={() => navigator.clipboard?.writeText(cmd)}>
              <Icon name="copy" size={12} /> Copy
            </button>
          </div>
          <pre style={{ margin: 0, padding: 12, fontSize: 12 }}>{cmd}</pre>
        </div>
      )}

      <div className="card card-pad" style={{ marginTop: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          {[
            ['Manifest', finding.file_path],
            ['Tool', finding.tool],
            ['Status', finding.status],
            ['Detected', finding.normalized_at ? new Date(finding.normalized_at).toLocaleString() : null],
          ].filter(([, v]) => v).map(([k, v]) => (
            <div key={k as string}>
              <div style={{ color: 'var(--fg-3)', fontSize: 11, marginBottom: 2 }}>{k}</div>
              <div className="mono" style={{ fontSize: 12, wordBreak: 'break-all' }}>{v}</div>
            </div>
          ))}
        </div>
      </div>

      {owasp && (
        <div className="card card-pad" style={{ marginTop: 16 }}>
          <div style={{ fontSize: 11, color: 'var(--fg-3)', marginBottom: 4 }}>OWASP Top 10 2021</div>
          <div style={{ fontSize: 13, fontWeight: 500 }}>{owasp}</div>
        </div>
      )}
    </div>
  );
}

export function PageSCA() {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectFilter, setProjectFilter] = useState<number | 'all'>('all');
  const [sevFilter, setSevFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    api.projects.list().then(setProjects).catch(() => {});
  }, []);

  useEffect(() => { setPage(0); }, [projectFilter, sevFilter, search]);

  useEffect(() => {
    setLoading(true);
    const params: FindingListParams = {
      category: 'deps',
      limit: PAGE_SIZE,
      skip: page * PAGE_SIZE,
    };
    if (projectFilter !== 'all') params.project_id = projectFilter as number;
    if (sevFilter !== 'all') params.severity = sevFilter;
    if (search.trim()) params.q = search.trim();

    api.findings.listWithTotal(params)
      .then(({ data, total: t }) => {
        setFindings(data);
        setTotal(t);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [page, projectFilter, sevFilter, search]);

  const selected = findings.find(f => f.id === selectedId) ?? findings[0] ?? null;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>
      <div className="vuln-split" style={{ flex: 1, minWidth: 0 }}>

        <div className="vuln-list-pane" style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{
            padding: '14px 16px 10px', borderBottom: '1px solid var(--line)',
            display: 'flex', alignItems: 'baseline', gap: 10, flexShrink: 0,
          }}>
            <h2 className="h2" style={{ margin: 0 }}>Dependencies (SCA)</h2>
            <span className="muted" style={{ fontSize: 12 }}>{total} total</span>
          </div>

          {projects.length > 1 && (
            <div style={{ padding: '6px 12px 0', flexShrink: 0 }}>
              <select
                style={{
                  width: '100%', padding: '5px 8px', background: 'var(--bg-elev)',
                  border: '1px solid var(--line)', borderRadius: 6, fontSize: 11.5,
                }}
                value={projectFilter}
                onChange={e => setProjectFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))}
              >
                <option value="all">All projects</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}

          <div style={{ padding: '8px 12px 6px', flexShrink: 0 }}>
            <div className="search-box" style={{ width: '100%' }}>
              <Icon name="search" size={13} />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="CVE, package, file…" />
            </div>
          </div>

          <div className="filter-toolbar">
            {(['all', 'critical', 'high', 'medium', 'low'] as const).map(s => (
              <button
                key={s}
                className={`tb-pill${sevFilter === s ? ' active' : ''}`}
                onClick={() => setSevFilter(s)}
              >
                {s === 'all' ? 'All' : s[0].toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>

          {!loading && findings.length > 0 && <CveSummaryPanel findings={findings} />}

          {!loading && total > PAGE_SIZE && (
            <div style={{
              padding: '6px 14px', borderBottom: '1px solid var(--line)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              fontSize: 11, color: 'var(--fg-3)', flexShrink: 0,
            }}>
              <span>Showing <span className="mono">{page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)}</span> of <span className="mono">{total}</span></span>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn ghost sm" style={{ padding: '2px 8px', fontSize: 11 }}
                  onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0}>← Prev</button>
                <span style={{ alignSelf: 'center' }}>{page + 1} / {totalPages}</span>
                <button className="btn ghost sm" style={{ padding: '2px 8px', fontSize: 11 }}
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))} disabled={page >= totalPages - 1}>Next →</button>
              </div>
            </div>
          )}

          <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
            {loading && <div className="empty">Loading…</div>}
            {!loading && findings.length === 0 && (
              <div className="empty">{total === 0 ? 'No dependency vulnerabilities' : 'No findings match filters'}</div>
            )}
            {findings.map(f => {
              const { name, current, fixed, cveId } = pkgMeta(f);
              return (
                <div
                  key={f.id}
                  data-testid="dep-finding-row"
                  data-sev={f.severity}
                  className={`vuln-row${selectedId === f.id ? ' active' : ''}`}
                  onClick={() => setSelectedId(f.id)}
                >
                  <div className="vuln-row-title">
                    {name || f.message.split('\n')[0]}
                    {fixed && <span className="mono" style={{ fontSize: 10.5, color: 'var(--fg-3)', marginLeft: 6 }}>{current || '?'} → {fixed}</span>}
                  </div>
                  <div className="vuln-row-meta">
                    <SevChip sev={f.severity} />
                    <span className="tool-tag">{f.tool}</span>
                    {cveId && <span className="chip" style={{ fontSize: 10 }}>{cveId}</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {selected
            ? <DepDetail finding={selected} />
            : <div className="empty" style={{ marginTop: 80 }}>
                {loading ? 'Loading…' : 'Chọn một dependency để xem chi tiết'}
              </div>}
        </div>
      </div>
    </div>
  );
}
