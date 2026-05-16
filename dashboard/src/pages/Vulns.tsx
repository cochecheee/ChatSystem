import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import type { FindingListParams } from '../api/client';
import { POLL_INTERVAL_MS } from '../lib/constants';
import { Badge } from '../components/Badge';
import { Icon } from '../components/Icon';
import { AiTriageModal } from '../components/AiTriageModal';
import { useActiveProjectParam } from '../contexts/ProjectContext';
import { useOverviewStats } from '../features/findings/useStats';
import type { AnalysisResult, Finding, Project } from '../types';

// Dependency-scanner tools — findings from these are CVE/package-update type.
// MUST khớp với DEPS_TOOLS ở backend (repositories/finding_repo.py) để filter category=sast|deps đúng.
const DEP_SCAN_TOOLS = new Set(['trivy', 'dep-check', 'dependency-check', 'snyk', 'owasp-dep-check', 'owasp-dependency-check', 'grype', 'trivy-deps']);
function isDepScan(tool: string) {
  return DEP_SCAN_TOOLS.has(tool.toLowerCase());
}

const PAGE_SIZE = 100;

// Extract package metadata from raw_data (field names vary by tool)
function pkgMeta(f: Finding) {
  const d = f.raw_data ?? {};
  const name = (d.PkgName ?? d.pkg_name ?? d.package_name ?? d.packageName ?? d.component ?? '') as string;
  const current = (d.InstalledVersion ?? d.installed_version ?? d.current_version ?? d.version ?? '') as string;
  const fixed = (d.FixedVersion ?? d.fixed_version ?? d.fix_version ?? d.patchedVersions ?? '') as string;
  const cveId = (d.VulnerabilityID ?? d.vulnerability_id ?? '') as string || (f.rule_id.match(/^(CVE|GHSA|PRISMA|SNYK)-/i) ? f.rule_id : '');
  return { name, current, fixed, cveId };
}

function SevChip({ sev }: { sev: string }) {
  return <Badge variant={sev as 'critical' | 'high' | 'medium' | 'low' | 'info'} dot>{sev}</Badge>;
}

function DiffView({ diff }: { diff: string }) {
  const lines = diff.split('\n');
  return (
    <div className="code-block">
      <div className="code-block-header">
        <span>Remediation diff</span>
        <button className="btn ghost sm" onClick={() => navigator.clipboard?.writeText(diff)}>
          <Icon name="copy" size={12} /> Copy
        </button>
      </div>
      <pre style={{ margin: 0, padding: 12, overflowX: 'auto', lineHeight: 1.55, fontSize: 12 }}>
        {lines.map((line, i) => {
          const isAdd = line.startsWith('+') && !line.startsWith('+++');
          const isRem = line.startsWith('-') && !line.startsWith('---');
          const kind = isAdd ? 'add' : isRem ? 'rem' : 'ctx';
          return (
            <div key={i} className={`diff-line ${kind}`}>
              <span className="ln">{i + 1}</span>
              <span className="marker">{isAdd ? '+' : isRem ? '−' : ' '}</span>
              <span>{line.slice(1)}</span>
            </div>
          );
        })}
      </pre>
    </div>
  );
}

// Prominent update card shown at top of detail for CVE/dep-scan findings
function CveUpdateCard({ finding }: { finding: Finding }) {
  const { name, current, fixed, cveId } = pkgMeta(finding);
  const manifest = finding.file_path.split('/').pop() ?? finding.file_path;
  const displayName = name || manifest;

  return (
    <div className="cve-update-card">
      <div className="cve-update-header">
        <Icon name="download" size={11} />
        Dependency update required
      </div>
      <div className="cve-pkg-row">
        <span className="cve-pkg-name">{displayName}</span>
        {current ? (
          <span className="cve-version current">{current}</span>
        ) : null}
        {(current || fixed) && <span className="cve-arrow">→</span>}
        {fixed ? (
          <span className="cve-version fixed">{fixed}</span>
        ) : (
          <span className="cve-version unknown">check latest</span>
        )}
      </div>
      {(cveId || finding.cwe_id) && (
        <div className="cve-id-row">
          {cveId && <span className="cve-id-badge">{cveId}</span>}
          {finding.cwe_id && cveId !== finding.cwe_id && (
            <span className="cve-id-badge">{finding.cwe_id}</span>
          )}
          {finding.cvss_score != null && (
            <span className="chip" style={{ fontSize: 11 }}>CVSS {finding.cvss_score}</span>
          )}
        </div>
      )}
    </div>
  );
}

