import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Icon } from './Icon';

interface Rule {
  id: number;
  rule_id: string | null;
  file_glob: string | null;
  tool: string | null;
  severity_max: string | null;
  reason: string;
  created_by: string;
  created_at: string;
  expires_at: string | null;
}

/**
 * V3.1 Tier 2 — inline manager for a project's suppression rules.
 * Mirrors ProjectMembers UX: collapsible panel inside the Settings project
 * card, list + add form. Rule scope (rule_id / file_glob / tool / severity_max)
 * empty means "any". Default 90-day expiry to prevent shadow rules.
 */
export function ProjectSuppressions({ projectId }: { projectId: number }) {
  const [open, setOpen] = useState(false);
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [ruleId, setRuleId] = useState('');
  const [fileGlob, setFileGlob] = useState('');
  const [tool, setTool] = useState('');
  const [sevMax, setSevMax] = useState<'' | 'low' | 'medium' | 'high' | 'critical'>('');
  const [reason, setReason] = useState('');
  const [ttlDays, setTtlDays] = useState(90);

  const refresh = async () => {
    setLoading(true);
    setError('');
    try {
      setRules(await api.projects.listSuppressions(projectId));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId]);

  const handleAdd = async () => {
    if (!reason.trim()) {
      setError('Reason là bắt buộc');
      return;
    }
    setError('');
    try {
      await api.projects.addSuppression(projectId, {
        reason: reason.trim(),
        rule_id: ruleId.trim() || null,
        file_glob: fileGlob.trim() || null,
        tool: tool.trim() || null,
        severity_max: sevMax || null,
        expires_in_days: ttlDays || null,
      });
      setReason('');
      setRuleId('');
      setFileGlob('');
      setTool('');
      setSevMax('');
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm(`Xoá suppression rule #${id}?`)) return;
    try {
      await api.projects.deleteSuppression(projectId, id);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  if (!open) {
    return (
      <button
        className="btn ghost sm"
        style={{ padding: '4px 8px', fontSize: 11 }}
        onClick={() => setOpen(true)}
        title="Manage suppression rules"
      >
        <Icon name="shield" size={12} /> Suppressions
      </button>
    );
  }

  return (
    <div
      style={{
        width: '100%',
        padding: '8px 12px',
        marginTop: 8,
        background: 'var(--surface-2)',
        borderRadius: 6,
        border: '1px solid var(--line)',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong style={{ fontSize: 12 }}>Suppression rules ({rules.length})</strong>
        <button
          className="btn ghost sm"
          style={{ padding: '2px 6px', fontSize: 10 }}
          onClick={() => setOpen(false)}
        >
          Close
        </button>
      </div>
      {loading && (
        <div className="muted" style={{ fontSize: 11 }}>
          Loading…
        </div>
      )}
      {error && <div style={{ color: 'var(--danger, #f55)', fontSize: 11 }}>{error}</div>}
      {rules.length === 0 && !loading && (
        <div className="muted" style={{ fontSize: 11 }}>
          No active rules. Add one below.
        </div>
      )}
      {rules.map((r) => (
        <div
          key={r.id}
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 8,
            fontSize: 12,
            padding: '4px 0',
            borderTop: '1px solid var(--line)',
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="mono" style={{ fontSize: 11 }}>
              {[
                r.rule_id && `rule=${r.rule_id}`,
                r.tool && `tool=${r.tool}`,
                r.file_glob && `glob=${r.file_glob}`,
                r.severity_max && `sev≤${r.severity_max}`,
              ]
                .filter(Boolean)
                .join(' · ') || '(catch-all)'}
            </div>
            <div className="muted" style={{ fontSize: 10.5 }}>
              {r.reason} · by <code>{r.created_by}</code>
              {r.expires_at && ` · expires ${new Date(r.expires_at).toLocaleDateString()}`}
            </div>
          </div>
          <button
            className="btn ghost sm"
            style={{ padding: '2px 6px', fontSize: 10 }}
            onClick={() => handleDelete(r.id)}
            title="Delete rule"
          >
            <Icon name="trash" size={10} />
          </button>
        </div>
      ))}

      <div
        style={{
          marginTop: 8,
          paddingTop: 8,
          borderTop: '1px dashed var(--line)',
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 6,
          fontSize: 11,
        }}
      >
        <input
          placeholder="Mã quy tắc (vd java/path-injection)"
          value={ruleId}
          onChange={(e) => setRuleId(e.target.value)}
          style={inputStyle}
        />
        <input
          placeholder="Đường dẫn file (vd src/test/**)"
          value={fileGlob}
          onChange={(e) => setFileGlob(e.target.value)}
          style={inputStyle}
        />
        <input
          placeholder="Công cụ (vd semgrep)"
          value={tool}
          onChange={(e) => setTool(e.target.value)}
          style={inputStyle}
        />
        <select
          value={sevMax}
          onChange={(e) => setSevMax(e.target.value as typeof sevMax)}
          style={inputStyle}
        >
          <option value="">severity_max: any</option>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
          <option value="critical">critical</option>
        </select>
        <input
          placeholder="Reason (required)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void handleAdd();
          }}
          style={{ ...inputStyle, gridColumn: 'span 2' }}
        />
        <input
          type="number"
          min={0}
          placeholder="TTL days (0 = permanent)"
          value={ttlDays}
          onChange={(e) => setTtlDays(parseInt(e.target.value) || 0)}
          style={inputStyle}
        />
        <button
          className="btn primary sm"
          style={{ padding: '4px 8px', fontSize: 11 }}
          onClick={handleAdd}
        >
          Add rule
        </button>
      </div>
      <div className="muted" style={{ fontSize: 10, marginTop: 4 }}>
        Empty field = "any". All non-empty fields must match a finding for it to auto-revoke.
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: '4px 8px',
  fontSize: 11,
  background: 'var(--bg-2)',
  color: 'var(--fg-1)',
  border: '1px solid var(--line)',
  borderRadius: 4,
};
