import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import { POLL_INTERVAL_MS } from '../../lib/constants';

export interface OverviewStats {
  total: number;
  critical_high: number;
  ai_analyzed: number;
  ai_analyzed_pct: number;
  by_severity: Record<string, number>;
  by_status: Record<string, number>;
  by_tool: Record<string, number>;
  open: number;
  approved: number;
  revoked: number;
  pending: number;
}

const DEPS_TOOLS = new Set([
  'dependency-check',
  'owasp-dependency-check',
  'trivy',
  'trivy-deps',
]);

/**
 * Hook poll `/stats/overview` — server-side counts đáng tin trên 8000+ findings.
 * Polling 15s per báo cáo tiến độ docx ch.4.5.
 */
export function useOverviewStats(intervalMs = POLL_INTERVAL_MS) {
  const [stats, setStats] = useState<OverviewStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetch = () => {
      api.stats.overview()
        .then(s => { if (!cancelled) { setStats(s); setLoading(false); } })
        .catch(() => { if (!cancelled) setLoading(false); });
    };
    fetch();
    const id = setInterval(fetch, intervalMs);
    return () => { cancelled = true; clearInterval(id); };
  }, [intervalMs]);

  return { stats, loading };
}

/**
 * Derive SAST vs Deps counts từ stats.by_tool — server-side luôn correct.
 */
export function splitSastDepsFromStats(byTool: Record<string, number>): {
  sast: number;
  deps: number;
} {
  let sast = 0;
  let deps = 0;
  for (const [tool, count] of Object.entries(byTool)) {
    if (DEPS_TOOLS.has(tool)) deps += count;
    else sast += count;
  }
  return { sast, deps };
}