function AiPanel({ finding, onClose }: { finding: Finding; onClose: () => void }) {
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<{ role: 'user' | 'ai'; text: string }[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setError('');
    setMessages([]);
    if (finding.ai_analysis) {
      setAnalysis(finding.ai_analysis);
    } else {
      setAnalysis(null);
    }
  }, [finding.id]);

  const runAnalysis = async () => {
    setLoading(true);
    setError('');
    try {
      const result = await api.findings.explain(finding.id);
      setAnalysis(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text) return;
    setMessages(m => [...m, { role: 'user', text }]);
    setInput('');
    try {
      const res = await api.chat.message(text, finding.id);
      setMessages(m => [...m, { role: 'ai', text: res.reply }]);
    } catch (e) {
      setMessages(m => [...m, { role: 'ai', text: `Lỗi: ${e}` }]);
    }
  };

  return (
    <div className="ai-panel docked" style={{ display: 'flex', height: '100%', minHeight: 0 }}>
      <div className="ai-header">
        <div className="ai-orb" />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 500, fontSize: 13 }}>AI Assistant</div>
          <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>Gemini · tiếng Việt</div>
        </div>
        <button className="btn ghost" style={{ padding: 4 }} onClick={onClose}>
          <Icon name="x" size={14} />
        </button>
      </div>

      <div className="ai-messages" style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
        {!analysis && !loading && messages.length === 0 && (
          <div className="msg">
            <div className="msg-role"><Icon name="bot" size={13} /><span className="who">Sentinel AI</span></div>
            <div className="msg-body">
              <p>
                Finding: <strong>{finding.rule_id}</strong><br />
                File: <code>{finding.file_path}{finding.line_number ? `:${finding.line_number}` : ''}</code>
              </p>
              <p>Nhấn nút bên dưới để nhận giải thích và remediation diff bằng tiếng Việt, hoặc đặt câu hỏi tự do.</p>
            </div>
            <div className="msg-actions" style={{ marginTop: 8 }}>
              <div className="action-card" onClick={runAnalysis}>
                <div className="ac-icon"><Icon name="sparkle" size={14} /></div>
                <div>
                  <div className="ac-title">Phân tích AI</div>
                  <div className="ac-sub">Giải thích + diff sửa lỗi</div>
                </div>
              </div>
            </div>
          </div>
        )}

        {loading && (
          <div className="msg">
            <div className="msg-role"><Icon name="bot" size={13} /><span className="who">Sentinel AI</span></div>
            <div className="msg-body" style={{ color: 'var(--fg-3)', fontSize: 12 }}>Đang phân tích…</div>
          </div>
        )}

        {error && (
          <div className="msg">
            <div className="msg-role">
              <Icon name="alert" size={13} style={{ color: 'var(--err-fg)' }} />
              <span className="who" style={{ color: 'var(--err-fg)' }}>Lỗi</span>
            </div>
            <div className="msg-body" style={{ color: 'var(--err-fg)', fontSize: 12 }}>{error}</div>
          </div>
        )}

        {analysis && (
          <div className="msg">
            <div className="msg-role">
              <Icon name="bot" size={13} />
              <span className="who">Sentinel AI</span>
              <span className="chip" style={{ fontSize: 10, marginLeft: 4 }}>
                confidence: {analysis.confidence}
              </span>
            </div>
            <div className="msg-body">
              <p><strong>Giải thích:</strong> {analysis.explanation_vi}</p>
              <p><strong>Tác động:</strong> {analysis.impact_vi}</p>
              {analysis.cwe_reference && (
                <p><strong>CWE:</strong> {analysis.cwe_reference}</p>
              )}
            </div>
            {analysis.remediation_diff && (
              <div style={{ marginTop: 8 }}>
                <DiffView diff={analysis.remediation_diff} />
              </div>
            )}
            {!loading && (
              <div className="msg-actions" style={{ marginTop: 8 }}>
                <div className="action-card" onClick={runAnalysis}>
                  <div className="ac-icon"><Icon name="refresh" size={14} /></div>
                  <div>
                    <div className="ac-title">Phân tích lại</div>
                    <div className="ac-sub">Gọi Gemini thêm một lần nữa</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-role">
              <Icon name={m.role === 'user' ? 'user' : 'bot'} size={13} />
              <span className="who">{m.role === 'user' ? 'Bạn' : 'Sentinel AI'}</span>
            </div>
            <div className="msg-body"><p>{m.text}</p></div>
          </div>
        ))}
      </div>

      <div style={{ padding: '0 14px 6px', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {['/explain', '/fix', '/scan'].map(cmd => (
            <span key={cmd} className="suggestion-chip" onClick={() => setInput(cmd)}>{cmd}</span>
          ))}
        </div>
      </div>

      <div className="ai-composer" style={{ flexShrink: 0 }}>
        <div className="ai-composer-box">
          <textarea
            ref={textareaRef}
            rows={2}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
            placeholder="Hỏi về finding này… (Enter để gửi)"
          />
          <div className="ai-composer-row">
            <span className="grow" />
            <button className="btn primary sm" onClick={sendMessage} disabled={!input.trim()}>
              <Icon name="send" size={12} /> Gửi
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function FindingDetail({ finding, showAI, onToggleAI }: {
  finding: Finding;
  showAI: boolean;
  onToggleAI: () => void;
}) {
  const owasp = finding.raw_data?.owasp_category as string | undefined;
  const cweName = finding.raw_data?.cwe_name as string | undefined;
  const depScan = isDepScan(finding.tool);

  const SEV_FG: Record<string, string> = {
    critical: 'var(--sev-crit-fg)', high: 'var(--sev-high-fg)',
    medium:   'var(--sev-med-fg)',  low:  'var(--sev-low-fg)',
    info:     'var(--sev-info-fg)',
  };
  const SEV_BG: Record<string, string> = {
    critical: 'var(--sev-crit-bg)', high: 'var(--sev-high-bg)',
    medium:   'var(--sev-med-bg)',  low:  'var(--sev-low-bg)',
    info:     'var(--sev-info-bg)',
  };
  const sevFg = SEV_FG[finding.severity] ?? 'var(--fg-3)';
  const sevBg = SEV_BG[finding.severity] ?? 'var(--bg-muted)';

  return (
    <div style={{ display: 'grid', gridTemplateColumns: showAI ? 'minmax(0,1fr) 360px' : '1fr', height: '100%', minHeight: 0 }}>
      <div style={{ overflowY: 'auto', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {/* Severity accent header */}
        <div style={{ background: sevBg, flexShrink: 0 }}>
          <div style={{ height: 4, background: sevFg }} />
          <div style={{ padding: '18px 28px 16px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <SevChip sev={finding.severity} />
                <span className="tool-tag">{finding.tool}</span>
                {!depScan && finding.cwe_id && <span className="chip">{finding.cwe_id}</span>}
                {finding.status === 'ai_analyzed' && (
                  <span className="chip" style={{ background: 'var(--accent-tint)', color: 'var(--accent-2)', fontSize: 10 }}>AI analyzed</span>
                )}
                {finding.status === 'APPROVED' && (
                  <span className="chip" style={{ background: 'rgba(67,160,71,0.15)', color: 'var(--sev-low-fg)', fontSize: 10 }}>Approved</span>
                )}
                {finding.status === 'REVOKED' && (
                  <span className="chip" style={{ background: 'rgba(229,57,53,0.15)', color: 'var(--sev-crit-fg)', fontSize: 10 }}>Revoked</span>
                )}
              </div>
              <h2 className="h2" style={{ lineHeight: 1.4 }}>{finding.message}</h2>
            </div>
            <button className="btn sm" style={{ flexShrink: 0, marginLeft: 12 }} onClick={onToggleAI}>
              <Icon name="sparkle" size={12} /> {showAI ? 'Hide AI' : 'Ask AI'}
            </button>
          </div>
        </div>

        <div style={{ padding: '20px 28px 40px', flex: 1 }}>
          {/* CVE update card — replaces metadata clutter for dep-scan findings */}
          {depScan && <CveUpdateCard finding={finding} />}

          {/* Metadata grid — simplified for dep-scan (no redundant CVE fields) */}
          <div className="card card-pad" style={{ marginBottom: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              {(depScan
                ? [
                    ['Manifest', finding.file_path],
                    ['Tool', finding.tool],
                    ['Status', finding.status],
                    ['Detected', finding.normalized_at ? new Date(finding.normalized_at).toLocaleString() : null],
                  ]
                : [
                    ['Rule', finding.rule_id],
                    ['File', `${finding.file_path}${finding.line_number ? `:${finding.line_number}` : ''}`],
                    ['Tool', finding.tool],
                    ['Status', finding.status],
                    ['CWE', finding.cwe_id],
                    ['CVSS', finding.cvss_score != null ? String(finding.cvss_score) : null],
                    ['Normalized', finding.normalized_at ? new Date(finding.normalized_at).toLocaleString() : null],
                  ]
              ).filter(([_k, v]) => v).map(([k, v]) => (
                <div key={k as string}>
                  <div style={{ color: 'var(--fg-3)', fontSize: 11, marginBottom: 2 }}>{k}</div>
                  <div className="mono" style={{ fontSize: 12, wordBreak: 'break-all' }}>{v}</div>
                </div>
              ))}
            </div>
          </div>

          {!depScan && (owasp || cweName) && (
            <div className="card card-pad" style={{ marginBottom: 16 }}>
              {owasp && (
                <>
                  <div style={{ fontSize: 11, color: 'var(--fg-3)', marginBottom: 4 }}>OWASP Top 10 2021</div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{owasp}</div>
                </>
              )}
              {cweName && (
                <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: owasp ? 4 : 0 }}>{cweName}</div>
              )}
            </div>
          )}

          {(finding.approved_by || finding.revoked_by) && (
            <div className="card card-pad" style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--fg-3)', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                Audit Trail
              </div>
              {finding.approved_by && (
                <div style={{ fontSize: 12, marginBottom: 6 }}>
                  <span style={{ color: 'var(--fg-3)' }}>Approved by </span>
                  <strong>{finding.approved_by}</strong>
                  {finding.approved_at && <span style={{ color: 'var(--fg-3)' }}> · {new Date(finding.approved_at).toLocaleString()}</span>}
                  {finding.justification && <div style={{ marginTop: 4, fontStyle: 'italic', color: 'var(--fg-3)' }}>"{finding.justification}"</div>}
                </div>
              )}
              {finding.revoked_by && (
                <div style={{ fontSize: 12 }}>
                  <span style={{ color: 'var(--fg-3)' }}>Revoked by </span>
                  <strong>{finding.revoked_by}</strong>
                  {finding.revoked_at && <span style={{ color: 'var(--fg-3)' }}> · {new Date(finding.revoked_at).toLocaleString()}</span>}
                  {finding.revoke_justification && <div style={{ marginTop: 4, fontStyle: 'italic', color: 'var(--fg-3)' }}>"{finding.revoke_justification}"</div>}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {showAI && (
        <AiPanel finding={finding} onClose={onToggleAI} />
      )}
    </div>
  );
}

export function PageVulns({ initialId }: { initialId?: number }) {
  // Vulns page = SAST findings only. Dependencies → SCA page.
  const [findings, setFindings] = useState<Finding[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [projectFilter, setProjectFilter] = useState<number | 'all'>('all');
  const [sevFilter, setSevFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [toolFilter, setToolFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(initialId ?? null);
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [showAI, setShowAI] = useState(true);

  const { stats } = useOverviewStats(POLL_INTERVAL_MS);
  const ambient = useActiveProjectParam();
  const [triageOpen, setTriageOpen] = useState(false);
  const [refetchTick, setRefetchTick] = useState(0);

  useEffect(() => {
    api.projects.list().then(setProjects).catch(() => {});
  }, []);

  const buildParams = (override: Partial<FindingListParams> = {}): FindingListParams => {
    const params: FindingListParams = {
      limit: PAGE_SIZE,
      skip: page * PAGE_SIZE,
      category: 'sast',
      ...override,
    };
    if (projectFilter !== 'all') params.project_id = projectFilter as number;
    else if (ambient.project_id !== undefined) params.project_id = ambient.project_id;
    if (sevFilter !== 'all') params.severity = sevFilter;
    if (toolFilter !== 'all') params.tool = toolFilter;
    if (statusFilter !== 'all') {
      const map: Record<string, string> = {
        pending: 'pending_review',
        analyzed: 'ai_analyzed',
        approved: 'APPROVED',
        revoked: 'REVOKED',
      };
      if (map[statusFilter]) params.status = map[statusFilter];
    }
    if (search.trim()) params.q = search.trim();
    return params;
  };

  useEffect(() => {
    setPage(0);
  }, [projectFilter, sevFilter, statusFilter, toolFilter, search]);

  useEffect(() => {
    setLoading(true);
    api.findings.listWithTotal(buildParams())
      .then(({ data, total: t }) => {
        setFindings(data);
        setTotal(t);
        setLoading(false);
      })
      .catch(() => setLoading(false));
    const id = setInterval(() => {
      api.findings.listWithTotal(buildParams())
        .then(({ data, total: t }) => { setFindings(data); setTotal(t); })
        .catch(() => {});
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, projectFilter, sevFilter, statusFilter, toolFilter, search, ambient.project_id, refetchTick]);

  useEffect(() => { if (initialId != null) setSelectedId(initialId); }, [initialId]);

  useEffect(() => {
    if (selectedId == null) { setSelectedFinding(null); return; }
    const cached = findings.find(f => f.id === selectedId);
    if (cached) setSelectedFinding(cached);
    api.findings.get(selectedId)
      .then(f => {
        setSelectedFinding(f);
        setFindings(prev => prev.map(x => x.id === f.id ? f : x));
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // Total SAST findings từ server stats (across all severity/status filter).
  let sastTotal = 0;
  for (const [tool, count] of Object.entries(stats?.by_tool ?? {})) {
    if (!DEP_SCAN_TOOLS.has(tool.toLowerCase())) sastTotal += count;
  }

  // Tools dropdown: chỉ SAST tools.
  const tools = Object.keys(stats?.by_tool ?? {})
    .filter(t => !DEP_SCAN_TOOLS.has(t.toLowerCase()))
    .sort();

  // Severity counts cho summary bar — derive từ current page (sample).
  // Khi total > PAGE_SIZE và filter sev='all', đây là sample chứ không phải full;
  // nhưng trong practice user filter từng severity nên numbers phản ánh đúng phạm vi đang xem.
  const sevCounts = findings.reduce(
    (acc, f) => { acc[f.severity] = (acc[f.severity] ?? 0) + 1; return acc; },
    {} as Record<string, number>,
  );

  const filtered = findings.slice();
  const selected = selectedFinding ?? filtered[0] ?? null;

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>
      <div className="vuln-split" style={{ flex: 1, minWidth: 0 }}>

        <div className="vuln-list-pane" style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {/* Page header — SAST findings only (dependencies → SCA page) */}
          <div style={{
            padding: '14px 16px 10px', borderBottom: '1px solid var(--line)',
            display: 'flex', alignItems: 'baseline', gap: 10, flexShrink: 0,
          }}>
            <h2 className="h2" style={{ margin: 0 }}>SAST findings</h2>
            <span className="muted" style={{ fontSize: 12 }}>
              {stats == null ? '…' : `${sastTotal} total`}
            </span>
            <div style={{ flex: 1 }} />
            <button
              className="btn primary sm"
              style={{ padding: '4px 10px', fontSize: 11 }}
              onClick={() => setTriageOpen(true)}
              title="Gemini classify pending findings — auto-revoke false positives"
            >
              <Icon name="sparkle" size={11} /> AI Triage
            </button>
          </div>

          {/* Project selector */}
          {projects.length > 1 && (
            <div style={{ padding: '6px 12px 0', flexShrink: 0 }}>
              <select
                style={{
                  width: '100%', padding: '5px 8px', background: 'var(--bg-elev)',
                  border: '1px solid var(--line)', borderRadius: 6, color: 'var(--fg)', fontSize: 11.5, outline: 'none',
                  font: 'inherit',
                }}
                value={projectFilter}
                onChange={e => setProjectFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))}
              >
                <option value="all">All projects</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </div>
          )}

          {/* Search */}
          <div style={{ padding: '8px 12px 6px', flexShrink: 0 }}>
            <div className="search-box" style={{ width: '100%' }}>
              <Icon name="search" size={13} />
              <input
                value={search}
                onChange={e => setSearch(e.target.value)}
                placeholder="Rule, file, message…"
              />
            </div>
          </div>

          {/* Severity summary bar */}
          {!loading && findings.length > 0 && (
            <div className="sev-summary-bar">
              {(['critical', 'high', 'medium', 'low'] as const).map(sev => {
                const cnt = sevCounts[sev] ?? 0;
                if (cnt === 0) return null;
                return (
                  <button
                    key={sev}
                    className={`sev-summary-chip sev-${sev}${sevFilter === sev ? ' active' : ''}`}
                    onClick={() => setSevFilter(prev => prev === sev ? 'all' : sev)}
                    title={`Filter to ${sev} only — click again to clear`}
                  >
                    <span className="sev-summary-label">{sev[0].toUpperCase() + sev.slice(1)}</span>
                    <span className="sev-summary-count">{cnt}</span>
                  </button>
                );
              })}
              {sevFilter !== 'all' && (
                <button
                  className="sev-summary-chip"
                  style={{ background: 'var(--bg-muted)', color: 'var(--fg-3)' }}
                  onClick={() => setSevFilter('all')}
                  title="Clear severity filter"
                >
                  ✕ all
                </button>
              )}
            </div>
          )}

          {/* Compact filter toolbar */}
          <div className="filter-toolbar">
            {tools.length > 1 && (
              <>
                <select value={toolFilter} onChange={e => setToolFilter(e.target.value)} title="Filter by tool">
                  <option value="all">All tools</option>
                  {tools.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
                <span className="tb-sep" />
              </>
            )}
            {([
              ['all',      'All'],
              ['pending',  'Pending'],
              ['analyzed', 'AI'],
              ['approved', 'OK'],
              ['revoked',  'Revoked'],
            ] as [string, string][]).map(([v, l]) => (
              <button key={v} className={`tb-pill${statusFilter === v ? ' active' : ''}`} onClick={() => setStatusFilter(v)}>{l}</button>
            ))}
          </div>

          {/* Pagination header — chỉ hiển thị khi total > PAGE_SIZE */}
          {!loading && total > PAGE_SIZE && (
            <div style={{
              padding: '6px 14px', borderBottom: '1px solid var(--line)',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              fontSize: 11, color: 'var(--fg-3)', flexShrink: 0,
            }}>
              <span>
                Showing <span className="mono">{page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)}</span>
                {' '}of <span className="mono">{total}</span>
              </span>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  className="btn ghost sm"
                  style={{ padding: '2px 8px', fontSize: 11 }}
                  onClick={() => setPage(p => Math.max(0, p - 1))}
                  disabled={page === 0}
                >
                  ← Prev
                </button>
                <span style={{ alignSelf: 'center' }}>
                  {page + 1} / {totalPages}
                </span>
                <button
                  className="btn ghost sm"
                  style={{ padding: '2px 8px', fontSize: 11 }}
                  onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                >
                  Next →
                </button>
              </div>
            </div>
          )}

          {/* Finding list */}
          <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
            {loading && <div className="empty">Loading…</div>}
            {!loading && filtered.length === 0 && (
              <div className="empty">
                {total === 0 ? 'No SAST findings found' : 'No findings match filters'}
              </div>
            )}

            {filtered.map(f => (
              <div
                key={f.id}
                data-testid="finding-row"
                data-sev={f.severity}
                className={`vuln-row${selectedId === f.id ? ' active' : ''}`}
                onClick={() => setSelectedId(f.id)}
              >
                <div className="vuln-row-title">{f.message.split('\n')[0]}</div>
                <div className="vuln-row-meta">
                  <SevChip sev={f.severity} />
                  <span className="tool-tag">{f.tool}</span>
                  <span className="mono" style={{ fontSize: 10.5 }}>
                    {f.file_path.split('/').pop()}{f.line_number ? `:${f.line_number}` : ''}
                  </span>
                  {f.status === 'ai_analyzed' && (
                    <Icon name="sparkle" size={11} style={{ color: 'var(--accent)', marginLeft: 2 }} />
                  )}
                  {f.status === 'APPROVED' && <span className="row-status-badge approved">OK</span>}
                  {f.status === 'REVOKED'  && <span className="row-status-badge revoked">Rev</span>}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {selected ? (
            <FindingDetail
              finding={selected}
              showAI={showAI}
              onToggleAI={() => setShowAI(s => !s)}
            />
          ) : (
            <div className="empty" style={{ marginTop: 80 }}>
              {loading ? 'Loading findings…' : 'Chọn một finding để xem chi tiết'}
            </div>
          )}
        </div>

      </div>
      <AiTriageModal
        open={triageOpen}
        onClose={() => setTriageOpen(false)}
        projectId={
          projectFilter !== 'all'
            ? (projectFilter as number)
            : ambient.project_id
        }
        onTriaged={() => setRefetchTick(t => t + 1)}
      />
    </div>
  );
}
