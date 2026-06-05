import { useEffect, useRef, useState } from 'react';
import { api, setAuthChallengeHandler } from './api/client';
import { POLL_INTERVAL_MS } from './lib/constants';
import { type PageId, Sidebar, Topbar } from './components/Shell';
import { AuthProvider } from './features/auth/AuthContext';
import { LoginModal } from './components/LoginModal';
import { ProjectProvider, useProjectContext } from './contexts/ProjectContext';
import { useAuth } from './features/auth/AuthContext';
import { PageChat } from './pages/Chat';
import { PageOverview } from './pages/Overview';
import { PagePipelines } from './pages/Pipelines';
import { PageReports } from './pages/Reports';
import { PageSCA } from './pages/Sca';
import { PageSettings } from './pages/Settings';
import { PageVulns } from './pages/Vulns';
import { PageRuntime } from './pages/Runtime';
import { PageMonitor } from './pages/Monitor';

function AppInner() {
  const [active, setActive] = useState<PageId>('overview');
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [openVulnId, setOpenVulnId] = useState<number | undefined>();
  const [newCritHighCount, setNewCritHighCount] = useState(0);
  const [loginOpen, setLoginOpen] = useState(false);
  const { activeProjectId, refresh: refreshProjects } = useProjectContext();
  const { user } = useAuth();

  // Re-fetch projects whenever auth identity changes so RBAC-filtered lists
  // appear/disappear immediately on login/logout.
  useEffect(() => {
    void refreshProjects();
  }, [user?.username, refreshProjects]);

  // V3.3 — any fetch that sees a 401 will open the login modal. Stays
  // registered for the app's lifetime; LoginModal closes itself on success.
  useEffect(() => {
    setAuthChallengeHandler(() => setLoginOpen(true));
    return () => setAuthChallengeHandler(null);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const critHighRef = useRef(0);

  useEffect(() => {
    // Reset baseline when switching projects so a higher-count tenant doesn't
    // produce a spurious "+N new" badge on the first poll.
    critHighRef.current = 0;
    setNewCritHighCount(0);
    const fetchData = () => {
      api.stats
        .overview(activeProjectId !== null ? { project_id: activeProjectId } : undefined)
        .then((s) => {
          const critHigh = s.critical_high;
          if (critHighRef.current !== 0 && critHigh > critHighRef.current) {
            setNewCritHighCount((prev) => prev + (critHigh - critHighRef.current));
          }
          critHighRef.current = critHigh;
        })
        .catch(() => {});
    };
    fetchData();
    const id = setInterval(fetchData, POLL_INTERVAL_MS);
    return () => clearInterval(id);
    // Re-fetch on login/logout too (user?.username) so KPIs refresh when the
    // RBAC scope changes — not only when the active project changes.
  }, [activeProjectId, user?.username]);

  const onNav = (id: PageId) => {
    setActive(id);
    if (id !== 'vulns') setOpenVulnId(undefined);
  };

  const onOpenVuln = (id: number) => {
    setOpenVulnId(id);
    setActive('vulns');
  };

  let page;
  switch (active) {
    case 'overview':
      page = <PageOverview onNav={onNav} onOpenVuln={onOpenVuln} />;
      break;
    case 'pipelines':
      page = <PagePipelines />;
      break;
    case 'vulns':
      page = <PageVulns initialId={openVulnId} />;
      break;
    case 'sca':
      page = <PageSCA />;
      break;
    case 'runtime':
      page = <PageRuntime />;
      break;
    case 'monitor':
      page = <PageMonitor />;
      break;
    case 'chat':
      page = <PageChat />;
      break;
    case 'reports':
      page = <PageReports />;
      break;
    case 'settings':
      page = <PageSettings />;
      break;
    default:
      page = <PageOverview onNav={onNav} onOpenVuln={onOpenVuln} />;
  }

  return (
    <div className="app-shell">
      <Sidebar active={active} onNav={onNav} />
      <div className="main">
        <Topbar
          active={active}
          onNav={onNav}
          theme={theme}
          onToggleTheme={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
          newCritHighCount={newCritHighCount}
          onClearCritHigh={() => setNewCritHighCount(0)}
          onOpenLogin={() => setLoginOpen(true)}
        />
        {page}
      </div>
      <LoginModal open={loginOpen} onClose={() => setLoginOpen(false)} />
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <ProjectProvider>
        <AppInner />
      </ProjectProvider>
    </AuthProvider>
  );
}
