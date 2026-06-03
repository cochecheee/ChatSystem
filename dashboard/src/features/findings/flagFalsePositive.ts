import { api } from '../../api/client';
import type { Finding } from '../../types';

// Auto-filled when the user flags without typing a reason. Must be >= 20 chars
// to satisfy the /revoke justification gate (command_service _MIN_JUSTIFICATION).
const DEFAULT_JUSTIFICATION = 'Đánh dấu false positive (flag nhanh từ danh sách Vulnerabilities).';

export interface FlagOptions {
  /** Custom reason; falls back to a default if empty. */
  justification?: string;
  /** Also create a Tier 2 SuppressionRule so moved/edited recurrences skip too. Default true. */
  createSuppression?: boolean;
}

/**
 * Flag a finding as a false positive so future pipeline scans skip it.
 *
 * Reuses the existing V3.1 FP loop — no new backend:
 *   - POST /revoke sets status=REVOKED (+ audit). Next scan auto-revokes any
 *     finding with the same dedup_hash (Tier 1).
 *   - addSuppression creates a Tier 2 pattern rule (rule_id + file + tool) so
 *     recurrences that shifted line/wording are caught too.
 *
 * The backend keeps the security_lead+ gate, so callers without the role get a
 * 403 here (surface it to the user). Suppression-rule creation is best-effort:
 * the revoke alone already makes the exact finding skip next time.
 */
export async function flagFalsePositive(finding: Finding, opts: FlagOptions = {}): Promise<void> {
  const justification = (opts.justification ?? '').trim() || DEFAULT_JUSTIFICATION;

  await api.chat.command({
    command: '/revoke',
    finding_id: finding.id,
    justification,
  });

  if (opts.createSuppression !== false && finding.project_id) {
    try {
      await api.projects.addSuppression(finding.project_id, {
        rule_id: finding.rule_id,
        file_glob: finding.file_path || null,
        tool: finding.tool,
        reason: `FP flag (finding #${finding.id}): ${justification}`.slice(0, 500),
        expires_in_days: 90,
      });
    } catch {
      // Best-effort — Tier 1 (dedup) already covers the exact recurrence.
    }
  }
}
