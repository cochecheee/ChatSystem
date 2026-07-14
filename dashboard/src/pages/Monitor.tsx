import { useEffect, useState } from 'react';
import { api, type AlertItem, type UptimeCheck, type UptimeSummary } from '../api/client';
import { POLL_INTERVAL_MS } from '../lib/constants';
import { Badge } from '../components/Badge';
import { Icon } from '../components/Icon';

/**
 * Monitor tab — V2.4. Uptime % per target, latency, recent ping history,
 * unacknowledged alerts. Polls every 30s while page is mounted.
 */
export function PageMonitor() {
  const [summary, setSummary] = useState<UptimeSummary | null>(null);
  const [checks, setChecks] = useState<UptimeCheck[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [pinging, setPinging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const [s, u, a] = await Promise.all([
        api.monitor.summary(24),
        api.monitor.uptime(6),
        api.monitor.alerts({ only_open: false }),
      ]);
      setSummary(s);
      setChecks(u.items.slice(0, 30));
      setAlerts(a.slice(0, 20));
      setError(null);
    } catch (err) {
      setError(String((err as Error).message ?? err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  const onPing = async () => {
    setPinging(true);
    try {
      await api.monitor.ping();
      await load();
    } catch (err) {
      setError(String((err as Error).message ?? err));
    } finally {
      setPinging(false);
    }
  };

  const onAck = async (id: number) => {
    await api.monitor.ack(id);
    await load();
  };

  if (loading) {
    return (
      <div className="page-pad">
        <div className="empty-state">
          <Icon name="refresh" />
          <p>Loading monitor…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="page-pad">
      <div
        className="page-header"
        style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
      >
        <div>
          <h1 style={{ margin: 0 }}>Uptime — Health checks + Alerts</h1>
          <p style={{ color: 'var(--fg-3)', margin: '4px 0 0', fontSize: 13 }}>
            Hệ thống tự động kiểm tra mỗi 5 phút tới URL staging của dự án để theo dõi thời gian
            hoạt động (uptime).
          </p>
        </div>
        <button className="btn" onClick={onPing} disabled={pinging}>
          <Icon name="refresh" size={13} />
          {pinging ? 'Pinging…' : 'Ping now'}
        </button>
      </div>

      {error && (
        <div
          style={{
            background: 'var(--bg-2)',
            border: '1px solid var(--sev-high-fg)',
            padding: 12,
            borderRadius: 8,
            margin: '12px 0',
            fontSize: 13,
          }}
        >
          {error}
        </div>
      )}

      {/* Uptime summary cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 16,
          marginTop: 16,
        }}
      >
        {summary?.targets.length === 0 && (
          <div
            className="empty-state"
            style={{ gridColumn: '1 / -1', padding: 32, textAlign: 'center' }}
          >
            <Icon name="alert" size={24} />
            <h3 style={{ margin: '12px 0 6px' }}>Chưa có monitor target</h3>
            <p style={{ color: 'var(--fg-3)', fontSize: 13 }}>
              Set <code>MONITOR_TARGETS</code> env trên Render và <code>MONITOR_ENABLED=true</code>.
            </p>
          </div>
        )}
        {summary?.targets.map((t) => (
          <div key={t.target_url} className="card" style={{ padding: 16 }}>
            <div
              style={{
                fontSize: 11,
                color: 'var(--fg-3)',
                marginBottom: 4,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {t.target_url}
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                margin: '8px 0',
              }}
            >
              <div
                style={{
                  fontSize: 32,
                  fontWeight: 600,
                  color:
                    t.uptime_pct >= 99
                      ? 'var(--sev-low-fg)'
                      : t.uptime_pct >= 95
                        ? 'var(--sev-med-fg)'
                        : 'var(--sev-high-fg)',
                }}
              >
                {t.uptime_pct}%
              </div>
              <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>
                {t.checks} checks · {t.avg_latency_ms ?? '—'}ms avg
              </div>
            </div>
            <div style={{ fontSize: 11, color: 'var(--fg-3)' }}>
              Up: {t.up} · Down: {t.down} · Last 24h
            </div>
          </div>
        ))}
      </div>

      {/* Alerts */}
      <h2 style={{ marginTop: 32, marginBottom: 12 }}>Alerts</h2>
      {alerts.length === 0 ? (
        <p style={{ color: 'var(--fg-3)', fontSize: 13 }}>No alerts.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Kind</th>
              <th>Severity</th>
              <th>Title</th>
              <th>Raised</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {alerts.map((a) => (
              <tr key={a.id}>
                <td>
                  <Badge
                    variant={a.kind === 'down' ? 'high' : a.kind === 'recovered' ? 'low' : 'info'}
                  >
                    {a.kind}
                  </Badge>
                </td>
                <td>
                  <Badge variant={a.severity as 'high' | 'medium' | 'low' | 'info'} dot>
                    {a.severity}
                  </Badge>
                </td>
                <td style={{ maxWidth: 360 }}>{a.title}</td>
                <td style={{ fontSize: 12, color: 'var(--fg-3)' }}>
                  {new Date(a.raised_at).toLocaleString()}
                </td>
                <td>
                  {a.acknowledged_at ? (
                    <span style={{ fontSize: 11, color: 'var(--sev-low-fg)' }}>ack'd</span>
                  ) : (
                    <span style={{ fontSize: 11, color: 'var(--sev-high-fg)' }}>open</span>
                  )}
                </td>
                <td>
                  {!a.acknowledged_at && (
                    <button className="btn ghost sm" onClick={() => onAck(a.id)}>
                      Acknowledge
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Recent checks */}
      <h2 style={{ marginTop: 32, marginBottom: 12 }}>Recent pings (6h)</h2>
      {checks.length === 0 ? (
        <p style={{ color: 'var(--fg-3)', fontSize: 13 }}>No checks yet.</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Target</th>
              <th>Status</th>
              <th>Latency</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {checks.map((c) => (
              <tr key={c.id}>
                <td style={{ fontSize: 12, color: 'var(--fg-3)' }}>
                  {new Date(c.checked_at).toLocaleString()}
                </td>
                <td style={{ fontSize: 12, fontFamily: 'monospace' }}>{c.target_url}</td>
                <td>
                  {c.is_up ? (
                    <Badge variant="low" dot>
                      {c.http_status}
                    </Badge>
                  ) : (
                    <Badge variant="high" dot>
                      {c.http_status || 'FAIL'}
                    </Badge>
                  )}
                </td>
                <td style={{ fontSize: 12 }}>{c.response_time_ms ?? '—'}ms</td>
                <td style={{ fontSize: 11, color: 'var(--fg-3)' }}>{c.error_message ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
