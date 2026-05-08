import { useEffect, useRef, useState } from 'react';
import { api } from './api/client';
import { type PageId, Sidebar, Topbar } from './components/Shell';
import { AuthProvider } from './features/auth/AuthContext';
import { PageChat } from './pages/Chat';
import { PageOverview } from './pages/Overview';
import { PagePipelines } from './pages/Pipelines';
import { PageReports } from './pages/Reports';
import { PageSCA } from './pages/Sca';
import { PageSettings } from './pages/Settings';
import { PageVulns } from './pages/Vulns';

export default function App() {
  const [active, setActive] = useState<PageId>('overview');
  const [theme, setTheme] = useState<'light' | 'dark'>('light');
  const [openVulnId, setOpenVulnId] = useState<number | undefined>();
  const [vulnCount, setVulnCount] = useState(0);
  const [newCritHighCount, setNewCritHighCount] = useState(0);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);

  const critHighRef = useRef(0);

  useEffect(() => {
    const fetchData = () => {
      api.stats.overview().then(s => {
        setVulnCount(s.open);
        const critHigh = s.critical_high;
        if (critHighRef.current !== 0 && critHigh > critHighRef.current) {
          setNewCritHighCount(prev => prev + (critHigh - critHighRef.current));
        }
        critHighRef.current = critHigh;
      }).catch(() => {});
    };
    fetchData();
    const id = setInterval(fetchData, 60_000);
    return () => clearInterval(id);
  }, []);

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
    case 'overview':   page = <PageOverview onNav={onNav} onOpenVuln={onOpenVuln} />; break;
    case 'pipelines':  page = <PagePipelines />; break;
    case 'vulns':      page = <PageVulns initialId={openVulnId} />; break;
    case 'sca':        page = <PageSCA />; break;
    case 'chat':       page = <PageChat />; break;
    case 'reports':    page = <PageReports />; break;
    case 'settings':   page = <PageSettings />; break;
    default:           page = <PageOverview onNav={onNav} onOpenVuln={onOpenVuln} />;
  }

  return (
    <AuthProvider>
      <div className="app-shell">
        <Sidebar active={active} onNav={onNav} vulnCount={vulnCount} />
        <div className="main">
          <Topbar
            active={active}
            onNav={onNav}
            theme={theme}
            onToggleTheme={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
            newCritHighCount={newCritHighCount}
            onClearCritHigh={() => setNewCritHighCount(0)}
          />
          {page}
        </div>
      </div>
    </AuthProvider>
  );
}
