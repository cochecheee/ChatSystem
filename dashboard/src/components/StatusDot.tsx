interface StatusDotProps {
  status: 'ok' | 'error' | 'warn' | 'info' | 'critical' | 'high' | 'medium' | 'low';
  label?: string;
  size?: number;
}

export function StatusDot({ status, label, size }: StatusDotProps) {
  const isSev = ['critical', 'high', 'medium', 'low', 'info'].includes(status);
  const inlineColor = !isSev
    ? (
        {
          ok: 'var(--ok-fg)',
          error: 'var(--err-fg)',
          warn: 'var(--warn-fg)',
          info: 'var(--fg-4)',
        } as Record<string, string>
      )[status]
    : undefined;

  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      {isSev ? (
        <span
          className={`sev-dot ${status}`}
          style={size ? { width: size, height: size } : undefined}
        />
      ) : (
        <span
          style={{
            width: size ?? 8,
            height: size ?? 8,
            borderRadius: '50%',
            background: inlineColor,
            flexShrink: 0,
          }}
        />
      )}
      {label && <span style={{ fontSize: 'var(--ts-xs)', color: 'var(--fg-3)' }}>{label}</span>}
    </span>
  );
}
