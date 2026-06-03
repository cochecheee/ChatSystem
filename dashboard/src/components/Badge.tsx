import React from 'react';

type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';
type StatusVariant = 'passed' | 'failed' | 'running' | 'queued' | 'warning';

interface BadgeProps {
  variant: Severity | StatusVariant | 'neutral';
  dot?: boolean;
  children: React.ReactNode;
}

export function Badge({ variant, dot = false, children }: BadgeProps) {
  const isSev = ['critical', 'high', 'medium', 'low', 'info'].includes(variant);
  const cls = isSev ? `sev-${variant}` : variant === 'neutral' ? '' : `status-${variant}`;
  return <span className={`chip${dot ? ' dot' : ''} ${cls}`.trim()}>{children}</span>;
}
