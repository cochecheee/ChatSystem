import { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { FindingListParams } from '../../api/client';
import { POLL_INTERVAL_MS } from '../../lib/constants';
import { useActiveProjectParam } from '../../contexts/ProjectContext';
import type { Finding, Project } from '../../types';

const PAGE_SIZE = 100;

/**
 * Data layer for the Vulnerabilities page (SAST findings only).
 *
 * Owns: project list, filtered+paginated findings, the 15s polling refresh,
 * and the selected-finding fetch. Returns plain state + setters so the page
 * component stays presentational. Behavior is unchanged from the previous
 * inline implementation — this is a straight extraction.
 */
export function useVulnsFindings(initialId?: number) {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [projectFilter, setProjectFilter] = useState<number | 'all'>('all');
  const [sevFilter, setSevFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [toolFilter, setToolFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState<number | null>(initialId ?? null);
  const [selectedFinding, setSelectedFinding] = useState<Finding | null>(null);
  const [refetchTick, setRefetchTick] = useState(0);

  const ambient = useActiveProjectParam();

  useEffect(() => {
    api.projects
      .list()
      .then(setProjects)
      .catch(() => {});
  }, []);

  const buildParams = (override: Partial<FindingListParams> = {}): FindingListParams => {
    const params: FindingListParams = {
      limit: PAGE_SIZE,
      skip: page * PAGE_SIZE,
      category: 'sast',
      latest_run_only: true, // current-state: chỉ run mới nhất (khớp Overview)
      ...override,
    };
    if (projectFilter !== 'all') params.project_id = projectFilter as number;
    else if (ambient.project_id !== undefined) params.project_id = ambient.project_id;
    if (sevFilter !== 'all') params.severity = sevFilter;
    if (toolFilter !== 'all') params.tool = toolFilter;
    if (statusFilter !== 'all') {
      const map: Record<string, string> = {
        pending: 'pending_review',
        analyzed: 'ai_analyzed',
        approved: 'APPROVED',
        revoked: 'REVOKED',
      };
      if (map[statusFilter]) params.status = map[statusFilter];
    } else {
      // Default view hides REVOKED false-positives — user đã triage thì
      // không hiện lại ở run sau. Muốn xem lại thì chọn filter "Revoked".
      params.exclude_revoked = true;
    }
    if (search.trim()) params.q = search.trim();
    return params;
  };

  // Reset to first page whenever a filter changes.
  useEffect(() => {
    setPage(0);
  }, [projectFilter, sevFilter, statusFilter, toolFilter, search]);

  useEffect(() => {
    setLoading(true);
    api.findings
      .listWithTotal(buildParams())
      .then(({ data, total: t }) => {
        setFindings(data);
        setTotal(t);
        setLoading(false);
      })
      .catch(() => setLoading(false));
    const id = setInterval(() => {
      api.findings
        .listWithTotal(buildParams())
        .then(({ data, total: t }) => {
          setFindings(data);
          setTotal(t);
        })
        .catch(() => {});
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    page,
    projectFilter,
    sevFilter,
    statusFilter,
    toolFilter,
    search,
    ambient.project_id,
    refetchTick,
  ]);

  useEffect(() => {
    if (initialId != null) setSelectedId(initialId);
  }, [initialId]);

  useEffect(() => {
    if (selectedId == null) {
      setSelectedFinding(null);
      return;
    }
    const cached = findings.find((f) => f.id === selectedId);
    if (cached) setSelectedFinding(cached);
    api.findings
      .get(selectedId)
      .then((f) => {
        setSelectedFinding(f);
        setFindings((prev) => prev.map((x) => (x.id === f.id ? f : x)));
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const refetch = () => setRefetchTick((t) => t + 1);

  return {
    PAGE_SIZE,
    findings,
    total,
    totalPages,
    page,
    setPage,
    loading,
    projects,
    projectFilter,
    setProjectFilter,
    sevFilter,
    setSevFilter,
    statusFilter,
    setStatusFilter,
    toolFilter,
    setToolFilter,
    search,
    setSearch,
    selectedId,
    setSelectedId,
    selectedFinding,
    ambient,
    refetch,
  };
}
