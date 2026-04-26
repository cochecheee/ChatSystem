import { Icon } from './Icon';

export type PageId = 'overview' | 'pipelines' | 'vulns' | 'chat' | 'reports' | 'settings';

const NAV = [
  {
    group: 'Workspace', items: [
      { id: 'overview' as PageId, label: 'Overview', icon: 'dashboard' },
      { id: 'pipelines' as PageId, label: 'Pipelines', icon: 'pipeline' },
      { id: 'vulns' as PageId, label: 'Vulnerabilities', icon: 'shield' },
    ],
  },
  {
    group: 'Assistant', items: [
      { id: 'chat' as PageId, label: 'AI Assistant', icon: 'chat' },
    ],
  },
  {
    group: 'Insight', items: [
      { id: 'reports' as PageId, label: 'Reports', icon: 'report' },
      { id: 'settings' as PageId, label: 'Settings', icon: 'settings' },
    ],
  },
];

const CRUMB: Record<PageId, string[]> = {
  overview:  ['Workspace', 'Overview'],
  pipelines: ['Workspace', 'Pipelines'],
  vulns:     ['Workspace', 'Vulnerabilities'],
  chat:      ['Assistant', 'AI Assistant'],
  reports:   ['Insight', 'Reports'],
  settings:  ['Insight', 'Settings'],
};

interface SidebarProps {
  active: PageId;
  onNav: (id: PageId) => void;
  vulnCount: number;
}

export function Sidebar({ active, onNav, vulnCount }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">S</div>
        <div>
          <div className="brand-name">Sentinel</div>
          <div className="brand-sub">SAST · CI/CD · AI</div>
        </div>
      </div>
      {NAV.map(group => (
        <div key={group.group}>
          <div className="nav-group-label">{group.group}</div>
          {group.items.map(it => (
            <div
              key={it.id}
              className={`nav-item${active === it.id ? ' active' : ''}`}
              onClick={() => onNav(it.id)}
            >
              <Icon name={it.icon} className="icon" />
              <span>{it.label}</span>
              {it.id === 'vulns' && vulnCount > 0 && (
                <span className="nav-count">{vulnCount}</span>
              )}
            </div>
          ))}
        </div>
      ))}
      <div className="sidebar-footer">
        <div className="user-chip">
          <div className="avatar">MT</div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="user-chip-name">Minh Tran</div>
            <div className="user-chip-role">SAST_CICD · admin</div>
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
}

export function Topbar({ active, onNav, theme, onToggleTheme }: TopbarProps) {
  const crumbs = CRUMB[active] ?? [];
  return (
    <div className="topbar">
      <div className="crumbs">
        {crumbs.map((c, i) => (
          <span key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {i > 0 && <Icon name="chevron_right" size={12} style={{ color: 'var(--fg-4)' }} />}
            <span className={i === crumbs.length - 1 ? 'current' : ''}>{c}</span>
          </span>
        ))}
      </div>
      <div className="topbar-right">
        <div className="search-box">
          <Icon name="search" size={14} />
          <input placeholder="Search vulnerabilities, runs…" readOnly />
          <span className="kbd">⌘K</span>
        </div>
        <button className="btn ghost" style={{ padding: 6 }}>
          <Icon name="bell" size={15} />
        </button>
        <button className="btn" onClick={onToggleTheme} title="Toggle theme">
          {theme === 'dark' ? '☀' : '☾'}
        </button>
        <button className="btn primary" onClick={() => onNav('chat')}>
          <Icon name="sparkle" size={13} />
          Ask AI
        </button>
      </div>
    </div>
  );
}
