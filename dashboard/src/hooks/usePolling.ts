import { useEffect, useRef } from 'react';

/**
 * Generic polling hook — gọi `fn` mỗi `intervalMs`.
 *
 * - Gọi 1 lần ngay khi mount.
 * - Cleanup khi unmount hoặc deps đổi.
 * - Pass `enabled=false` để pause polling.
 *
 * Usage:
 *   usePolling(() => api.findings.list().then(setFindings), 60_000, [projectId]);
 */
export function usePolling(
  fn: () => void | Promise<void>,
  intervalMs: number,
  deps: React.DependencyList = [],
  enabled = true,
) {
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      void fnRef.current();
    };
    tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, enabled, ...deps]);
}
