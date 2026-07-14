import { useState } from 'react';
import { api } from '../api/client';
import { Icon } from './Icon';

interface Props {
  open: boolean;
  onClose: () => void;
  projectId: number | undefined;
  /** Called after successful triage so the parent can refresh its list. */
  onTriaged?: () => void;
}

type ResultRow = {
  finding_id: number;
  classification: string;
  confidence: number;
  reason: string;
  applied: boolean;
};

const COLOR: Record<string, string> = {
  TRUE_POSITIVE: 'var(--sev-high-fg, #f55)',
  FALSE_POSITIVE: 'var(--ok-fg, #4a4)',
  NEEDS_REVIEW: 'var(--fg-3)',
};

/**
 * V3.1 Tier 3 — "AI Triage" interactive modal. Two-step:
 *   1. Dry run → preview classification table (no DB writes)
 *   2. Apply → re-run with dry_run=false so high-confidence FP get REVOKED
 */
export function AiTriageModal({ open, onClose, projectId, onTriaged }: Props) {
  const [confidence, setConfidence] = useState(0.8);
  const [limit, setLimit] = useState(50);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ResultRow[] | null>(null);
  const [summary, setSummary] = useState<{
    total: number;
    auto_revoked: number;
    classifications?: Record<string, number>;
    dry_run: boolean;
  } | null>(null);
  const [error, setError] = useState('');

  if (!open) return null;

  const run = async (dry: boolean) => {
    setError('');
    setLoading(true);
    try {
      const r = await api.findings.triage({
        project_id: projectId,
        confidence_threshold: confidence,
        dry_run: dry,
        limit,
      });
      setResults(r.items as ResultRow[]);
      setSummary({
        total: r.total,
        auto_revoked: r.auto_revoked,
        classifications: r.classifications,
        dry_run: r.dry_run,
      });
      if (!dry) onTriaged?.();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 900,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.55)',
        backdropFilter: 'blur(3px)',
      }}
    >
      <div
        style={{
          background: 'var(--bg-elev)',
          border: '1px solid var(--line)',
          borderRadius: 10,
          width: 720,
          maxHeight: '85vh',
          overflow: 'auto',
          padding: '20px 24px',
          position: 'relative',
        }}
      >
        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            top: 10,
            right: 14,
            background: 'transparent',
            border: 'none',
            color: 'var(--fg-3)',
            fontSize: 20,
            cursor: 'pointer',
            padding: 4,
            lineHeight: 1,
          }}
        >
          ×
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
          <Icon name="sparkle" size={16} />
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Phân loại AI</div>
            <div className="muted" style={{ fontSize: 11.5 }}>
              AI tự động phân loại lỗi chờ duyệt là thật hay dương tính giả, và loại bỏ các lỗi
              dương tính giả có độ tin cậy cao.
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 12, marginBottom: 12, alignItems: 'end' }}>
          <div>
            <label style={labelStyle}>Confidence threshold</label>
            <input
              type="number"
              min={0.5}
              max={1.0}
              step={0.05}
              value={confidence}
              onChange={(e) => setConfidence(parseFloat(e.target.value) || 0.8)}
              style={inputStyle}
            />
          </div>
          <div>
            <label style={labelStyle}>Findings limit</label>
            <input
              type="number"
              min={1}
              max={500}
              value={limit}
              onChange={(e) => setLimit(parseInt(e.target.value) || 50)}
              style={inputStyle}
            />
          </div>
          <div style={{ flex: 1 }} />
          <button
            className="btn"
            style={{ padding: '6px 12px', fontSize: 12 }}
            disabled={loading}
            onClick={() => run(true)}
          >
            {loading ? 'Running…' : 'Dry run'}
          </button>
          <button
            className="btn primary"
            style={{ padding: '6px 12px', fontSize: 12 }}
            disabled={loading}
            onClick={() => run(false)}
          >
            {loading ? 'Applying…' : 'Apply revokes'}
          </button>
        </div>

        {error && <div style={{ color: 'var(--sev-high-fg)', fontSize: 12 }}>{error}</div>}

        {summary && (
          <div
            style={{
              marginTop: 12,
              padding: '8px 12px',
              background: 'var(--surface-2)',
              borderRadius: 6,
              fontSize: 12,
            }}
          >
            <strong>{summary.dry_run ? 'Preview' : 'Applied'}</strong>: classified{' '}
            <strong>{summary.total}</strong> findings · auto-revoked{' '}
            <strong>{summary.auto_revoked}</strong>
            {summary.classifications && (
              <span style={{ marginLeft: 10, color: 'var(--fg-3)' }}>
                {Object.entries(summary.classifications)
                  .map(([k, v]) => `${k}=${v}`)
                  .join(' · ')}
              </span>
            )}
          </div>
        )}

        {results && results.length > 0 && (
          <div style={{ marginTop: 12, maxHeight: '50vh', overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--line)' }}>
                  <th style={th}>id</th>
                  <th style={th}>classification</th>
                  <th style={th}>conf</th>
                  <th style={th}>reason</th>
                  <th style={th}>applied</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => (
                  <tr key={r.finding_id} style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={td}>{r.finding_id}</td>
                    <td style={{ ...td, color: COLOR[r.classification] || 'inherit' }}>
                      {r.classification}
                    </td>
                    <td style={td}>{r.confidence.toFixed(2)}</td>
                    <td style={{ ...td, fontSize: 11 }}>{r.reason}</td>
                    <td style={td}>
                      {r.applied ? (
                        <Icon name="check" size={12} />
                      ) : (
                        <span className="muted">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: 11,
  color: 'var(--fg-3)',
  marginBottom: 4,
};
const inputStyle: React.CSSProperties = {
  padding: '6px 10px',
  fontSize: 12,
  width: 120,
  background: 'var(--bg-muted)',
  color: 'var(--fg)',
  border: '1px solid var(--line)',
  borderRadius: 4,
};
const th: React.CSSProperties = {
  textAlign: 'left',
  padding: '6px 8px',
  fontWeight: 500,
  color: 'var(--fg-3)',
};
const td: React.CSSProperties = { padding: '6px 8px', verticalAlign: 'top' };
