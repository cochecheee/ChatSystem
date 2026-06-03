import { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';

export interface SastToolsConfig {
  semgrep: boolean;
  codeql: boolean;
  spotbugs: boolean;
  eslint: boolean;
  trivy: boolean;
  dependency_check: boolean;
}

export interface GatesConfig {
  block_on_critical: boolean;
  block_on_high: boolean;
  block_on_secrets: boolean;
  min_cvss_score: number;
  require_ai_analysis: boolean;
}

export interface AiConfig {
  auto_analyze_critical: boolean;
  auto_analyze_high: boolean;
  model: string;
  max_findings_per_run: number;
  include_source_context: boolean;
}

export interface AllConfig {
  sast_tools?: SastToolsConfig;
  gates?: GatesConfig;
  ai?: AiConfig;
}

/**
 * Hook để load + update config từ BE.
 *
 * - Trên mount: load `GET /config` (1 lần).
 * - `update(key, value)` gọi `PUT /config/{key}` (admin only).
 * - State sync luôn khi update thành công.
 */
export function useAppConfig() {
  const [config, setConfig] = useState<AllConfig>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    api.config
      .list()
      .then((c) => {
        setConfig(c as AllConfig);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  const update = useCallback(async <K extends keyof AllConfig>(key: K, value: AllConfig[K]) => {
    const updated = await api.config.update(
      key as string,
      value as unknown as Record<string, unknown>
    );
    setConfig((prev) => ({ ...prev, [key]: updated }));
    return updated;
  }, []);

  return { config, loading, error, update };
}
