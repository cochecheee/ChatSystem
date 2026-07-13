import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { POLL_INTERVAL_MS } from '../lib/constants';
import { useActiveProjectParam } from '../contexts/ProjectContext';
import { Icon } from '../components/Icon';
import { DedupSummary } from '../components/DedupSummary';
import { SevChip } from '../features/findings/sast';
import type { PageId } from '../components/Shell';
import type { AiStats, DedupStats, SeverityStats } from '../types';

interface Props {
  onNav: (id: PageId) => void;
  onOpenVuln?: (id: number) => void;
}

interface GateStats {
  critical: number;
  high: number;
  medium: number;
  low: number;
  pass?: boolean | null;
  policy?: { critical_threshold: number; high_threshold: number } | null;
}

type StageKey = 'raw' | 'normalize' | 'dedup' | 'ai' | 'unique' | 'gate';

const ACCENT = 'var(--accent, #6c63ff)';

function Stat({ label, value, color }: { label: string; value: number | string; color?: string }) {
  return (
    <div style={{ minWidth: 90 }}>
      <div className="mono" style={{ fontSize: 20, fontWeight: 700, color: color ?? 'inherit' }}>
        {value}
      </div>
      <div className="muted" style={{ fontSize: 11 }}>
        {label}
      </div>
    </div>
  );
}

/**
 * V4.1 — "Xử lý dữ liệu" (Processing): visualizes the ingest pipeline as a flow
 * Raw → Chuẩn hoá severity → Khử trùng lặp → Unique → Gate, with counts at each
 * transition and click-to-expand drill-downs (promoted findings, dedup clusters).
 * Data: /findings/severity-stats + /findings/dedup-stats + /findings/gate-count.
 */
