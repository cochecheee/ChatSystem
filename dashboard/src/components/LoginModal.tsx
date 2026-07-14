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
 * Global login modal — username + password. The user's role is determined
 * server-side from the `users` table after the password verifies (no longer
 * client-selectable). Reachable from anywhere via the topbar Sign-in button.
 */
export function LoginModal({ open, onClose, required }: Props) {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  if (!open) return null;

  const handleLogin = async () => {
    if (!username.trim()) {
      setError('Nhập tên đăng nhập');
      return;
    }
    if (!password) {
      setError('Nhập mật khẩu');
      return;
    }
    setLoading(true);
    setError('');
    try {
      await login(username.trim(), password);
      setUsername('');
      setPassword('');
      onClose();
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'rgba(0,0,0,0.65)',
        backdropFilter: 'blur(4px)',
      }}
    >
      <div
        style={{
          background: 'var(--bg-elev)',
          border: '1px solid var(--line)',
          borderRadius: 12,
          padding: '28px 32px',
          width: 340,
          boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
          position: 'relative',
        }}
      >
        {!required && (
          <button
            onClick={onClose}
            style={{
              position: 'absolute',
              top: 10,
              right: 12,
              background: 'transparent',
              border: 'none',
              color: 'var(--fg-3)',
              fontSize: 18,
              cursor: 'pointer',
              padding: 4,
              lineHeight: 1,
            }}
            aria-label="Close"
          >
            ×
          </button>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
          <svg width="30" height="30" viewBox="0 0 64 64" aria-label="Shiftwall">
            <rect width="64" height="64" rx="14" fill="var(--accent)" />
            <g fill="none" stroke="#fff" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round">
              <path d="M24 16 H18 V48 H24" /><path d="M40 16 H46 V48 H40" />
              <path d="M39 32 H27" /><path d="M31 27 L26 32 L31 37" />
            </g>
          </svg>
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Shiftwall Login</div>
            <div className="muted" style={{ fontSize: 11.5 }}>
              Đăng nhập bằng mật khẩu
            </div>
          </div>
        </div>

        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--fg-3)' }}>
          Username
        </label>
        <input
          style={{
            width: '100%',
            padding: '7px 10px',
            background: 'var(--bg-muted)',
            border: '1px solid var(--line)',
            borderRadius: 6,
            color: 'var(--fg)',
            fontSize: 13,
            marginBottom: 12,
            outline: 'none',
          }}
          placeholder="Tên đăng nhập"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void handleLogin();
          }}
          autoFocus
        />

        <label style={{ display: 'block', fontSize: 12, marginBottom: 4, color: 'var(--fg-3)' }}>
          Password
        </label>
        <input
          type="password"
          style={{
            width: '100%',
            padding: '7px 10px',
            background: 'var(--bg-muted)',
            border: '1px solid var(--line)',
            borderRadius: 6,
            color: 'var(--fg)',
            fontSize: 13,
            marginBottom: 16,
            outline: 'none',
          }}
          placeholder="••••••••"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void handleLogin();
          }}
        />

        {error && (
          <div style={{ color: 'var(--sev-high-fg)', fontSize: 12, marginBottom: 12 }}>{error}</div>
        )}

        <button
          className="btn primary"
          style={{ width: '100%' }}
          onClick={handleLogin}
          disabled={loading}
        >
          {loading ? 'Đang đăng nhập…' : 'Đăng nhập'}
        </button>
      </div>
    </div>
  );
}
