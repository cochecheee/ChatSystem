import { useEffect, useRef, useState } from 'react';

interface ActionDialogProps {
  open: boolean;
  onClose: () => void;
  onConfirm: (justification: string) => Promise<void>;
  title: string;
  description: string;
  confirmLabel: string;
  confirmDanger?: boolean;
  findingId?: number;
}

export function ActionDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel,
  confirmDanger = false,
  findingId,
}: ActionDialogProps) {
  const [justification, setJustification] = useState('');
  const [loading, setLoading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const MIN_CHARS = 20;
  const isValid = justification.trim().length >= MIN_CHARS;

  useEffect(() => {
    if (open) {
      setJustification('');
      setLoading(false);
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (open) document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open, onClose]);

  if (!open) return null;

  const handleConfirm = async () => {
    if (!isValid || loading) return;
    setLoading(true);
    try {
      await onConfirm(justification.trim());
      onClose();
    } catch {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: 'var(--bg-elev)', border: '1px solid var(--line)',
          borderRadius: 10, padding: '24px 28px', width: 440, maxWidth: '90vw',
          boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
        }}
      >
        <div style={{ marginBottom: 6, fontSize: 15, fontWeight: 600 }}>{title}</div>
        {findingId !== undefined && (
          <div className="muted" style={{ fontSize: 12, marginBottom: 12 }}>
            Finding #{findingId}
          </div>
        )}
        <div className="muted" style={{ fontSize: 12.5, marginBottom: 14 }}>{description}</div>

        <textarea
          ref={textareaRef}
          rows={4}
          value={justification}
          onChange={e => setJustification(e.target.value)}
          placeholder={`Lý do (tối thiểu ${MIN_CHARS} ký tự)…`}
          style={{
            width: '100%', resize: 'vertical', padding: '8px 10px',
            background: 'var(--surface-2)', border: '1px solid var(--line)',
            borderRadius: 6, color: 'var(--fg)', fontSize: 13,
            fontFamily: 'inherit', outline: 'none',
          }}
        />

        {justification.length > 0 && !isValid && (
          <div style={{ fontSize: 11.5, color: 'var(--sev-high-fg)', marginTop: 4 }}>
            Cần thêm {MIN_CHARS - justification.trim().length} ký tự nữa
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 16 }}>
          <button className="btn" onClick={onClose} disabled={loading}>
            Hủy
          </button>
          <button
            className={`btn ${confirmDanger ? 'danger' : 'primary'}`}
            disabled={!isValid || loading}
            onClick={handleConfirm}
          >
            {loading ? 'Đang xử lý…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
