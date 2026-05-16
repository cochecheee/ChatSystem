import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { api } from '../api/client';
import type { Project } from '../types';

interface ProjectContextValue {
  projects: Project[];
  activeProjectId: number | null;
  setActiveProjectId: (id: number | null) => void;
  refresh: () => Promise<void>;
  loading: boolean;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

const STORAGE_KEY = 'active_project_id';

function readStored(): number | null {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw || raw === 'null') return null;
  const n = parseInt(raw, 10);
  return Number.isFinite(n) ? n : null;
}

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setActiveProjectIdState] = useState<number | null>(readStored());
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    try {
      const list = await api.projects.list();
      setProjects(list);
      // Drop active if it no longer exists in the fresh list (deleted elsewhere).
      if (activeProjectId !== null && !list.find(p => p.id === activeProjectId)) {
        setActiveProjectIdState(null);
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Surface via empty state; auth errors are non-fatal here.
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setActiveProjectId = (id: number | null) => {
    setActiveProjectIdState(id);
    if (id === null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, String(id));
  };

  return (
    <ProjectContext.Provider value={{ projects, activeProjectId, setActiveProjectId, refresh, loading }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProjectContext(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error('useProjectContext must be used inside <ProjectProvider>');
  return ctx;
}

/** Param value to merge into API query strings. undefined when "All projects" is active. */
export function useActiveProjectParam(): { project_id?: number } {
  const { activeProjectId } = useProjectContext();
  return activeProjectId !== null ? { project_id: activeProjectId } : {};
}
