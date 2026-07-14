import type { FPInvestigation, InvestigationStep } from '../../types';

// V4.3 — renders the chat "lỗi này có thật không?" investigation: a verdict
// badge + short summary + step-by-step data-flow reasoning where each step
// cites a real code snippet (with line numbers) and a per-step grounding badge.
// Reuses the FP amber-callout + grounding-badge + code-block visual grammar
// from FindingDetail's AiPanel.

const VERDICT_META: Record<
  string,
  { label: string; bg: string; fg: string; icon: string }
> = {
  FALSE_POSITIVE: {
    label: 'Khả năng là dương tính giả',
    bg: 'var(--sev-med-bg, rgba(240,192,56,0.12))',
    fg: 'var(--sev-med-fg, #f0c038)',
    icon: '⚠️',
  },
  TRUE_POSITIVE: {
    label: 'Lỗi thật',
    bg: 'var(--sev-high-bg, rgba(255,126,54,0.12))',
    fg: 'var(--sev-high-fg, #ff7e36)',
    icon: '🛑',
  },
  UNCERTAIN: {
    label: 'Chưa kết luận',
    bg: 'var(--bg-2, rgba(120,120,120,0.12))',
    fg: 'var(--fg-2, #8a8a8a)',
    icon: '❓',
  },
};

const KIND_LABEL: Record<string, string> = {
  source: 'nguồn',
  propagation: 'lan truyền',
  sink: 'điểm đích',
  sanitizer: 'khử độc',
};

function StepEvidence({ step, index }: { step: InvestigationStep; index: number }) {
  const range =
    step.line_start && step.line_end && step.line_end !== step.line_start
      ? `${step.line_start}-${step.line_end}`
      : step.line_start
        ? `${step.line_start}`
        : '?';
  const loc = `${(step.file || '').split('/').pop() || step.file || ''}:${range}`;
  return (
    <div style={{ padding: '8px 0', borderBottom: '1px solid var(--line)' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 4 }}>
        <span className="mono" style={{ fontSize: 11, color: 'var(--fg-2)' }}>
          {index + 1}.
        </span>
        {step.kind && (
          <span className="chip" style={{ fontSize: 9.5 }}>
            {KIND_LABEL[step.kind] || step.kind}
          </span>
        )}
        <span style={{ fontSize: 12.5 }}>{step.claim_vi}</span>
      </div>
      {step.quote && (
        <div className="code-block" style={{ margin: '2px 0 4px' }}>
          <div className="code-block-header">
            <span className="mono" style={{ fontSize: 10.5 }}>
              {loc}
            </span>
            <span
              style={{
                fontSize: 10,
                color: step.grounded ? 'var(--sev-low-fg, #35c07a)' : 'var(--sev-high-fg, #ff7e36)',
              }}
              title={step.grounded_note || ''}
            >
              {step.grounded ? '✓ khớp mã thật' : '⚠ chưa neo được'}
            </span>
          </div>
          <pre
            style={{ margin: 0, padding: '8px 10px', overflowX: 'auto', fontSize: 11.5, lineHeight: 1.5 }}
          >
            <div className="diff-line ctx">
              {step.line_start ? <span className="ln">{step.line_start}</span> : null}
              <span>{step.quote}</span>
            </div>
          </pre>
        </div>
      )}
    </div>
  );
}

export function InvestigationCard({ inv }: { inv: FPInvestigation }) {
  const meta = VERDICT_META[inv.verdict] || VERDICT_META.UNCERTAIN;
  return (
    <div style={{ marginTop: 4 }}>
      <div
        style={{
          margin: '4px 0 8px',
          padding: '8px 10px',
          borderRadius: 8,
          fontSize: 12.5,
          background: meta.bg,
          borderLeft: `3px solid ${meta.fg}`,
        }}
      >
        {meta.icon} <b>{meta.label}.</b>{' '}
        <span className="chip" style={{ fontSize: 10, marginLeft: 4 }}>
          độ tin cậy: {inv.confidence}
        </span>{' '}
        {inv.summary_vi}
      </div>

      {inv.steps.length > 0 ? (
        <>
          <div className="muted" style={{ fontSize: 11, marginBottom: 2 }}>
            Lần theo luồng dữ liệu ({inv.steps.length} bước) — bằng chứng trích từ mã nguồn thật:
          </div>
          {inv.steps.map((s, i) => (
            <StepEvidence key={i} step={s} index={i} />
          ))}
          <div
            style={{
              fontSize: 11,
              marginTop: 6,
              color: inv.grounded ? 'var(--sev-low-fg, #35c07a)' : 'var(--sev-high-fg, #ff7e36)',
            }}
            title={inv.grounded_note || ''}
          >
            {inv.grounded
              ? '✓ Kết luận dựa trên bằng chứng đã đối chiếu mã nguồn thật.'
              : '⚠ Bằng chứng chưa neo chắc vào mã nguồn — cần người xem lại.'}
          </div>
        </>
      ) : (
        <div className="muted" style={{ fontSize: 12 }}>
          {inv.source_available === false
            ? 'Không đủ mã nguồn để lần theo luồng — cần người xem xét.'
            : 'Không có bước lập luận nào.'}
        </div>
      )}
    </div>
  );
}
