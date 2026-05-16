import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Icon } from './Icon';

const ROLES = ['viewer', 'developer', 'security_lead', 'owner'] as const;

interface Member {
  username: string;
  role: string;
  created_at: string;
}

/**
 * Inline member-list panel for a single project. Reuses the existing JWT
 * — admins can mutate any project; owners can mutate their own; everyone
 * else gets a 403 the panel surfaces as a one-line error.
 */
export function ProjectMembers({ projectId }: { projectId: number }) {
  const [open, setOpen] = useState(false);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [newName, setNewName] = useState('');
  const [newRole, setNewRole] = useState<typeof ROLES[number]>('viewer');

  const refresh = async () => {
    setLoading(true);
    setError('');
    try {
      setMembers(await api.projects.listMembers(projectId));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projectId]);

  const handleAdd = async () => {
    if (!newName.trim()) return;
    setError('');
    try {
      await api.projects.addMember(projectId, newName.trim(), newRole);
      setNewName('');
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  const handleRemove = async (username: string) => {
    if (!confirm(`Remove ${username} from project?`)) return;
    setError('');
    try {
      await api.projects.removeMember(projectId, username);
      await refresh();
    } catch (e) {
      setError(String(e));
    }
  };

  if (!open) {
    return (
      <button
        className="btn ghost sm"
        style={{ padding: '4px 8px', fontSize: 11 }}
        onClick={() => setOpen(true)}
        title="Manage project members"
      >
        <Icon name="user" size={12} /> Members
      </button>
    );
  }

  return (
    <div style={{
      width: '100%',
      padding: '8px 12px',
      background: 'var(--surface-2)',
      borderRadius: 6,
      border: '1px solid var(--line)',
      marginTop: 8,
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <strong style={{ fontSize: 12 }}>Members ({members.length})</strong>
        <button className="btn ghost sm" style={{ padding: '2px 6px', fontSize: 10 }} onClick={() => setOpen(false)}>
          Close
        </button>
      </div>
      {loading && <div className="muted" style={{ fontSize: 11 }}>Loading…</div>}
      {error && <div style={{ color: 'var(--danger)', fontSize: 11 }}>{error}</div>}
      {members.map(m => (
        <div key={m.username} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12 }}>
          <span style={{ flex: 1 }}>{m.username}</span>
          <span className="chip" style={{ fontSize: 10 }}>{m.role}</span>
          <button
            className="btn ghost sm"
            style={{ padding: '2px 6px', fontSize: 10 }}
            onClick={() => handleRemove(m.username)}
            title="Remove"
          >
            <Icon name="trash" size={10} />
          </button>
        </div>
      ))}
      <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
        <input
          placeholder="username"
          value={newName}
          onChange={e => setNewName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') void handleAdd(); }}
          style={{
            flex: 1, padding: '4px 8px', fontSize: 11,
            background: 'var(--bg-2)', color: 'var(--fg-1)',
            border: '1px solid var(--line)', borderRadius: 4,
          }}
        />
        <select
          value={newRole}
          onChange={e => setNewRole(e.target.value as typeof ROLES[number])}
          style={{
            padding: '4px 8px', fontSize: 11,
            background: 'var(--bg-2)', color: 'var(--fg-1)',
            border: '1px solid var(--line)', borderRadius: 4,
          }}
        >
          {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
        <button className="btn primary sm" style={{ padding: '4px 8px', fontSize: 11 }} onClick={handleAdd}>
          Add
        </button>
      </div>
    </div>
  );
}
