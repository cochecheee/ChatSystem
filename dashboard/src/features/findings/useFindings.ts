import { useState } from 'react';
import { api } from '../../api/client';
import type { FindingListParams } from '../../api/client';
import { usePolling } from '../../hooks/usePolling';
import { POLL_INTERVAL_MS } from '../../lib/constants';
import type { Finding } from '../../types';

/**
 * Polling hook cho list findings — wrap api.findings.list + setInterval.
 *
 * Usage:
 *   const { findings, loading } = useFindings({ limit: 200 });
 */
export function useFindings(params: FindingListParams = {}, intervalMs = POLL_INTERVAL_MS) {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);

  usePolling(async () => {
    try {
      const f = await api.findings.list(params);
      setFindings(f);
    } catch {
      // ignore — caller có thể check loading state
    } finally {
      setLoading(false);
    }
  }, intervalMs, [JSON.stringify(params)]);

  return { findings, loading };
}
