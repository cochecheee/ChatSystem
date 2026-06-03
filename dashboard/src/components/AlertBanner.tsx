interface AlertBannerProps {
  type: 'error' | 'success' | 'info' | 'warning';
  message: string;
  onDismiss?: () => void;
  action?: { label: string; onClick: () => void };
}

export function AlertBanner({ type, message, onDismiss, action }: AlertBannerProps) {
  const vars = {
    error: { fg: 'var(--err-fg)', bg: 'var(--err-bg)' },
    success: { fg: 'var(--ok-fg)', bg: 'var(--ok-bg)' },
    warning: { fg: 'var(--warn-fg)', bg: 'var(--warn-bg)' },
    info: { fg: 'var(--fg-2)', bg: 'var(--bg-muted)' },
  }[type];
  return (
    <div className="alert-banner" style={{ color: vars.fg, background: vars.bg }}>
      <span className="alert-banner-msg">{message}</span>
      {action && (
        <button className="btn ghost sm" onClick={action.onClick}>
          {action.label}
        </button>
      )}
      {onDismiss && (
        <button className="btn ghost sm" onClick={onDismiss}>
          ×
        </button>
      )}
    </div>
  );
}