export function PageProcessing({ onNav, onOpenVuln }: Props) {
  const { project_id } = useActiveProjectParam();
  const [sev, setSev] = useState<SeverityStats | null>(null);
  const [dedup, setDedup] = useState<DedupStats | null>(null);
  const [gate, setGate] = useState<GateStats | null>(null);
  const [ai, setAi] = useState<AiStats | null>(null);
  const [open, setOpen] = useState<StageKey>('normalize');

  useEffect(() => {
    let alive = true;
    const load = () => {
      api.findings
        .severityStats({ project_id, top: 20 })
        .then((r) => alive && setSev(r))
        .catch(() => {});
      api.findings
        .dedupStats({ project_id, top: 12 })
        .then((r) => alive && setDedup(r))
        .catch(() => {});
      api.findings
        .gateCount({ project_id })
        .then((r) => alive && setGate(r as unknown as GateStats))
        .catch(() => {});
      api.findings
        .aiStats({ project_id, top: 15 })
        .then((r) => alive && setAi(r))
        .catch(() => {});
    };
    load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [project_id]);

  const rawEst = dedup?.raw_findings_estimate ?? sev?.total ?? 0;
  const crossRemoved = dedup?.cross_tool_duplicates_removed ?? 0;
  const unique = dedup?.unique_findings ?? sev?.total ?? 0;
  const gateTotal = gate ? gate.critical + gate.high : 0;

  const stages: { key: StageKey; label: string; value: number; sub: string; icon: string; tint?: string }[] = [
    { key: 'raw', label: 'Raw (từ tools)', value: rawEst, sub: 'mọi finding tool báo', icon: 'package' },
    {
      key: 'normalize',
      label: 'Chuẩn hoá severity',
      value: sev?.promoted ?? 0,
      sub: `${sev?.promoted ?? 0} đổi bậc · ${sev?.disagreements ?? 0} lệch nhãn/điểm`,
      icon: 'filter',
      tint: ACCENT,
    },
    {
      key: 'dedup',
      label: 'Khử trùng lặp',
      value: crossRemoved,
      sub: `cross-tool −${crossRemoved} · ${dedup?.multi_tool_clusters ?? 0} cụm`,
      icon: 'layers',
      tint: 'var(--sev-high-fg, #ff7e36)',
    },
    {
      key: 'ai',
      label: 'AI: FP + grounding',
      value: ai?.fp_likelihood?.HIGH ?? 0,
      sub: `${ai?.fp_likelihood?.HIGH ?? 0} nghi FP · ${ai?.ungrounded ?? 0} fix chưa neo`,
      icon: 'brain',
      tint: ACCENT,
    },
    { key: 'unique', label: 'Unique', value: unique, sub: '= số ở KPI/lists', icon: 'shield', tint: 'var(--sev-low-fg, #35c07a)' },
    {
      key: 'gate',
      label: 'Security Gate',
      value: gateTotal,
      sub: `crit ${gate?.critical ?? 0} · high ${gate?.high ?? 0}`,
      icon: 'target',
    },
  ];

  const noProv = sev != null && sev.with_provenance === 0 && sev.total > 0;

  return (
    <div className="content">
      <div className="page-header">
        <div>
          <h1 className="h1">Xử lý dữ liệu</h1>
          <div className="sub">
            Quy trình chuẩn hoá & khử trùng lặp: raw → chuẩn hoá severity → dedup → kết quả → gate
          </div>
        </div>
      </div>

      {noProv && (
        <div
          className="card card-pad"
          style={{ marginBottom: 16, borderLeft: '3px solid var(--sev-med-fg, #f0c038)' }}
        >
          <b>Chưa có dữ liệu chuẩn hoá severity.</b>{' '}
          <span className="muted">
            Các finding hiện có được ingest trước V4.1 (không có provenance). Chạy lại 1 lần scan
            (re-ingest) để populate — dedup vẫn hiển thị bình thường bên dưới.
          </span>
        </div>
      )}

      {/* Pipeline flow */}
      <div
        style={{
          display: 'flex',
          alignItems: 'stretch',
          gap: 6,
          overflowX: 'auto',
          paddingBottom: 8,
          marginBottom: 16,
        }}
      >
        {stages.map((st, i) => (
          <div key={st.key} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <button
              onClick={() => setOpen(st.key)}
              className="card"
              style={{
                minWidth: 150,
                textAlign: 'left',
                padding: '12px 14px',
                borderRadius: 10,
                cursor: 'pointer',
                border: open === st.key ? `1px solid ${ACCENT}` : '1px solid var(--line)',
                background: open === st.key ? 'var(--bg-2, rgba(108,99,255,0.06))' : 'var(--bg-elev)',
              }}
            >
              <div
                style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}
                className="muted"
              >
                <Icon name={st.icon} size={13} />
                <span style={{ fontSize: 11.5 }}>{st.label}</span>
              </div>
              <div className="mono" style={{ fontSize: 24, fontWeight: 700, color: st.tint ?? 'inherit' }}>
                {st.value}
              </div>
              <div className="muted" style={{ fontSize: 10.5, marginTop: 2 }}>
                {st.sub}
              </div>
            </button>
            {i < stages.length - 1 && (
              <span className="muted" style={{ fontSize: 18 }}>
                →
              </span>
            )}
          </div>
        ))}
      </div>

      {/* Drill-down panel */}
      {open === 'raw' && (
        <div className="card card-pad">
          <div className="muted" style={{ fontSize: 11, marginBottom: 8 }}>
            Số finding thô theo tool (trước khi chuẩn hoá & khử trùng)
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {Object.entries(sev?.by_tool ?? {}).map(([t, v]) => (
              <span key={t} className="tool-tag">
                {t}: <b>{v.total}</b>
              </span>
            ))}
            {!sev && <span className="muted">Đang tải…</span>}
          </div>
        </div>
      )}

      {open === 'normalize' && (
        <div className="card card-pad">
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 12 }}>
            <Stat label="đổi bậc (promote)" value={sev?.promoted ?? 0} color={ACCENT} />
            <Stat label="nhãn ≠ điểm CVSS" value={sev?.disagreements ?? 0} />
            <Stat label="CVSS thật (tool)" value={sev?.cvss_real ?? 0} />
            <Stat label="CVSS ước lượng" value={sev?.cvss_derived ?? 0} />
            <Stat label="có provenance" value={`${sev?.with_provenance ?? 0}/${sev?.total ?? 0}`} />
          </div>
          <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
            Finding được nâng bậc (điểm CVSS / DAST cao hơn nhãn tool báo)
          </div>
          {(sev?.top_promoted ?? []).map((r) => (
            <div
              key={r.finding_id}
              onClick={() => onOpenVuln?.(r.finding_id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 0',
                borderBottom: '1px solid var(--line)',
                cursor: onOpenVuln ? 'pointer' : 'default',
              }}
            >
              <span className="tool-tag" style={{ flexShrink: 0 }}>
                {r.tool}
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
                title={r.file_path}
              >
                {r.file_path.split('/').pop()}
                {r.line_number ? `:${r.line_number}` : ''}
              </span>
              <span className="muted" style={{ fontSize: 11, flexShrink: 0 }}>
                {r.original_label ?? '?'}
                {r.cvss != null ? ` · CVSS ${r.cvss}${r.cvss_kind ? ` (${r.cvss_kind})` : ''}` : ''} →
              </span>
              <SevChip sev={r.normalized} />
            </div>
          ))}
          {sev != null && (sev.top_promoted?.length ?? 0) === 0 && (
            <div className="muted" style={{ fontSize: 12 }}>
              Không có finding nào bị nâng bậc trong lần quét này.
            </div>
          )}
        </div>
      )}

      {open === 'dedup' && <DedupSummary projectId={project_id} onOpenFinding={onOpenVuln} />}

      {open === 'ai' && (
        <div className="card card-pad">
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', marginBottom: 12 }}>
            <Stat label="đã phân tích AI" value={ai?.analyzed ?? 0} />
            <Stat label="nghi false positive" value={ai?.fp_likelihood?.HIGH ?? 0} color={ACCENT} />
            <Stat label="fix đã neo mã nguồn" value={ai?.grounded ?? 0} color="var(--sev-low-fg, #35c07a)" />
            <Stat label="fix chưa neo (nghi bịa)" value={ai?.ungrounded ?? 0} color="var(--sev-high-fg, #ff7e36)" />
            <Stat label="AI tự thu hồi" value={ai?.ai_revoked ?? 0} />
          </div>
          <div className="muted" style={{ fontSize: 11, marginBottom: 6 }}>
            Finding AI nghi là false positive — nên cân nhắc trước khi đào sâu để sửa
          </div>
          {(ai?.top_false_positive ?? []).map((r) => (
            <div
              key={r.finding_id}
              onClick={() => onOpenVuln?.(r.finding_id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '6px 0',
                borderBottom: '1px solid var(--line)',
                cursor: onOpenVuln ? 'pointer' : 'default',
              }}
            >
              <span className="tool-tag" style={{ flexShrink: 0 }}>
                {r.tool}
              </span>
              <span
                className="mono"
                style={{ flexShrink: 0, fontSize: 11 }}
                title={r.file_path}
              >
                {r.file_path.split('/').pop()}
                {r.line_number ? `:${r.line_number}` : ''}
              </span>
              <span className="muted" style={{ flex: 1, minWidth: 0, fontSize: 11.5 }}>
                {r.reason || '(không rõ lý do)'}
              </span>
            </div>
          ))}
          {ai != null && (ai.top_false_positive?.length ?? 0) === 0 && (
            <div className="muted" style={{ fontSize: 12 }}>
              Chưa có finding nào AI nghi là false positive (hoặc chưa phân tích AI).
            </div>
          )}
        </div>
      )}

      {open === 'unique' && (
        <div className="card card-pad">
          <div style={{ fontSize: 13, marginBottom: 8 }}>
            <b>{unique}</b> finding duy nhất sau khi gộp — đây là con số mọi KPI, danh sách và report
            dùng (một nguồn sự thật).
          </div>
          <button className="btn" onClick={() => onNav('vulns')}>
            <Icon name="shield" /> Xem danh sách Vulnerabilities
          </button>
        </div>
      )}

      {open === 'gate' && (
        <div className="card card-pad">
          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap', alignItems: 'center' }}>
            <Stat label="critical (active)" value={gate?.critical ?? 0} color="var(--sev-crit-fg, #ff4757)" />
            <Stat label="high (active)" value={gate?.high ?? 0} color="var(--sev-high-fg, #ff7e36)" />
            {gate?.pass != null && (
              <span
                className={`chip ${gate.pass ? 'status-passed' : 'status-failed'}`}
                style={{ fontSize: 12 }}
              >
                {gate.pass ? 'GATE PASS' : 'GATE FAIL'}
              </span>
            )}
          </div>
          <div className="muted" style={{ fontSize: 11, marginTop: 8 }}>
            Gate chỉ đếm rủi ro còn hiệu lực (loại REVOKED/APPROVED). Số này đã phản ánh severity đã
            chuẩn hoá + đã khử trùng lặp.
          </div>
        </div>
      )}
    </div>
  );
}
