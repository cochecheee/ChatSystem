import { useState } from 'react';
import { api } from '../../api/client';
import { useActiveProjectParam } from '../../contexts/ProjectContext';
import { usePolling } from '../../hooks/usePolling';
import { POLL_INTERVAL_MS } from '../../lib/constants';
import type { WorkflowRun } from '../../types';

/**
 * Polling hook cho list workflow runs. Honors the ProjectContext selection
 * — when a project is active, the request uses that project's credentials.
 */
export function useRuns(branch?: string, intervalMs = POLL_INTERVAL_MS) {
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const { project_id } = useActiveProjectParam();

  usePolling(async () => {
    try {
      const r = await api.github.runs(branch, project_id);
      setRuns(r);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, intervalMs, [branch ?? '', project_id ?? '']);

  return { runs, loading };
}
