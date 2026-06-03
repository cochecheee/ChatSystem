import { useCallback, useState } from 'react';

interface AsyncState {
  loading: boolean;
  error: string | null;
  success: boolean;
}

export function useAsyncAction<T extends unknown[]>(fn: (...args: T) => Promise<void>) {
  const [state, setState] = useState<AsyncState>({
    loading: false,
    error: null,
    success: false,
  });

  const run = useCallback(
    async (...args: T) => {
      setState({ loading: true, error: null, success: false });
      try {
        await fn(...args);
        setState({ loading: false, error: null, success: true });
      } catch (e) {
        setState({ loading: false, error: String(e), success: false });
      }
    },
    [fn]
  );

  const clear = useCallback(() => setState({ loading: false, error: null, success: false }), []);

  return { ...state, run, clear };
}
