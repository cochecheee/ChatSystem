import { useState } from 'react';
import { api } from '../../api/client';
import type { FindingListParams } from '../../api/client';
import { useActiveProjectParam } from '../../contexts/ProjectContext';
import { usePolling } from '../../hooks/usePolling';
import { POLL_INTERVAL_MS } from '../../lib/constants';
import type { Finding } from '../../types';

/**
 * Polling hook cho list findings. Merges active-project filter from
 * ProjectContext unless caller already passed `project_id` explicitly.
 *
 * Usage:
 *   const { findings, loading } = useFindings({ limit: 200 });
 */
export function useFindings(params: FindingListParams = {}, intervalMs = POLL_INTERVAL_MS) {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const ambient = useActiveProjectParam();
  const merged: FindingListParams = { ...ambient, ...params };

  usePolling(
    async () => {
      try {
        const f = await api.findings.list(merged);
        setFindings(f);
      } catch {
        // ignore — caller có thể check loading state
      } finally {
        setLoading(false);
      }
    },
    intervalMs,
    [JSON.stringify(merged)]
  );

  return { findings, loading };
}
