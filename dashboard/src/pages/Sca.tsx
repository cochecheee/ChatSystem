import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import type { FindingListParams } from '../api/client';
import { Badge } from '../components/Badge';
import { Icon } from '../components/Icon';
import { useActiveProjectParam } from '../contexts/ProjectContext';
import { flagFalsePositive } from '../features/findings/flagFalsePositive';
import { useResizableSplit } from '../hooks/useResizableSplit';
import { pkgMeta, pickRecommendedVersion, upgradeCmd } from '../lib/cveUtils';
import type { AnalysisResult, Finding, Project } from '../types';

const SEV_RANK: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1, info: 0 };
const PAGE_SIZE = 500;

function SevChip({ sev }: { sev: string }) {
  return (
    <Badge variant={sev as 'critical' | 'high' | 'medium' | 'low' | 'info'} dot>
      {sev}
    </Badge>
  );
}

interface PackageGroup {
  key: string; // "name@current"
  name: string;
  current: string;
  recommended: string;
  manifestPath: string;
  maxSev: string;
  sevCounts: Record<string, number>;
  cves: Finding[]; // findings (one per CVE), deduped by CVE id
}

function groupByPackage(findings: Finding[]): PackageGroup[] {
  const map = new Map<string, PackageGroup>();
  for (const f of findings) {
    const { name, current, fixed, cveId } = pkgMeta(f);
    const key = name ? `${name}@${current || '?'}` : `__file:${f.file_path}`;
    let g = map.get(key);
    if (!g) {
      g = {
        key,
        name: name || f.file_path.split('/').pop() || f.file_path,
        current,
        recommended: '',
        manifestPath: f.file_path,
        maxSev: f.severity,
        sevCounts: {},
        cves: [],
      };
      map.set(key, g);
    }
    // Dedup by CVE id within the package group
    if (cveId && g.cves.some((x) => pkgMeta(x).cveId === cveId)) continue;
    g.cves.push(f);
    g.sevCounts[f.severity] = (g.sevCounts[f.severity] ?? 0) + 1;
    if ((SEV_RANK[f.severity] ?? 0) > (SEV_RANK[g.maxSev] ?? 0)) g.maxSev = f.severity;
    if (fixed) {
      const cur = g.recommended ? [g.recommended, fixed] : [fixed];
      g.recommended = pickRecommendedVersion(cur);
    }
  }
  return Array.from(map.values()).sort(
    (a, b) => (SEV_RANK[b.maxSev] ?? 0) - (SEV_RANK[a.maxSev] ?? 0) || b.cves.length - a.cves.length
  );
}

