/**
 * Pure functions để compute stats từ findings array.
 * Tách ra khỏi page components để dễ test + reuse.
 */
import type { Finding } from '../../types';

const DEPS_TOOLS = new Set(['dependency-check', 'owasp-dependency-check', 'trivy', 'trivy-deps']);

export function isDepScan(tool: string): boolean {
  return DEPS_TOOLS.has(tool);
}

export function bySeverity(findings: Finding[]): Record<string, number> {
  return findings.reduce(
    (acc, f) => {
      acc[f.severity] = (acc[f.severity] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );
}

export function byTool(findings: Finding[]): Record<string, number> {
  return findings.reduce(
    (acc, f) => {
      acc[f.tool] = (acc[f.tool] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );
}

export function byStatus(findings: Finding[]): Record<string, number> {
  return findings.reduce(
    (acc, f) => {
      acc[f.status] = (acc[f.status] ?? 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );
}

export function aiAnalyzedCount(findings: Finding[]): number {
  return findings.filter((f) => !!f.ai_analysis).length;
}

export function aiAnalyzedPercent(findings: Finding[]): number {
  if (findings.length === 0) return 0;
  return Math.round((aiAnalyzedCount(findings) / findings.length) * 100);
}

export function splitSastDeps(findings: Finding[]): { sast: Finding[]; deps: Finding[] } {
  const sast: Finding[] = [];
  const deps: Finding[] = [];
  for (const f of findings) {
    if (isDepScan(f.tool)) deps.push(f);
    else sast.push(f);
  }
  return { sast, deps };
}
