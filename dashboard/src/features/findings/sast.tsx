import { Badge } from '../../components/Badge';
import { getSeverityInfo, type Finding } from '../../types';

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

/** Build a "why this severity" tooltip from the provenance block. */
export function severityTooltip(f: Finding): string | undefined {
  const info = getSeverityInfo(f);
  if (!info) return undefined;
  const parts: string[] = [];
  if (info.original_label) parts.push(`Tool: ${info.original_label}`);
  if (info.cvss != null) {
    const kind = info.cvss_kind ? ` ${info.cvss_kind}` : '';
    const est = info.cvss_source === 'derived-from-label' ? ', ước lượng từ nhãn' : '';
    parts.push(`CVSS ${info.cvss}${kind}${est}`);
  }
  const head = parts.join(' · ') || 'severity';
  const why =
    info.source === 'promoted-dast'
      ? ' (nâng bậc DAST)'
      : info.disagreement
        ? ' (lấy mức cao hơn giữa nhãn & điểm)'
        : '';
  return `${head} → ${info.normalized ?? f.severity}${why}`;
}

export function SevChip({ sev, finding }: { sev: string; finding?: Finding }) {
  const chip = (
    <Badge variant={sev as 'critical' | 'high' | 'medium' | 'low' | 'info'} dot>
      {sev}
    </Badge>
  );
  const info = finding ? getSeverityInfo(finding) : undefined;
  if (!info) return chip;
  const promoted = info.source === 'promoted-dast' || info.disagreement === true;
  return (
    <span
      title={severityTooltip(finding!)}
      style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}
    >
      {chip}
      {promoted && (
        <span style={{ color: 'var(--sev-crit-fg, #ff4757)', fontSize: 9, lineHeight: 1 }}>▲</span>
      )}
    </span>
  );
}
