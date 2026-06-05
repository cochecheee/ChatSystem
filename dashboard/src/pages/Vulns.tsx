import { useState } from 'react';
import { Icon } from '../components/Icon';
import { AiTriageModal } from '../components/AiTriageModal';
import { useOverviewStats } from '../features/findings/useStats';
import { useVulnsFindings } from '../features/findings/useVulnsFindings';
import { FindingDetail } from '../features/findings/FindingDetail';
import { DEP_SCAN_TOOLS, SevChip } from '../features/findings/sast';
import { flagFalsePositive } from '../features/findings/flagFalsePositive';
import { useResizableSplit } from '../hooks/useResizableSplit';
import { POLL_INTERVAL_MS } from '../lib/constants';
import type { Finding } from '../types';

export function PageVulns({ initialId }: { initialId?: number }) {
  // Vulns page = SAST findings only. Dependencies → SCA page.
  const {
    PAGE_SIZE,
    findings,
    total,
    totalPages,
    page,
    setPage,
    loading,
    projects,
    projectFilter,
    setProjectFilter,
    sevFilter,
    setSevFilter,
    statusFilter,
    setStatusFilter,
    toolFilter,
    setToolFilter,
    search,
    setSearch,
    selectedId,
    setSelectedId,
    selectedFinding,
    ambient,
    refetch,
  } = useVulnsFindings(initialId);

  const { stats } = useOverviewStats(POLL_INTERVAL_MS);
  const [showAI, setShowAI] = useState(true);
  const [triageOpen, setTriageOpen] = useState(false);
  const { containerRef, gridColumns, onResizerPointerDown } = useResizableSplit('vulns.listWidth');

  // Inline "flag as false positive" — 1-click revoke + Tier 2 suppression so
  // the next pipeline scan skips it. Backend keeps the security_lead+ gate.
  const [flaggingId, setFlaggingId] = useState<number | null>(null);
  const [flagNotice, setFlagNotice] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null);

  const handleFlag = async (f: Finding) => {
    setFlaggingId(f.id);
    setFlagNotice(null);
    try {
      await flagFalsePositive(f);
      setFlagNotice({
        kind: 'ok',
        text: `Đã flag finding #${f.id} là false positive — lần quét sau sẽ tự bỏ qua.`,
      });
      refetch();
    } catch (e) {
      setFlagNotice({ kind: 'err', text: `Không flag được #${f.id}: ${(e as Error).message}` });
    } finally {
      setFlaggingId(null);
    }
  };

  // Total SAST findings từ server stats (across all severity/status filter).
  let sastTotal = 0;
  for (const [tool, count] of Object.entries(stats?.by_tool ?? {})) {
    if (!DEP_SCAN_TOOLS.has(tool.toLowerCase())) sastTotal += count;
  }

  // Tools dropdown: chỉ SAST tools.
  const tools = Object.keys(stats?.by_tool ?? {})
    .filter((t) => !DEP_SCAN_TOOLS.has(t.toLowerCase()))
    .sort();

  // Severity counts cho summary bar — derive từ current page (sample).
  // Khi total > PAGE_SIZE và filter sev='all', đây là sample chứ không phải full;
  // nhưng trong practice user filter từng severity nên numbers phản ánh đúng phạm vi đang xem.
  const sevCounts = findings.reduce(
    (acc, f) => {
      acc[f.severity] = (acc[f.severity] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );

  const filtered = findings.slice();
  const selected = selectedFinding ?? filtered[0] ?? null;

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
          {/* Page header — SAST findings only (dependencies → SCA page) */}
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
              SAST findings
            </h2>
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
                  width: '100%',
                  padding: '5px 8px',
                  background: 'var(--bg-elev)',
                  border: '1px solid var(--line)',
                  borderRadius: 6,
                  color: 'var(--fg)',
                  fontSize: 11.5,
                  outline: 'none',
                  font: 'inherit',
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

          {/* Search */}
          <div style={{ padding: '8px 12px 6px', flexShrink: 0 }}>
            <div className="search-box" style={{ width: '100%' }}>
              <Icon name="search" size={13} />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Rule, file, message…"
              />
            </div>
          </div>

          {/* Severity summary bar */}
          {!loading && findings.length > 0 && (
            <div className="sev-summary-bar">
              {(['critical', 'high', 'medium', 'low'] as const).map((sev) => {
                const cnt = sevCounts[sev] ?? 0;
                if (cnt === 0) return null;
                return (
                  <button
                    key={sev}
                    className={`sev-summary-chip sev-${sev}${sevFilter === sev ? ' active' : ''}`}
                    onClick={() => setSevFilter((prev) => (prev === sev ? 'all' : sev))}
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
                <select
                  value={toolFilter}
                  onChange={(e) => setToolFilter(e.target.value)}
                  title="Filter by tool"
                >
                  <option value="all">All tools</option>
                  {tools.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <span className="tb-sep" />
              </>
            )}
            {(
              [
                ['all', 'All'],
                ['pending', 'Pending'],
                ['analyzed', 'AI'],
                ['approved', 'OK'],
                ['revoked', 'Revoked'],
              ] as [string, string][]
            ).map(([v, l]) => (
              <button
                key={v}
                className={`tb-pill${statusFilter === v ? ' active' : ''}`}
                onClick={() => setStatusFilter(v)}
              >
                {l}
              </button>
            ))}
          </div>

          {/* Pagination header — chỉ hiển thị khi total > PAGE_SIZE */}
          {!loading && total > PAGE_SIZE && (
            <div
              style={{
                padding: '6px 14px',
                borderBottom: '1px solid var(--line)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: 11,
                color: 'var(--fg-3)',
                flexShrink: 0,
              }}
            >
              <span>
                Showing{' '}
                <span className="mono">
                  {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)}
                </span>{' '}
                of <span className="mono">{total}</span>
              </span>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  className="btn ghost sm"
                  style={{ padding: '2px 8px', fontSize: 11 }}
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
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
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                >
                  Next →
                </button>
              </div>
            </div>
          )}

          {/* Flag-as-FP result notice */}
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

          {/* Finding list */}
          <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
            {loading && <div className="empty">Loading…</div>}
            {!loading && filtered.length === 0 && (
              <div className="empty">
                {total === 0 ? 'No SAST findings found' : 'No findings match filters'}
              </div>
            )}

            {filtered.map((f) => (
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
                  <span className="tool-tag" style={{ flexShrink: 0 }}>
                    {f.tool}
                  </span>
                  <span
                    className="mono"
                    style={{
                      fontSize: 10.5,
                      flex: 1,
                      minWidth: 0,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {f.file_path.split('/').pop()}
                    {f.line_number ? `:${f.line_number}` : ''}
                  </span>
                  {f.status === 'ai_analyzed' && (
                    <Icon
                      name="sparkle"
                      size={11}
                      style={{ color: 'var(--accent)', flexShrink: 0 }}
                    />
                  )}
                  {f.status === 'APPROVED' && <span className="row-status-badge approved">OK</span>}
                  {f.status === 'REVOKED' && <span className="row-status-badge revoked">Rev</span>}
                  {f.status !== 'REVOKED' && (
                    <button
                      className="btn ghost sm"
                      style={{ padding: '2px 5px', flexShrink: 0 }}
                      title="Đánh dấu false positive — lần quét sau tự bỏ qua (cần quyền security_lead+)"
                      disabled={flaggingId === f.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleFlag(f);
                      }}
                    >
                      <Icon name={flaggingId === f.id ? 'refresh' : 'shield'} size={12} />
                    </button>
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
            <FindingDetail
              finding={selected}
              showAI={showAI}
              onToggleAI={() => setShowAI((s) => !s)}
              onRevoked={refetch}
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
        projectId={projectFilter !== 'all' ? (projectFilter as number) : ambient.project_id}
        onTriaged={refetch}
      />
    </div>
  );
}
