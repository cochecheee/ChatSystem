import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Icon } from './Icon';
import { MiniMarkdown } from './MiniMarkdown';

type SeverityKey = 'critical' | 'high' | 'medium';

interface Risk {
  severity: SeverityKey;
  rule_id: string;
  file_path: string;
  one_line_reason: string;
  finding_id: number;
}

interface AiSummary {
  project_id: number | null;
  run_id: number | null;
  generated_at: string;
  cached: boolean;
  cache_ttl_remaining: number;
  model: string;
  overview_md: string;
  top_risks: Risk[];
  recommendations_md: string;
  pipeline_health: {
    runs_total: number;
    runs_passed: number;
    pass_rate_pct: number;
    trend: 'improving' | 'stable' | 'degrading';
  };
}

interface Props {
  projectId?: number;
  onOpenFinding?: (id: number) => void;
}

const SEV_COLOR: Record<SeverityKey, string> = {
  critical: 'var(--sev-crit-fg, #ff4757)',
  high: 'var(--sev-high-fg, #ff7e36)',
  medium: 'var(--sev-med-fg, #f0c038)',
};

const SEV_DOT: Record<SeverityKey, string> = {
  critical: '●●',
  high: '●',
  medium: '◐',
};

const TREND_BADGE: Record<string, { label: string; cls: string; icon: string }> = {
  improving: { label: 'Improving', cls: 'kpi-delta-down', icon: '↗' },
  stable: { label: 'Stable', cls: 'muted', icon: '→' },
  degrading: { label: 'Degrading', cls: 'kpi-delta-up', icon: '↘' },
};

/**
 * V3.3 Part B — Gemini-generated risk briefing card.
 * 4 sections in one card: Overview / Top Risks (click-through) /
 * Recommendations / Pipeline Health. Shows cache age in footer.
 */
