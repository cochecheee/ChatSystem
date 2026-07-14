import { useState } from 'react';
import { Icon } from './Icon';
import type { IntegrationInfo } from '../types';

/**
 * V4.4 — one-time integration bundle shown right after creating a project.
 * Everything needed to wire the target repo's pipeline: project_id, the two
 * repo secrets, and a ready-to-commit `.github/workflows/security.yml`. The
 * webhook token appears ONLY here (server hides it afterwards) — hence the
 * "save now" warning and copy buttons. Closing drops it from state.
 */
function CopyBtn({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="btn ghost sm"
      title="Copy"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {
          /* clipboard blocked — user can still select manually */
        }
      }}
    >
      <Icon name={done ? 'check' : 'copy'} size={12} /> {done ? 'Đã copy' : 'Copy'}
    </button>
  );
}

export function ProjectIntegrationModal({
  info,
  onClose,
}: {
  info: IntegrationInfo;
  onClose: () => void;
}) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--bg-elev, var(--surface-2))',
          border: '1px solid var(--line)',
          borderRadius: 10,
          width: 'min(720px, 96vw)',
          maxHeight: '90vh',
          overflow: 'auto',
          padding: 20,
          display: 'flex',
          flexDirection: 'column',
          gap: 14,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 16, fontWeight: 700 }}>Tích hợp pipeline — copy ngay</div>
          <button className="btn ghost sm" onClick={onClose} title="Đóng">
            <Icon name="x" size={14} />
          </button>
        </div>

        <div
          style={{
            fontSize: 12.5,
            color: 'var(--sev-high-fg, #c2410c)',
            background: 'var(--surface-2)',
            border: '1px solid var(--line)',
            borderRadius: 6,
            padding: '8px 10px',
          }}
        >
          ⚠ {info.note}
        </div>

        <div style={{ fontSize: 13 }}>
          <b>Project ID:</b> <span className="mono">{info.project_id}</span>
        </div>

        <div>
          <div
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--fg-3)',
              marginBottom: 6,
              textTransform: 'uppercase',
              letterSpacing: 0.3,
            }}
          >
            Secrets đặt trong repo (Settings → Secrets and variables → Actions)
          </div>
          {info.secrets_to_set.map((s) => {
            const optional = s.required === 'false';
            return (
              <div key={s.name} style={{ marginBottom: 10 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <span className="mono" style={{ minWidth: 150, fontSize: 12 }}>
                    {s.name}
                  </span>
                  <span
                    style={{
                      fontSize: 10.5,
                      fontWeight: 600,
                      padding: '1px 6px',
                      borderRadius: 4,
                      whiteSpace: 'nowrap',
                      color: optional ? 'var(--fg-3)' : 'var(--sev-high-fg, #c2410c)',
                      background: 'var(--surface-2)',
                      border: '1px solid var(--line)',
                    }}
                  >
                    {optional ? 'tuỳ chọn' : 'bắt buộc'}
                  </span>
                  <input
                    readOnly
                    className="mono"
                    value={s.value}
                    placeholder={optional ? '(dán giá trị nếu có — bỏ trống vẫn chạy)' : ''}
                    onFocus={(e) => e.currentTarget.select()}
                    style={{
                      flex: 1,
                      minWidth: 0,
                      padding: '5px 8px',
                      background: 'var(--surface-2)',
                      border: '1px solid var(--line)',
                      borderRadius: 6,
                      color: 'var(--fg)',
                      fontSize: 12,
                    }}
                  />
                  <CopyBtn text={s.value} />
                </div>
                {s.note && (
                  <div
                    className="muted"
                    style={{ fontSize: 10.5, marginTop: 3, marginLeft: 158, lineHeight: 1.4 }}
                  >
                    {s.note}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: 6,
            }}
          >
            <div
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: 'var(--fg-3)',
                textTransform: 'uppercase',
                letterSpacing: 0.3,
              }}
            >
              .github/workflows/security.yml
            </div>
            <CopyBtn text={info.workflow_yaml} />
          </div>
          <pre
            className="mono"
            style={{
              margin: 0,
              padding: 12,
              background: 'var(--surface-2)',
              border: '1px solid var(--line)',
              borderRadius: 8,
              fontSize: 11.5,
              overflowX: 'auto',
              whiteSpace: 'pre',
            }}
          >
            {info.workflow_yaml}
          </pre>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn primary sm" onClick={onClose}>
            Đã lưu, đóng
          </button>
        </div>
      </div>
    </div>
  );
}