function SummaryBar({ groups }: { groups: PackageGroup[] }) {
  const totalCves = groups.reduce((n, g) => n + g.cves.length, 0);
  const sev: Record<string, number> = { critical: 0, high: 0, medium: 0, low: 0 };
  for (const g of groups)
    for (const [s, c] of Object.entries(g.sevCounts)) sev[s] = (sev[s] ?? 0) + c;
  const top = groups.slice(0, 8);
  return (
    <div
      style={{
        background: 'var(--bg-muted)',
        border: '1px solid var(--line)',
        borderRadius: 6,
        padding: '10px 14px',
        margin: '10px 12px',
      }}
    >
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 6 }}>
        {groups.length} {groups.length === 1 ? 'dependency' : 'dependencies'} affected
        <span style={{ color: 'var(--fg-3)', fontWeight: 400, marginLeft: 6 }}>
          · {totalCves} CVE{totalCves === 1 ? '' : 's'} (đã gộp)
        </span>
      </div>
      <div
        style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: top.length > 0 ? 8 : 0 }}
      >
        {(['critical', 'high', 'medium', 'low'] as const).flatMap((s) => {
          const c = sev[s] ?? 0;
          if (!c) return [];
          return [
            <SevChip key={s} sev={s} />,
            <span
              key={`c-${s}`}
              style={{ fontSize: 11, alignSelf: 'center', color: 'var(--fg-2)' }}
            >
              {c}
            </span>,
          ];
        })}
      </div>
      {top.length > 0 && (
        <div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)', marginBottom: 4 }}>
            Top affected packages
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {top.map((g) => (
              <span
                key={g.key}
                className="chip"
                style={{ fontSize: 10 }}
                title={`${g.cves.length} CVE${g.cves.length > 1 ? 's' : ''}`}
              >
                {g.name} ({g.cves.length})
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PackageDetail({
  group,
  onFlag,
  flaggingId,
}: {
  group: PackageGroup;
  onFlag: (f: Finding) => void;
  flaggingId: number | null;
}) {
  const cmd = upgradeCmd(group.name, group.recommended, group.manifestPath);

  // CVE fix suggestion — AI giải thích CVE + đề xuất nâng cấp (gọi /findings/{id}/explain,
  // backend tự dùng prompt CVE-aware cho finding phụ thuộc).
  const [aiById, setAiById] = useState<Record<number, AnalysisResult>>({});
  const [aiLoadingId, setAiLoadingId] = useState<number | null>(null);
  const [aiErr, setAiErr] = useState<Record<number, string>>({});

  const runFix = async (f: Finding) => {
    setAiLoadingId(f.id);
    setAiErr((e) => ({ ...e, [f.id]: '' }));
    try {
      const res = await api.findings.explain(f.id);
      setAiById((m) => ({ ...m, [f.id]: res }));
    } catch (err) {
      setAiErr((e) => ({ ...e, [f.id]: err instanceof Error ? err.message : 'Lỗi gọi AI' }));
    } finally {
      setAiLoadingId(null);
    }
  };

  return (
    <div style={{ overflowY: 'auto', padding: '20px 28px 40px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <SevChip sev={group.maxSev} />
        <span className="chip" style={{ fontSize: 11 }}>
          {group.cves.length} CVE{group.cves.length > 1 ? 's' : ''}
        </span>
      </div>
      <h2 className="h2" style={{ lineHeight: 1.4, marginBottom: 16 }}>
        {group.name}
      </h2>

      <div className="cve-update-card">
        <div className="cve-update-header">
          <Icon name="download" size={11} /> Recommended dependency update
        </div>
        <div className="cve-pkg-row">
          <span className="cve-pkg-name">{group.name}</span>
          {group.current && <span className="cve-version current">{group.current}</span>}
          {(group.current || group.recommended) && <span className="cve-arrow">→</span>}
          {group.recommended ? (
            <span className="cve-version fixed">{group.recommended}</span>
          ) : (
            <span className="cve-version unknown">no fixed version published</span>
          )}
        </div>
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
        <div
          style={{
            fontSize: 11,
            fontWeight: 600,
            color: 'var(--fg-3)',
            marginBottom: 10,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
          }}
        >
          CVEs in this dependency ({group.cves.length})
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {group.cves
            .slice()
            .sort((a, b) => (SEV_RANK[b.severity] ?? 0) - (SEV_RANK[a.severity] ?? 0))
            .map((f) => {
              const { cveId, fixed } = pkgMeta(f);
              const ai = aiById[f.id];
              const aiLoading = aiLoadingId === f.id;
              const err = aiErr[f.id];
              // Gemini đôi khi bọc diff trong ```diff … ``` — bỏ fence cho gọn.
              const fixText = (ai?.remediation_diff || '')
                .replace(/^```[a-z]*\n?/i, '')
                .replace(/```\s*$/, '')
                .trim();
              return (
                <div
                  key={f.id}
                  style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                      padding: '8px 10px',
                      background: 'var(--bg-elev)',
                      border: '1px solid var(--line)',
                      borderRadius: 6,
                    }}
                  >
                    <SevChip sev={f.severity} />
                    <span className="mono" style={{ fontSize: 12, fontWeight: 600, minWidth: 140 }}>
                      {cveId || f.rule_id}
                    </span>
                    {f.cvss_score != null && (
                      <span className="chip" style={{ fontSize: 10 }}>
                        CVSS {f.cvss_score}
                      </span>
                    )}
                    <span
                      style={{
                        flex: 1,
                        fontSize: 12,
                        color: 'var(--fg-2)',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {f.message.split('\n')[0]}
                    </span>
                    {fixed && fixed !== group.recommended && (
                      <span className="mono" style={{ fontSize: 10.5, color: 'var(--fg-3)' }}>
                        fix: {fixed}
                      </span>
                    )}
                    <button
                      className="btn ghost sm"
                      style={{ padding: '1px 6px', fontSize: 10 }}
                      title="AI gợi ý cách khắc phục CVE này (nâng cấp phiên bản)"
                      disabled={aiLoading}
                      onClick={() => runFix(f)}
                    >
                      <Icon name="sparkle" size={11} /> {aiLoading ? '…' : ai ? 'AI ✓' : 'AI fix'}
                    </button>
                    {f.status === 'REVOKED' ? (
                      <span className="row-status-badge revoked">Rev</span>
                    ) : (
                      <button
                        className="btn ghost sm"
                        style={{ padding: '1px 6px', fontSize: 10 }}
                        title="Đánh dấu CVE này là false positive — lần quét sau tự bỏ qua (cần security_lead+)"
                        disabled={flaggingId === f.id}
                        onClick={() => onFlag(f)}
                      >
                        <Icon name="shield" size={11} /> {flaggingId === f.id ? '…' : 'Flag FP'}
                      </button>
                    )}
                  </div>

                  {err && (
                    <div style={{ fontSize: 11.5, color: 'var(--err-fg)', padding: '0 10px' }}>
                      {err}
                    </div>
                  )}

                  {ai && (
                    <div
                      className="cve-ai-fix"
                      style={{
                        border: '1px solid var(--line)',
                        borderLeft: '3px solid var(--accent, #ff6a3d)',
                        borderRadius: 6,
                        padding: '10px 12px',
                        background: 'var(--bg)',
                        fontSize: 12.5,
                        lineHeight: 1.5,
                      }}
                    >
                      <div style={{ fontWeight: 700, marginBottom: 4, display: 'flex', gap: 6, alignItems: 'center' }}>
                        <Icon name="sparkle" size={12} /> AI gợi ý fix
                        <span className="chip" style={{ fontSize: 10 }}>confidence: {ai.confidence}</span>
                      </div>
                      <p style={{ margin: '4px 0' }}>
                        <strong>Giải thích:</strong> {ai.explanation_vi}
                      </p>
                      <p style={{ margin: '4px 0' }}>
                        <strong>Tác động:</strong> {ai.impact_vi}
                      </p>
                      {fixText && (
                        <div className="code-block" style={{ marginTop: 8 }}>
                          <div className="code-block-header">
                            <span>Khắc phục (nâng cấp)</span>
                            <button
                              className="btn ghost sm"
                              onClick={() => navigator.clipboard?.writeText(fixText)}
                            >
                              <Icon name="copy" size={12} /> Copy
                            </button>
                          </div>
                          <pre style={{ margin: 0, padding: 12, fontSize: 12, overflowX: 'auto' }}>
                            {fixText}
                          </pre>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
        </div>
      </div>

      <div className="card card-pad" style={{ marginTop: 16 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <div style={{ color: 'var(--fg-3)', fontSize: 11, marginBottom: 2 }}>Manifest</div>
            <div className="mono" style={{ fontSize: 12, wordBreak: 'break-all' }}>
              {group.manifestPath}
            </div>
          </div>
          <div>
            <div style={{ color: 'var(--fg-3)', fontSize: 11, marginBottom: 2 }}>Tool</div>
            <div className="mono" style={{ fontSize: 12 }}>
              {group.cves[0]?.tool ?? ''}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

const SEV_FLOORS = ['critical', 'high', 'medium', 'low'] as const;
type SevFloor = (typeof SEV_FLOORS)[number];

export function PageSCA() {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectFilter, setProjectFilter] = useState<number | 'all'>('all');
  const [sevFloor, setSevFloor] = useState<SevFloor>('high'); // default: HIGH+CRITICAL only
  const [search, setSearch] = useState('');
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [refetchTick, setRefetchTick] = useState(0);

  // Inline "flag CVE as false positive" — same 1-click revoke + suppression
  // flow as the Vulnerabilities page. Backend keeps the security_lead+ gate.
  const [flaggingId, setFlaggingId] = useState<number | null>(null);
  const [flagNotice, setFlagNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);
  const { containerRef, gridColumns, onResizerPointerDown } = useResizableSplit('sca.listWidth');

  useEffect(() => {
    api.projects
      .list()
      .then(setProjects)
      .catch(() => {});
  }, []);

  const ambient = useActiveProjectParam();

  useEffect(() => {
    setLoading(true);
    const params: FindingListParams = {
      category: 'deps', limit: PAGE_SIZE, skip: 0,
      exclude_revoked: true, latest_run_only: true,
    };
    // Page-level dropdown wins; otherwise fall back to the topbar selection.
    if (projectFilter !== 'all') params.project_id = projectFilter as number;
    else if (ambient.project_id !== undefined) params.project_id = ambient.project_id;
    api.findings
      .listWithTotal(params)
      .then(({ data }) => {
        setFindings(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [projectFilter, ambient.project_id, refetchTick]);

  const handleFlag = async (f: Finding) => {
    setFlaggingId(f.id);
    setFlagNotice(null);
    try {
      await flagFalsePositive(f);
      setFlagNotice({
        kind: 'ok',
        text: `Đã flag CVE #${f.id} là false positive — lần quét sau sẽ tự bỏ qua.`,
      });
      setRefetchTick((t) => t + 1);
    } catch (e) {
      setFlagNotice({ kind: 'err', text: `Không flag được #${f.id}: ${(e as Error).message}` });
    } finally {
      setFlaggingId(null);
    }
  };

  const groups = useMemo(() => {
    const floor = SEV_RANK[sevFloor] ?? 3;
    const filtered = findings.filter((f) => (SEV_RANK[f.severity] ?? 0) >= floor);
    let g = groupByPackage(filtered);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      g = g.filter(
        (x) =>
          x.name.toLowerCase().includes(q) ||
          x.cves.some((c) => pkgMeta(c).cveId.toLowerCase().includes(q))
      );
    }
    return g;
  }, [findings, sevFloor, search]);

  const selected = groups.find((g) => g.key === selectedKey) ?? groups[0] ?? null;

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>
      <div
        ref={containerRef}
        className="vuln-split"
        style={{ flex: 1, minWidth: 0, gridTemplateColumns: gridColumns }}
      >
        <div
          className="vuln-list-pane"
          style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}
        >
          <div
            style={{
              padding: '14px 16px 10px',
              borderBottom: '1px solid var(--line)',
              display: 'flex',
              alignItems: 'baseline',
              gap: 10,
              flexShrink: 0,
            }}
          >
            <h2 className="h2" style={{ margin: 0 }}>
              Dependencies (SCA)
            </h2>
            <span className="muted" style={{ fontSize: 12 }}>
              {loading ? '…' : `${groups.length} affected`}
            </span>
          </div>

          {projects.length > 1 && (
            <div style={{ padding: '6px 12px 0', flexShrink: 0 }}>
              <select
                style={{
                  width: '100%',
                  padding: '5px 8px',
                  background: 'var(--bg-elev)',
                  border: '1px solid var(--line)',
                  borderRadius: 6,
                  fontSize: 11.5,
                }}
                value={projectFilter}
                onChange={(e) =>
                  setProjectFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))
                }
              >
                <option value="all">All projects</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div style={{ padding: '8px 12px 6px', flexShrink: 0 }}>
            <div className="search-box" style={{ width: '100%' }}>
              <Icon name="search" size={13} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Package, CVE id…"
              />
            </div>
          </div>

          <div className="filter-toolbar" title="Hiển thị mọi severity từ mức này trở lên">
            <span
              style={{ fontSize: 10.5, color: 'var(--fg-3)', alignSelf: 'center', marginRight: 4 }}
            >
              Severity ≥
            </span>
            {SEV_FLOORS.map((s) => (
              <button
                key={s}
                className={`tb-pill${sevFloor === s ? ' active' : ''}`}
                onClick={() => setSevFloor(s)}
                title={`Show ${s} and above`}
              >
                {s[0].toUpperCase() + s.slice(1)}
              </button>
            ))}
          </div>

          {flagNotice && (
            <div
              style={{
                margin: '6px 12px 0',
                padding: '6px 10px',
                borderRadius: 6,
                fontSize: 11.5,
                flexShrink: 0,
                background:
                  flagNotice.kind === 'err' ? 'rgba(229,57,53,0.15)' : 'rgba(67,160,71,0.15)',
                color: flagNotice.kind === 'err' ? 'var(--sev-crit-fg)' : 'var(--sev-low-fg)',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <span style={{ flex: 1 }}>{flagNotice.text}</span>
              <button
                className="btn ghost sm"
                style={{ padding: '0 4px' }}
                onClick={() => setFlagNotice(null)}
              >
                <Icon name="x" size={11} />
              </button>
            </div>
          )}

          {!loading && groups.length > 0 && <SummaryBar groups={groups} />}

          <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
            {loading && <div className="empty">Loading…</div>}
            {!loading && groups.length === 0 && (
              <div className="empty">
                {findings.length === 0
                  ? 'No dependency vulnerabilities'
                  : `No deps at severity ≥ ${sevFloor}`}
              </div>
            )}
            {groups.map((g) => (
              <div
                key={g.key}
                data-testid="dep-pkg-row"
                data-sev={g.maxSev}
                className={`vuln-row${selectedKey === g.key ? ' active' : ''}`}
                onClick={() => setSelectedKey(g.key)}
              >
                <div className="vuln-row-title">
                  {g.name}
                  {g.current && (
                    <span
                      className="mono"
                      style={{ fontSize: 10.5, color: 'var(--fg-3)', marginLeft: 6 }}
                    >
                      {g.current}
                      {g.recommended && g.recommended !== g.current ? ` → ${g.recommended}` : ''}
                    </span>
                  )}
                </div>
                <div className="vuln-row-meta">
                  <SevChip sev={g.maxSev} />
                  <span className="chip" style={{ fontSize: 10 }}>
                    {g.cves.length} CVE{g.cves.length > 1 ? 's' : ''}
                  </span>
                  {g.recommended && g.recommended !== g.current && (
                    <span
                      className="chip"
                      style={{
                        fontSize: 10,
                        background: 'var(--accent-tint)',
                        color: 'var(--accent-2)',
                      }}
                    >
                      fix available
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="col-resizer" onPointerDown={onResizerPointerDown} />

        <div
          style={{
            flex: 1,
            minWidth: 0,
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {selected ? (
            <PackageDetail group={selected} onFlag={handleFlag} flaggingId={flaggingId} />
          ) : (
            <div className="empty" style={{ marginTop: 80 }}>
              {loading ? 'Loading…' : 'Chọn một dependency để xem chi tiết'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