export function OverviewAiSummary({ projectId, onOpenFinding }: Props) {
  const [data, setData] = useState<AiSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const load = async (force = false) => {
    setLoading(true);
    setError('');
    try {
      const r = await api.findings.aiSummary({
        project_id: projectId,
        force_refresh: force,
      });
      setData(r);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  if (loading && !data) return <SummarySkeleton />;
  if (error && !data) return <SummaryError error={error} onRetry={() => load(true)} />;
  if (!data) return null;

  const trend = TREND_BADGE[data.pipeline_health.trend] ?? TREND_BADGE.stable;
  const generatedAgo = formatAge(data.generated_at);

  return (
    <div className="card" style={{
      marginBottom: 16,
      border: '1px solid var(--line)',
      borderRadius: 10,
      background: 'var(--bg-elev)',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '12px 18px',
        borderBottom: '1px solid var(--line)',
        background: 'linear-gradient(90deg, rgba(108,99,255,0.08), transparent)',
      }}>
        <div className="ai-orb" style={{ width: 28, height: 28, flexShrink: 0 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 13.5 }}>Project Risk Posture</div>
          <div className="muted" style={{ fontSize: 11, marginTop: 1 }}>
            {data.project_id ? `Project #${data.project_id}` : 'All projects'}
            {data.run_id ? ` · run #${data.run_id}` : ''}
            {' · '}{generatedAgo}
            {data.cached && (
              <span style={{ marginLeft: 6 }}>
                · <code className="mono" style={{ fontSize: 10 }}>cached {data.cache_ttl_remaining}s</code>
              </span>
            )}
          </div>
        </div>
        <button
          className="btn ghost sm"
          style={{ padding: '4px 8px', fontSize: 11 }}
          onClick={() => load(true)}
          disabled={loading}
          title="Regenerate summary (skip cache)"
        >
          <span style={{ display: 'inline-block', animation: loading ? 'spin 1s linear infinite' : 'none' }}>⟳</span>
          {' '}Refresh
        </button>
      </div>

      <div style={{ padding: '14px 18px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        <Section icon="📊" title="Overview">
          <MiniMarkdown text={data.overview_md} />
        </Section>

        {data.top_risks.length > 0 && (
          <Section icon="🚨" title="Top Risks" badge={`${data.top_risks.length} of ${data.top_risks.length}`}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {data.top_risks.map((r) => (
                <RiskRow key={r.finding_id} risk={r} onClick={() => onOpenFinding?.(r.finding_id)} />
              ))}
            </div>
          </Section>
        )}

        <Section icon="💡" title="Recommended Actions">
          <MiniMarkdown text={data.recommendations_md} />
        </Section>

        <Section icon="📈" title="Pipeline Health" inline>
          <span>
            <strong>{data.pipeline_health.runs_passed}</strong>
            {' / '}
            <strong>{data.pipeline_health.runs_total}</strong>
            {' pass'}
            {' ('}{data.pipeline_health.pass_rate_pct}%{')'}
          </span>
          <span className={trend.cls} style={{ marginLeft: 12, fontSize: 11.5 }}>
            {trend.icon} {trend.label}
          </span>
        </Section>
      </div>

      <div style={{
        padding: '6px 18px', fontSize: 10.5,
        borderTop: '1px solid var(--line)',
        color: 'var(--fg-4)', textAlign: 'right',
      }}>
        Generated by <code className="mono">{data.model}</code> · in-memory cache · TTL up to 10 min
      </div>
    </div>
  );
}

function Section({
  icon, title, badge, inline = false, children,
}: {
  icon: string; title: string; badge?: string; inline?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        fontSize: 11.5, fontWeight: 600, color: 'var(--fg-2)',
        marginBottom: inline ? 0 : 6,
        textTransform: 'uppercase', letterSpacing: '0.04em',
      }}>
        <span style={{ fontSize: 14 }}>{icon}</span>
        <span>{title}</span>
        {badge && (
          <span className="chip" style={{ fontSize: 10, padding: '1px 6px' }}>{badge}</span>
        )}
        {inline && <div style={{ flex: 1 }} />}
        {inline && children}
      </div>
      {!inline && <div style={{ fontSize: 12.5, color: 'var(--fg-1)' }}>{children}</div>}
    </div>
  );
}

function RiskRow({ risk, onClick }: { risk: Risk; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 10,
        padding: '8px 10px',
        background: 'var(--surface-2)',
        border: '1px solid var(--line)',
        borderRadius: 6,
        textAlign: 'left',
        cursor: 'pointer',
        color: 'inherit',
        font: 'inherit',
      }}
      title={`Open finding #${risk.finding_id}`}
    >
      <span style={{
        color: SEV_COLOR[risk.severity],
        fontSize: 13, lineHeight: 1, flexShrink: 0, marginTop: 2,
        fontFamily: 'monospace',
      }}>
        {SEV_DOT[risk.severity]}
      </span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          fontSize: 11.5, display: 'flex', gap: 8, alignItems: 'baseline',
          fontFamily: 'var(--font-mono)',
        }}>
          <span style={{ color: SEV_COLOR[risk.severity], fontWeight: 600, textTransform: 'uppercase' }}>
            {risk.severity}
          </span>
          <code className="mono" style={{ background: 'var(--bg-1)', padding: '0 4px', borderRadius: 3 }}>
            {risk.rule_id}
          </code>
          <span className="muted" style={{
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
          }}>
            {risk.file_path}
          </span>
        </div>
        <div style={{ fontSize: 12, marginTop: 3, color: 'var(--fg-1)' }}>
          {risk.one_line_reason}
        </div>
      </div>
      <Icon name="chevron_right" size={11} style={{ color: 'var(--fg-3)', flexShrink: 0, marginTop: 4 }} />
    </button>
  );
}

function SummarySkeleton() {
  return (
    <div className="card" style={{
      marginBottom: 16, padding: '20px 18px',
      border: '1px solid var(--line)', borderRadius: 10, background: 'var(--bg-elev)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
        <div className="ai-orb" style={{ width: 28, height: 28 }} />
        <div className="muted" style={{ fontSize: 12 }}>Generating AI risk briefing…</div>
      </div>
      {[80, 95, 60].map((w, i) => (
        <div key={i} style={{
          height: 10, background: 'var(--surface-2)',
          borderRadius: 4, marginBottom: 6, width: `${w}%`,
          animation: 'pulse 1.4s ease-in-out infinite',
        }} />
      ))}
    </div>
  );
}

function SummaryError({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div className="card" style={{
      marginBottom: 16, padding: '12px 16px',
      border: '1px solid var(--sev-high-fg)', borderRadius: 10,
      background: 'var(--bg-elev)',
      display: 'flex', alignItems: 'center', gap: 10,
    }}>
      <Icon name="alert" size={14} style={{ color: 'var(--sev-high-fg)' }} />
      <div style={{ flex: 1, fontSize: 12, color: 'var(--sev-high-fg)' }}>
        AI summary unavailable: {error}
      </div>
      <button className="btn ghost sm" onClick={onRetry} style={{ padding: '3px 8px', fontSize: 11 }}>
        Retry
      </button>
    </div>
  );
}

function formatAge(iso: string): string {
  try {
    const diff = Date.now() - new Date(iso).getTime();
    const s = Math.floor(diff / 1000);
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}
