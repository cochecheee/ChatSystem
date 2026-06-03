import { useAuth } from '../features/auth/AuthContext';
import { Icon } from './Icon';
import { ProjectSelector } from './ProjectSelector';

export type PageId =
  | 'overview'
  | 'pipelines'
  | 'vulns'
  | 'sca'
  | 'runtime'
  | 'monitor'
  | 'chat'
  | 'reports'
  | 'settings';

interface NavItem {
  id: PageId;
  label: string;
  icon: string;
}

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: 'Workspace',
    items: [
      { id: 'overview', label: 'Overview', icon: 'dashboard' },
      { id: 'pipelines', label: 'Pipelines', icon: 'pipeline' },
      { id: 'vulns', label: 'Vulnerabilities', icon: 'shield' },
      { id: 'sca', label: 'Dependencies', icon: 'package' },
      { id: 'runtime', label: 'Runtime (DAST)', icon: 'alert' },
      { id: 'monitor', label: 'Uptime', icon: 'clock' },
    ],
  },
  {
    group: 'Assistant',
    items: [{ id: 'chat', label: 'AI Chat', icon: 'chat' }],
  },
  {
    group: 'Admin',
    items: [
      { id: 'reports', label: 'Reports', icon: 'report' },
      { id: 'settings', label: 'Settings', icon: 'settings' },
    ],
  },
];

const CRUMB: Record<PageId, string[]> = {
  overview: ['Workspace', 'Overview'],
  pipelines: ['Workspace', 'Pipelines'],
  vulns: ['Workspace', 'Vulnerabilities'],
  sca: ['Workspace', 'Dependencies · SCA'],
  runtime: ['Workspace', 'Runtime · DAST'],
  monitor: ['Workspace', 'Uptime · Health checks'],
  chat: ['Assistant', 'AI Assistant'],
  reports: ['Admin', 'Reports'],
  settings: ['Admin', 'Settings'],
};

interface SidebarProps {
  active: PageId;
  onNav: (id: PageId) => void;
}

export function Sidebar({ active, onNav }: SidebarProps) {
  const { user } = useAuth();
  const initials = user ? user.username.slice(0, 2).toUpperCase() : '?';
  const chipName = user?.username ?? 'Not signed in';
  const chipRole = user?.role ?? 'anonymous';
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">S</div>
        <div>
          <div className="brand-name">Sentinel</div>
          <div className="brand-sub">SAST · CI/CD · AI</div>
        </div>
      </div>
      {NAV.map((group) => (
        <div key={group.group}>
          <div className="nav-group-label">{group.group}</div>
          {group.items.map((it) => (
            <div
              key={it.id}
              data-nav={it.id}
              className={`nav-item${active === it.id ? ' active' : ''}`}
              onClick={() => onNav(it.id)}
            >
              <Icon name={it.icon} className="icon" />
              <span>{it.label}</span>
            </div>
          ))}
        </div>
      ))}
      <div className="sidebar-footer">
        <div className="user-chip">
          <div className="avatar">{initials}</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="user-chip-name">{chipName}</div>
            <div className="user-chip-role">{chipRole}</div>
          </div>
          <Icon name="chevron_down" size={12} style={{ color: 'var(--fg-3)' }} />
        </div>
      </div>
    </aside>
  );
}

interface TopbarProps {
  active: PageId;
  onNav: (id: PageId) => void;
  theme: string;
  onToggleTheme: () => void;
  newCritHighCount?: number;
  onClearCritHigh?: () => void;
  onOpenLogin: () => void;
}

export function Topbar({
  active,
  onNav,
  theme,
  onToggleTheme,
  newCritHighCount,
  onClearCritHigh,
  onOpenLogin,
}: TopbarProps) {
  const { user, logout } = useAuth();
  const crumbs = CRUMB[active] ?? [];
  return (
    <div className="topbar">
      <div className="crumbs">
        {crumbs.map((c, i) => (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {i > 0 && <Icon name="chevron_right" size={12} className="sep" />}
            <span className={i === crumbs.length - 1 ? 'current' : ''}>{c}</span>
          </span>
        ))}
      </div>
      <div className="topbar-right">
        <ProjectSelector />
        <div className="search-box">
          <Icon name="search" size={14} />
          <input placeholder="Search vulnerabilities, repos, runs…" readOnly />
          <span className="kbd">⌘K</span>
        </div>
        <button
          className="btn ghost"
          style={{ padding: 6, position: 'relative' }}
          onClick={onClearCritHigh}
        >
          <Icon name="bell" size={15} />
          {(newCritHighCount ?? 0) > 0 && <span className="notif-dot">{newCritHighCount}</span>}
        </button>
        <button className="btn" onClick={onToggleTheme} title="Toggle theme">
          {theme === 'dark' ? '☀' : '☾'}
        </button>
        <button className="btn primary" onClick={() => onNav('chat')}>
          <Icon name="sparkle" size={13} />
          Ask AI
        </button>
        {user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span
              className="chip"
              title={`Logged in as ${user.username} (${user.role})`}
              style={{ fontSize: 11, padding: '3px 8px' }}
            >
              <Icon name="user" size={11} /> {user.username}:{user.role}
            </span>
            <button
              className="btn ghost sm"
              onClick={logout}
              style={{ padding: '4px 8px', fontSize: 11 }}
            >
              Sign out
            </button>
          </div>
        ) : (
          <button
            className="btn sm"
            onClick={onOpenLogin}
            style={{ padding: '4px 10px', fontSize: 12 }}
          >
            <Icon name="user" size={12} /> Sign in
          </button>
        )}
      </div>
    </div>
  );
}
