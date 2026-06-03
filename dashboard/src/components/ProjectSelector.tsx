import { useProjectContext } from '../contexts/ProjectContext';

/**
 * Dropdown in the topbar — switches the active project for every page hook.
 * `null` means "All projects" (aggregate).
 */
export function ProjectSelector() {
  const { projects, activeProjectId, setActiveProjectId, loading } = useProjectContext();
  if (loading) return null;

  return (
    <select
      className="project-selector"
      value={activeProjectId ?? ''}
      onChange={(e) => {
        const v = e.target.value;
        setActiveProjectId(v === '' ? null : parseInt(v, 10));
      }}
      title="Filter every page by project"
      style={{
        background: 'var(--bg-2)',
        color: 'var(--fg-1)',
        border: '1px solid var(--border)',
        borderRadius: 6,
        padding: '4px 8px',
        fontSize: 12,
        minWidth: 160,
      }}
    >
      <option value="">All projects</option>
      {projects.map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
        </option>
      ))}
    </select>
  );
}
