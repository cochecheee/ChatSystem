import { useState } from 'react';
import { api } from '../../api/client';
import { usePolling } from '../../hooks/usePolling';
import type { WorkflowRun } from '../../types';

/**
 * Polling hook cho list workflow runs.
 *
 * Usage:
 *   const { runs, loading } = useRuns(branch, 30_000);
 */
export function useRuns(branch?: string, intervalMs = 30_000) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);

  usePolling(async () => {
    try {
      const r = await api.github.runs(branch);
      setRuns(r);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, intervalMs, [branch ?? '']);

  return { runs, loading };
}
