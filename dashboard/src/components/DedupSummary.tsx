import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { POLL_INTERVAL_MS } from '../lib/constants';
import { SevChip } from '../features/findings/sast';
import type { DedupStats } from '../types';

interface Props {
  projectId?: number;
  onOpenFinding?: (id: number) => void;
}

function Bar({ value, total, color, label }: { value: number; total: number; color: string; label: string }) {
  const pct = total > 0 ? Math.round((100 * value) / total) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
      <div className="muted" style={{ width: 150, fontSize: 11.5, flexShrink: 0 }}>
        {label}
      </div>
      <div
        style={{
          flex: 1,
          height: 12,
          borderRadius: 6,
          background: 'var(--bg-2, rgba(0,0,0,0.06))',
          overflow: 'hidden',
        }}
      >
        <div style={{ width: `${pct}%`, height: '100%', background: color, transition: 'width .3s' }} />
      </div>
      <div className="mono" style={{ width: 34, textAlign: 'right', fontWeight: 600, fontSize: 12 }}>
        {value}
      </div>
    </div>
  );
}

/**
 * V4.0 — cross-tool deduplication card. Shows the funnel (raw findings across
 * all tools → unique after collapsing the same vulnerability reported by
 * multiple tools) plus the top corroborated clusters. Data comes from
 * /findings/dedup-stats, reconstructed from each keeper's raw_data._correlation.
 */
export function DedupSummary({ projectId, onOpenFinding }: Props) {
  const [data, setData] = useState<DedupStats | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    const load = () =>
      api.findings
        .dedupStats({ project_id: projectId, top: 8 })
        .then((r) => alive && setData(r))
        .catch((e) => alive && setError(String(e)));
    void load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [projectId]);

  if (error && !data) return null;
  if (!data || data.unique_findings === 0) return null;

  const { raw_findings_estimate, unique_findings, cross_tool_duplicates_removed, reduction_pct } = data;
  const contrib = Object.entries(data.by_tool_contribution);

  return (
    <div
      className="card"
      style={{
        marginBottom: 16,
        border: '1px solid var(--line)',
        borderRadius: 10,
        background: 'var(--bg-elev)',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '12px 18px',
          borderBottom: '1px solid var(--line)',
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 13.5 }}>Gộp lỗi trùng giữa các công cụ</div>
          <div className="muted" style={{ fontSize: 11, marginTop: 1 }}>
            {data.project_id ? `Dự án #${data.project_id}` : 'Tất cả dự án'}
            {data.run_id ? ` · lần chạy #${data.run_id}` : ''}
            {' · gộp cùng một lỗi được nhiều công cụ báo'}
          </div>
        </div>
        {cross_tool_duplicates_removed > 0 && (
          <span
            className="tool-tag"
            style={{ color: 'var(--accent)', borderColor: 'var(--accent)', fontWeight: 600 }}
            title="Tỉ lệ giảm số finding nhờ gộp cross-tool"
          >
            −{reduction_pct}%
          </span>
        )}
      </div>

      <div style={{ padding: '14px 18px' }}>
        <Bar
          label="Raw (mọi tool)"
          value={raw_findings_estimate}
          total={raw_findings_estimate}
          color="var(--fg-4, #999)"
        />
        <Bar
          label="Unique (đã gộp)"
          value={unique_findings}
          total={raw_findings_estimate}
          color="var(--accent, #6c63ff)"
        />
        <div className="muted" style={{ fontSize: 11.5, marginTop: 6 }}>
          Đã loại <b style={{ color: 'var(--sev-high-fg)' }}>{cross_tool_duplicates_removed}</b> bản
          trùng · <b>{data.multi_tool_clusters}</b> lỗi được nhiều tool cùng xác nhận
          {contrib.length > 0 && (
            <span style={{ marginLeft: 8 }}>
              {contrib.map(([t, n]) => (
                <span key={t} className="tool-tag" style={{ marginLeft: 4, fontSize: 10 }}>
                  {t} ×{n}
                </span>
              ))}
            </span>
          )}
        </div>

        {data.clusters.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
              Lỗi được nhiều tool xác nhận
            </div>
            {data.clusters.map((c) => (
              <div
                key={c.finding_id}
                onClick={() => onOpenFinding?.(c.finding_id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 8px',
                  borderRadius: 6,
                  cursor: onOpenFinding ? 'pointer' : 'default',
                  borderBottom: '1px solid var(--line)',
                }}
              >
                <SevChip sev={c.severity} />
                <span className="mono" style={{ fontSize: 11, flexShrink: 0 }}>
                  {c.cwe ?? '—'}
                </span>
                <span
                  className="mono"
                  style={{
                    flex: 1,
                    minWidth: 0,
                    fontSize: 11,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={c.file_path}
                >
                  {c.file_path.split('/').pop()}
                  {c.line_number ? `:${c.line_number}` : ''}
                </span>
                {c.tools.map((t) => (
                  <span
                    key={t}
                    className="tool-tag"
                    style={{
                      fontSize: 10,
                      flexShrink: 0,
                      ...(t === c.primary_tool
                        ? { color: 'var(--accent)', borderColor: 'var(--accent)' }
                        : {}),
                    }}
                    title={t === c.primary_tool ? `${t} (primary)` : t}
                  >
                    {t}
                  </span>
                ))}
                <span className="mono" style={{ fontSize: 11, fontWeight: 600, flexShrink: 0 }}>
                  ×{c.size}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
