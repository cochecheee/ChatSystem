import { Badge } from '../../components/Badge';

// Dependency-scanner tools — findings from these are CVE/package-update type.
// MUST khớp với DEPS_TOOLS ở backend (repositories/finding_repo.py) để filter
// category=sast|deps đúng. (Cố ý rộng hơn stats.ts:DEPS_TOOLS — bản đó chỉ phục
// vụ split sample phía client; đừng gộp hai set nếu chưa xác nhận backend.)
export const DEP_SCAN_TOOLS = new Set([
  'trivy',
  'dep-check',
  'dependency-check',
  'snyk',
  'owasp-dep-check',
  'owasp-dependency-check',
  'grype',
  'trivy-deps',
]);

export function isDepScan(tool: string): boolean {
  return DEP_SCAN_TOOLS.has(tool.toLowerCase());
}

export function SevChip({ sev }: { sev: string }) {
  return (
    <Badge variant={sev as 'critical' | 'high' | 'medium' | 'low' | 'info'} dot>
      {sev}
    </Badge>
  );
}
