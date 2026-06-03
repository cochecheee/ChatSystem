import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
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

  // V3.5 bug fix — `refresh` MUST be reference-stable, or any consumer that
  // includes it in a useEffect dep array (e.g. App.tsx re-fetches on auth
  // change) triggers an infinite loop:
  //   render -> new refresh ref -> dep changes -> effect fires ->
  //   refresh() -> setProjects -> re-render -> new refresh ref -> ...
  // Observed in production logs as /projects hitting ~75 req/s (~4500/min).
  // Functional setActiveProjectIdState lets us check the current id without
  // re-creating the callback when it changes.
  const refresh = useCallback(async () => {
    try {
      const list = await api.projects.list();
      setProjects(list);
      // Drop active if it no longer exists in the fresh list (deleted elsewhere).
      setActiveProjectIdState((cur) => {
        if (cur !== null && !list.find((p) => p.id === cur)) {
          localStorage.removeItem(STORAGE_KEY);
          return null;
        }
        return cur;
      });
    } catch {
      // Surface via empty state; auth errors are non-fatal here.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setActiveProjectId = (id: number | null) => {
    setActiveProjectIdState(id);
    if (id === null) localStorage.removeItem(STORAGE_KEY);
    else localStorage.setItem(STORAGE_KEY, String(id));
  };

  return (
    <ProjectContext.Provider
      value={{ projects, activeProjectId, setActiveProjectId, refresh, loading }}
    >
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
