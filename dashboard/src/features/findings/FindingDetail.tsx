import { useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import { Icon } from '../../components/Icon';
import { RevokeDialog } from '../../components/modals/RevokeDialog';
import type { AnalysisResult, Finding } from '../../types';
import { SevChip, isDepScan } from './sast';

// Extract package metadata from raw_data (field names vary by tool)
function pkgMeta(f: Finding) {
  const d = f.raw_data ?? {};
  const name = (d.PkgName ??
    d.pkg_name ??
    d.package_name ??
    d.packageName ??
    d.component ??
    '') as string;
  const current = (d.InstalledVersion ??
    d.installed_version ??
    d.current_version ??
    d.version ??
    '') as string;
  const fixed = (d.FixedVersion ??
    d.fixed_version ??
    d.fix_version ??
    d.patchedVersions ??
    '') as string;
  const cveId =
    ((d.VulnerabilityID ?? d.vulnerability_id ?? '') as string) ||
    (f.rule_id.match(/^(CVE|GHSA|PRISMA|SNYK)-/i) ? f.rule_id : '');
  return { name, current, fixed, cveId };
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
        {current ? <span className="cve-version current">{current}</span> : null}
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
            <span className="chip" style={{ fontSize: 11 }}>
              CVSS {finding.cvss_score}
            </span>
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
    setMessages((m) => [...m, { role: 'user', text }]);
    setInput('');
    try {
      const res = await api.chat.message(text, finding.id);
      setMessages((m) => [...m, { role: 'ai', text: res.reply }]);
    } catch (e) {
      setMessages((m) => [...m, { role: 'ai', text: `Lỗi: ${e}` }]);
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
            <div className="msg-role">
              <Icon name="bot" size={13} />
              <span className="who">Sentinel AI</span>
            </div>
            <div className="msg-body">
              <p>
                Finding: <strong>{finding.rule_id}</strong>
                <br />
                File:{' '}
                <code>
                  {finding.file_path}
                  {finding.line_number ? `:${finding.line_number}` : ''}
                </code>
              </p>
              <p>
                Nhấn nút bên dưới để nhận giải thích và remediation diff bằng tiếng Việt, hoặc đặt
                câu hỏi tự do.
              </p>
            </div>
            <div className="msg-actions" style={{ marginTop: 8 }}>
              <div className="action-card" onClick={runAnalysis}>
                <div className="ac-icon">
                  <Icon name="sparkle" size={14} />
                </div>
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
            <div className="msg-role">
              <Icon name="bot" size={13} />
              <span className="who">Sentinel AI</span>
            </div>
            <div className="msg-body" style={{ color: 'var(--fg-3)', fontSize: 12 }}>
              Đang phân tích…
            </div>
          </div>
        )}

        {error && (
          <div className="msg">
            <div className="msg-role">
              <Icon name="alert" size={13} style={{ color: 'var(--err-fg)' }} />
              <span className="who" style={{ color: 'var(--err-fg)' }}>
                Lỗi
              </span>
            </div>
            <div className="msg-body" style={{ color: 'var(--err-fg)', fontSize: 12 }}>
              {error}
            </div>
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
              <p>
                <strong>Giải thích:</strong> {analysis.explanation_vi}
              </p>
              <p>
                <strong>Tác động:</strong> {analysis.impact_vi}
              </p>
              {analysis.cwe_reference && (
                <p>
                  <strong>CWE:</strong> {analysis.cwe_reference}
                </p>
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
                  <div className="ac-icon">
                    <Icon name="refresh" size={14} />
                  </div>
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
            <div className="msg-body">
              <p>{m.text}</p>
            </div>
          </div>
        ))}
      </div>

      <div style={{ padding: '0 14px 6px', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {['/explain', '/fix', '/scan'].map((cmd) => (
            <span key={cmd} className="suggestion-chip" onClick={() => setInput(cmd)}>
              {cmd}
            </span>
          ))}
        </div>
      </div>

      <div className="ai-composer" style={{ flexShrink: 0 }}>
        <div className="ai-composer-box">
          <textarea
            ref={textareaRef}
            rows={2}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
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

export function FindingDetail({
  finding,
  showAI,
  onToggleAI,
  onRevoked,
}: {
  finding: Finding;
  showAI: boolean;
  onToggleAI: () => void;
  onRevoked: () => void;
}) {
  const owasp = finding.raw_data?.owasp_category as string | undefined;
  const cweName = finding.raw_data?.cwe_name as string | undefined;
  const depScan = isDepScan(finding.tool);
  const [revokeOpen, setRevokeOpen] = useState(false);
  // V3.6 FP-B — after a successful revoke, offer to create a Tier 2
  // suppression rule so future scans matching the same (rule_id, file)
  // pattern are auto-revoked at ingest time. Different from Tier 1 (which
  // only inherits via exact dedup_hash) — Tier 2 catches edits that shift
  // line numbers or wording.
  const [suppressOpen, setSuppressOpen] = useState(false);
  const [suppressLoading, setSuppressLoading] = useState(false);
  const [suppressMsg, setSuppressMsg] = useState<string | null>(null);
  const [lastJustification, setLastJustification] = useState('');

  // V3.6 FP-A — "Đánh dấu không phải lỗi" wraps the /revoke ChatOps command.
  // BE enforces security_lead+ role + min 20-char justification. On success
  // parent re-fetches list so the row badge flips to "Revoked".
  const handleRevoke = async (justification: string) => {
    await api.chat.command({
      command: '/revoke',
      finding_id: finding.id,
      justification,
    });
    setLastJustification(justification);
    onRevoked();
    setSuppressOpen(true); // FP-B prompt
  };

  const handleSuppress = async () => {
    if (!finding.project_id) {
      setSuppressMsg('Không xác định được project — bỏ qua.');
      return;
    }
    setSuppressLoading(true);
    try {
      await api.projects.addSuppression(finding.project_id, {
        rule_id: finding.rule_id,
        file_glob: finding.file_path || null,
        tool: finding.tool,
        reason: `Suppression từ FP marker (finding #${finding.id}): ${lastJustification}`.slice(
          0,
          500
        ),
        expires_in_days: 90,
      });
      setSuppressMsg('Đã tạo rule. Các lần quét sau sẽ tự bỏ qua finding cùng pattern.');
      setTimeout(() => {
        setSuppressOpen(false);
        setSuppressMsg(null);
      }, 2500);
    } catch (e) {
      setSuppressMsg(`Lỗi: ${(e as Error).message}`);
      setSuppressLoading(false);
    }
  };

  const alreadyRevoked = finding.status === 'REVOKED';

  const SEV_FG: Record<string, string> = {
    critical: 'var(--sev-crit-fg)',
    high: 'var(--sev-high-fg)',
    medium: 'var(--sev-med-fg)',
    low: 'var(--sev-low-fg)',
    info: 'var(--sev-info-fg)',
  };
  const SEV_BG: Record<string, string> = {
    critical: 'var(--sev-crit-bg)',
    high: 'var(--sev-high-bg)',
    medium: 'var(--sev-med-bg)',
    low: 'var(--sev-low-bg)',
    info: 'var(--sev-info-bg)',
  };
  const sevFg = SEV_FG[finding.severity] ?? 'var(--fg-3)';
  const sevBg = SEV_BG[finding.severity] ?? 'var(--bg-muted)';

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: showAI ? 'minmax(0,1fr) 360px' : '1fr',
        height: '100%',
        minHeight: 0,
      }}
    >
      <div style={{ overflowY: 'auto', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        {/* Severity accent header */}
        <div style={{ background: sevBg, flexShrink: 0 }}>
          <div style={{ height: 4, background: sevFg }} />
          <div
            style={{
              padding: '18px 28px 16px',
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <SevChip sev={finding.severity} />
                <span className="tool-tag">{finding.tool}</span>
                {!depScan && finding.cwe_id && <span className="chip">{finding.cwe_id}</span>}
                {finding.status === 'ai_analyzed' && (
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
                {finding.status === 'APPROVED' && (
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
                {finding.status === 'REVOKED' && (
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
              </div>
              <h2 className="h2" style={{ lineHeight: 1.4 }}>
                {finding.message}
              </h2>
            </div>
            <div style={{ display: 'flex', gap: 8, flexShrink: 0, marginLeft: 12 }}>
              {!alreadyRevoked && (
                <button
                  className="btn sm"
                  onClick={() => setRevokeOpen(true)}
                  title="Đánh dấu finding này không phải lỗi thật. Các lần quét sau sẽ tự bỏ qua theo dedup_hash."
                >
                  <Icon name="shield" size={12} /> Đánh dấu không phải lỗi
                </button>
              )}
              <button className="btn sm" onClick={onToggleAI}>
                <Icon name="sparkle" size={12} /> {showAI ? 'Hide AI' : 'Ask AI'}
              </button>
            </div>
          </div>
        </div>

        <RevokeDialog
          open={revokeOpen}
          findingId={finding.id}
          onClose={() => setRevokeOpen(false)}
          onConfirm={handleRevoke}
        />

        {/* V3.6 FP-B — post-revoke suppression shortcut */}
        {suppressOpen && (
          <div
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 1001,
              background: 'rgba(0,0,0,0.6)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            onClick={(e) => {
              if (e.target === e.currentTarget) setSuppressOpen(false);
            }}
          >
            <div
              style={{
                background: 'var(--bg-elev)',
                border: '1px solid var(--line)',
                borderRadius: 10,
                padding: '24px 28px',
                width: 480,
                maxWidth: '90vw',
                boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
              }}
            >
              <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>
                Tạo rule chặn future scans?
              </div>
              <div className="muted" style={{ fontSize: 12.5, marginBottom: 14, lineHeight: 1.5 }}>
                Đã đánh dấu finding #{finding.id} là không phải lỗi. Tạo thêm
                <strong> suppression rule </strong>để mọi finding cùng pattern ở các lần quét tiếp
                theo tự động bỏ qua (Tier 2 — pattern-based, khác với Tier 1 chỉ match dedup_hash
                chính xác).
              </div>
              <div
                style={{
                  background: 'var(--surface-2)',
                  border: '1px solid var(--line)',
                  borderRadius: 6,
                  padding: '10px 12px',
                  marginBottom: 14,
                  fontSize: 12,
                }}
              >
                <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '4px 12px' }}>
                  <span style={{ color: 'var(--fg-3)' }}>Rule:</span>
                  <span className="mono" style={{ wordBreak: 'break-all' }}>
                    {finding.rule_id}
                  </span>
                  <span style={{ color: 'var(--fg-3)' }}>File pattern:</span>
                  <span className="mono" style={{ wordBreak: 'break-all' }}>
                    {finding.file_path}
                  </span>
                  <span style={{ color: 'var(--fg-3)' }}>Tool:</span>
                  <span className="mono">{finding.tool}</span>
                  <span style={{ color: 'var(--fg-3)' }}>Hết hạn:</span>
                  <span>90 ngày (tự động)</span>
                </div>
              </div>
              {suppressMsg && (
                <div
                  style={{
                    fontSize: 12,
                    padding: '8px 12px',
                    marginBottom: 12,
                    borderRadius: 6,
                    background: suppressMsg.startsWith('Lỗi')
                      ? 'rgba(229,57,53,0.15)'
                      : 'rgba(67,160,71,0.15)',
                    color: suppressMsg.startsWith('Lỗi')
                      ? 'var(--sev-crit-fg)'
                      : 'var(--sev-low-fg)',
                  }}
                >
                  {suppressMsg}
                </div>
              )}
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button
                  className="btn"
                  onClick={() => setSuppressOpen(false)}
                  disabled={suppressLoading}
                >
                  Bỏ qua
                </button>
                <button
                  className="btn primary"
                  onClick={handleSuppress}
                  disabled={suppressLoading || !finding.project_id}
                >
                  {suppressLoading ? 'Đang tạo…' : 'Tạo rule'}
                </button>
              </div>
            </div>
          </div>
        )}

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
                    [
                      'Detected',
                      finding.normalized_at
                        ? new Date(finding.normalized_at).toLocaleString()
                        : null,
                    ],
                  ]
                : [
                    ['Rule', finding.rule_id],
                    [
                      'File',
                      `${finding.file_path}${finding.line_number ? `:${finding.line_number}` : ''}`,
                    ],
                    ['Tool', finding.tool],
                    ['Status', finding.status],
                    ['CWE', finding.cwe_id],
                    ['CVSS', finding.cvss_score != null ? String(finding.cvss_score) : null],
                    [
                      'Normalized',
                      finding.normalized_at
                        ? new Date(finding.normalized_at).toLocaleString()
                        : null,
                    ],
                  ]
              )
                .filter(([_k, v]) => v)
                .map(([k, v]) => (
                  <div key={k as string}>
                    <div style={{ color: 'var(--fg-3)', fontSize: 11, marginBottom: 2 }}>{k}</div>
                    <div className="mono" style={{ fontSize: 12, wordBreak: 'break-all' }}>
                      {v}
                    </div>
                  </div>
                ))}
            </div>
          </div>

          {!depScan && (owasp || cweName) && (
            <div className="card card-pad" style={{ marginBottom: 16 }}>
              {owasp && (
                <>
                  <div style={{ fontSize: 11, color: 'var(--fg-3)', marginBottom: 4 }}>
                    OWASP Top 10 2021
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{owasp}</div>
                </>
              )}
              {cweName && (
                <div style={{ fontSize: 12, color: 'var(--fg-3)', marginTop: owasp ? 4 : 0 }}>
                  {cweName}
                </div>
              )}
            </div>
          )}

          {(finding.approved_by || finding.revoked_by) && (
            <div className="card card-pad" style={{ marginBottom: 16 }}>
              <div
                style={{
                  fontSize: 11,
                  fontWeight: 600,
                  color: 'var(--fg-3)',
                  marginBottom: 8,
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                }}
              >
                Audit Trail
              </div>
              {finding.approved_by && (
                <div style={{ fontSize: 12, marginBottom: 6 }}>
                  <span style={{ color: 'var(--fg-3)' }}>Approved by </span>
                  <strong>{finding.approved_by}</strong>
                  {finding.approved_at && (
                    <span style={{ color: 'var(--fg-3)' }}>
                      {' '}
                      · {new Date(finding.approved_at).toLocaleString()}
                    </span>
                  )}
                  {finding.justification && (
                    <div style={{ marginTop: 4, fontStyle: 'italic', color: 'var(--fg-3)' }}>
                      "{finding.justification}"
                    </div>
                  )}
                </div>
              )}
              {finding.revoked_by && (
                <div style={{ fontSize: 12 }}>
                  <span style={{ color: 'var(--fg-3)' }}>Revoked by </span>
                  <strong>{finding.revoked_by}</strong>
                  {finding.revoked_at && (
                    <span style={{ color: 'var(--fg-3)' }}>
                      {' '}
                      · {new Date(finding.revoked_at).toLocaleString()}
                    </span>
                  )}
                  {finding.revoke_justification && (
                    <div style={{ marginTop: 4, fontStyle: 'italic', color: 'var(--fg-3)' }}>
                      "{finding.revoke_justification}"
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {showAI && <AiPanel finding={finding} onClose={onToggleAI} />}
    </div>
  );
}
