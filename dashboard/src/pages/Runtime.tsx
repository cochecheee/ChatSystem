import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Badge } from '../components/Badge';
import { Icon } from '../components/Icon';
import { useActiveProjectParam } from '../contexts/ProjectContext';
import type { Finding } from '../types';

/**
 * Runtime tab — finding DAST từ OWASP ZAP scan staging (V2.3).
 *
 * Source: chat-system mcp /findings?category=dast
 * Backend filter: Finding.tool IN DAST_TOOLS ({owasp-zap, zap, zaproxy})
 */
export function PageRuntime() {
  const [items, setItems] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stats, setStats] = useState<{ open?: number; critHigh?: number } | null>(null);

  const { project_id } = useActiveProjectParam();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const findingParams: any = { category: 'dast', limit: 200, exclude_revoked: true, latest_run_only: true };
    if (project_id !== undefined) findingParams.project_id = project_id;
    Promise.all([
      api.findings.list(findingParams),
      api.stats.overview(project_id !== undefined ? { project_id } : undefined),
    ])
      .then(([list, ov]) => {
        if (cancelled) return;
        setItems(list);
        setStats({
          open: (ov as any).dast_open ?? 0,
          critHigh: (ov as any).dast_critical_high ?? 0,
        });
      })
      .catch((err) => {
        if (cancelled) return;
        setError(String(err.message ?? err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [project_id]);

  if (loading) {
    return (
      <div className="page-pad">
        <div className="empty-state">
          <Icon name="refresh" size={20} />
          <p>Loading DAST findings…</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="page-pad">
        <div className="empty-state">
          <Icon name="alert" size={20} />
          <p>Lỗi tải dữ liệu Runtime: {error}</p>
        </div>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="page-pad">
        <div className="empty-state" style={{ padding: 40, textAlign: 'center' }}>
          <Icon name="alert" size={28} />
          <h3 style={{ margin: '12px 0 6px' }}>Chưa có DAST finding nào</h3>
          <p style={{ color: 'var(--fg-3)', maxWidth: 480, margin: '0 auto', lineHeight: 1.5 }}>
            DAST (Dynamic Application Security Testing) chạy OWASP ZAP baseline scan đối với app
            staging sau khi CD redeploy. Bật bằng cách thêm <code>dast: true</code> +{' '}
            <code>staging_url</code> vào file <code>.github/workflows/security.yml</code> của
            inheritor repo.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-pad">
      <div className="page-header">
        <div>
          <h1 style={{ margin: 0 }}>Runtime — DAST findings</h1>
          <p style={{ color: 'var(--fg-3)', margin: '4px 0 0', fontSize: 13 }}>
            OWASP ZAP baseline scan kết quả từ staging URL của inheritor.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 22, fontWeight: 600 }}>{stats?.open ?? 0}</div>
            <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>open</div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 22, fontWeight: 600, color: 'var(--sev-high-fg)' }}>
              {stats?.critHigh ?? 0}
            </div>
            <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>crit/high</div>
          </div>
        </div>
      </div>

      <table className="data-table" style={{ marginTop: 16 }}>
        <thead>
          <tr>
            <th>Sev</th>
            <th>Alert</th>
            <th>URL / Method</th>
            <th>CWE</th>
            <th>Evidence</th>
          </tr>
        </thead>
        <tbody>
          {items.map((f) => {
            const raw = f.raw_data ?? {};
            const alert = (raw.alert as string) ?? f.message;
            const uri = (raw.uri as string) ?? f.file_path;
            const method = (raw.method as string) ?? '';
            const evidence = (raw.evidence as string) ?? '';
            return (
              <tr key={f.id}>
                <td>
                  <Badge
                    variant={f.severity as 'critical' | 'high' | 'medium' | 'low' | 'info'}
                    dot
                  >
                    {f.severity}
                  </Badge>
                </td>
                <td style={{ maxWidth: 320 }}>
                  <div style={{ fontWeight: 500 }}>{alert}</div>
                  <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>{f.rule_id}</div>
                </td>
                <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                  {method && <span style={{ color: 'var(--fg-3)' }}>{method} </span>}
                  {uri}
                </td>
                <td>
                  {f.cwe_id ? (
                    <Badge variant="info">{f.cwe_id}</Badge>
                  ) : (
                    <span style={{ color: 'var(--fg-3)' }}>—</span>
                  )}
                </td>
                <td
                  style={{
                    fontFamily: 'monospace',
                    fontSize: 11,
                    maxWidth: 240,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                  title={evidence}
                >
                  {evidence || <span style={{ color: 'var(--fg-3)' }}>—</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
