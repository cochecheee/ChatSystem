import { useState } from 'react';
import { useAuth } from '../features/auth/AuthContext';

interface Props {
  /** When true, render the dim overlay + dialog. Caller controls visibility. */
  open: boolean;
  /** Close handler. Called after a successful login and on cancel click. */
  onClose: () => void;
  /** If true, the close (×) button is hidden — used when login is required to proceed. */
  required?: boolean;
}

/**
 * Global login modal — replaces the previous Chat-only LoginOverlay. Same
 * demo flow (username + role, no password) but reachable from anywhere via
 * the topbar Sign-in button.
 */
export function LoginModal({ open, onClose, required }: Props) {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('developer');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!open) return null;

  const handleLogin = async () => {
    if (!username.trim()) {
      setError('Nhập tên đăng nhập');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await login(username.trim(), role);
      setUsername('');
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.65)', backdropFilter: 'blur(4px)',
    }}>
      <div style={{
        background: 'var(--bg-elev)', border: '1px solid var(--line)',
        borderRadius: 12, padding: '28px 32px', width: 340,
        boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
        position: 'relative',
      }}>
        {!required && (
          <button
            onClick={onClose}
            style={{
              position: 'absolute', top: 10, right: 12, background: 'transparent',
              border: 'none', color: 'var(--fg-3)', fontSize: 18, cursor: 'pointer',
              padding: 4, lineHeight: 1,
            }}
            aria-label="Close"
          >×</button>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <div className="ai-orb" style={{ width: 28, height: 28 }} />
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Sentinel Login</div>
            <div className="muted" style={{ fontSize: 11.5 }}>Demo — không cần password</div>
          </div>
        </div>

        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--fg-3)' }}>Username</label>
        <input
          style={{
            width: '100%', padding: '7px 10px', background: 'var(--bg-muted)',
            border: '1px solid var(--line)', borderRadius: 6, color: 'var(--fg)',
            fontSize: 13, marginBottom: 12, outline: 'none',
          }}
          placeholder="cochecheee"
          value={username}
          onChange={e => setUsername(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') void handleLogin(); }}
          autoFocus
        />

        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--fg-3)' }}>Role</label>
        <select
          style={{
            width: '100%', padding: '7px 10px', background: 'var(--bg-muted)',
            border: '1px solid var(--line)', borderRadius: 6, color: 'var(--fg)',
            fontSize: 13, marginBottom: 16, outline: 'none',
          }}
          value={role}
          onChange={e => setRole(e.target.value)}
        >
          <option value="developer">developer</option>
          <option value="security_lead">security_lead</option>
          <option value="admin">admin</option>
        </select>

        {error && <div style={{ color: 'var(--sev-high-fg)', fontSize: 12, marginBottom: 12 }}>{error}</div>}

        <button className="btn primary" style={{ width: '100%' }} onClick={handleLogin} disabled={loading}>
          {loading ? 'Đang đăng nhập…' : 'Đăng nhập'}
        </button>

        <div className="muted" style={{ fontSize: 10.5, marginTop: 12, lineHeight: 1.4 }}>
          Project membership được pick up khi login. Seed sẵn: <code>cochecheee</code> (owner cả 2), <code>viewer-demo</code> (viewer project 1).
        </div>
      </div>
    </div>
  );
}
