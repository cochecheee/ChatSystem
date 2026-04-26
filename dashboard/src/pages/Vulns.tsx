import { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { Icon } from '../components/Icon';
import type { AnalysisResult, Finding, Project } from '../types';
import { SEVERITY_ORDER } from '../types';

function SevChip({ sev }: { sev: string }) {
  return <span className={`chip dot sev-${sev}`}>{sev}</span>;
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

  return (
    <div style={{ display: 'grid', gridTemplateColumns: showAI ? 'minmax(0,1fr) 360px' : '1fr', height: '100%', minHeight: 0 }}>
      <div style={{ overflowY: 'auto', padding: '24px 28px 40px', minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <SevChip sev={finding.severity} />
              <span className="tool-tag">{finding.tool}</span>
              {finding.cwe_id && <span className="chip">{finding.cwe_id}</span>}
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

        <div className="card card-pad" style={{ marginBottom: 16 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {([
              ['Rule', finding.rule_id],
              ['File', `${finding.file_path}${finding.line_number ? `:${finding.line_number}` : ''}`],
              ['Tool', finding.tool],
              ['Status', finding.status],
              ['CWE', finding.cwe_id],
              ['CVSS', finding.cvss_score != null ? String(finding.cvss_score) : null],
              ['Normalized', finding.normalized_at ? new Date(finding.normalized_at).toLocaleString() : null],
            ] as [string, string | null | undefined][]).filter(([, v]) => v).map(([k, v]) => (
              <div key={k}>
                <div style={{ color: 'var(--fg-3)', fontSize: 11, marginBottom: 2 }}>{k}</div>
                <div className="mono" style={{ fontSize: 12, wordBreak: 'break-all' }}>{v}</div>
              </div>
            ))}
          </div>
        </div>

        {(owasp || cweName) && (
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

      {showAI && (
        <AiPanel finding={finding} onClose={onToggleAI} />
      )}
    </div>
  );
}

export function PageVulns({ initialId }: { initialId?: number }) {
  const [findings, setFindings] = useState<Finding[]>([]);
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

  useEffect(() => {
    api.projects.list().then(setProjects).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const params: Parameters<typeof api.findings.list>[0] = { limit: 500 };
    if (projectFilter !== 'all') params.project_id = projectFilter as number;
    api.findings.list(params)
      .then(f => { setFindings(f); setLoading(false); })
      .catch(() => setLoading(false));
    const id = setInterval(() => {
      const p: Parameters<typeof api.findings.list>[0] = { limit: 500 };
      if (projectFilter !== 'all') p.project_id = projectFilter as number;
      api.findings.list(p).then(setFindings).catch(() => {});
    }, 30_000);
    return () => clearInterval(id);
  }, [projectFilter]);

  useEffect(() => { if (initialId != null) setSelectedId(initialId); }, [initialId]);

  // Fetch individual finding from GET /findings/{id} when selection changes
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

  const tools = Array.from(new Set(findings.map(f => f.tool))).sort();

  const filtered = findings
    .filter(f => {
      if (sevFilter !== 'all' && f.severity !== sevFilter) return false;
      if (toolFilter !== 'all' && f.tool !== toolFilter) return false;
      if (statusFilter === 'pending' && f.status !== 'pending_review') return false;
      if (statusFilter === 'analyzed' && f.status !== 'ai_analyzed') return false;
      if (search) {
        const q = search.toLowerCase();
        if (!`${f.message} ${f.file_path} ${f.rule_id} ${f.tool}`.toLowerCase().includes(q)) return false;
      }
      return true;
    })
    .sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 9) - (SEVERITY_ORDER[b.severity] ?? 9));

  const selected = selectedFinding ?? filtered[0] ?? null;

  return (
    <div style={{ display: 'flex', flex: 1, minHeight: 0, overflow: 'hidden' }}>
      <div className="vuln-split" style={{ flex: 1, minWidth: 0 }}>

        <div className="vuln-list-pane" style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <div style={{ padding: '16px 16px 10px', flexShrink: 0 }}>
            <h1 className="h1" style={{ fontSize: 17 }}>Vulnerabilities</h1>
            <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
              {loading ? 'Loading…' : `${filtered.length} / ${findings.length} findings`}
            </div>
            {projects.length > 1 && (
              <select
                style={{
                  marginTop: 8, width: '100%', padding: '5px 8px', background: 'var(--surface-2)',
                  border: '1px solid var(--line)', borderRadius: 6, color: 'var(--fg)', fontSize: 11.5, outline: 'none',
                }}
                value={projectFilter}
                onChange={e => setProjectFilter(e.target.value === 'all' ? 'all' : Number(e.target.value))}
              >
                <option value="all">All projects</option>
                {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            )}
          </div>

          <div style={{ padding: '0 12px 10px', flexShrink: 0 }}>
            <div className="search-box" style={{ width: '100%' }}>
              <Icon name="search" size={13} />
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Rule, file, message…" />
            </div>
          </div>

          <div className="filter-bar" style={{ padding: '4px 12px', flexShrink: 0 }}>
            {(['all', 'critical', 'high', 'medium', 'low'] as const).map(s => (
              <button key={s} className={`filter-pill${sevFilter === s ? ' active' : ''}`} onClick={() => setSevFilter(s)}>{s}</button>
            ))}
          </div>

          {tools.length > 1 && (
            <div className="filter-bar" style={{ padding: '3px 12px', borderTop: 0, flexShrink: 0, flexWrap: 'wrap' }}>
              <button className={`filter-pill${toolFilter === 'all' ? ' active' : ''}`} onClick={() => setToolFilter('all')}>all tools</button>
              {tools.map(t => (
                <button key={t} className={`filter-pill${toolFilter === t ? ' active' : ''}`} onClick={() => setToolFilter(t)}>{t}</button>
              ))}
            </div>
          )}

          <div className="filter-bar" style={{ padding: '3px 12px', borderTop: 0, flexShrink: 0 }}>
            {[['all', 'All'], ['pending', 'Pending'], ['analyzed', 'AI Analyzed']].map(([v, l]) => (
              <button key={v} className={`filter-pill${statusFilter === v ? ' active' : ''}`} onClick={() => setStatusFilter(v)}>{l}</button>
            ))}
          </div>

          <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
            {loading && <div className="empty">Loading…</div>}
            {!loading && filtered.length === 0 && <div className="empty">No findings match filters</div>}
            {filtered.map(f => (
              <div
                key={f.id}
                data-testid="finding-row"
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
    </div>
  );
}
