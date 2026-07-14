export interface Finding {
  id: number;
  artifact_id: number;
  project_id: number | null; // V3.2 Pydantic computed via Artifact relationship
  tool: string;
  rule_id: string;
  severity: string;
  message: string;
  file_path: string;
  line_number: number | null;
  normalized_at: string | null;
  cwe_id: string | null;
  cvss_score: number | null;
  dedup_hash: string | null;
  status: string;
  raw_data: Record<string, unknown> | null;
  ai_analysis: AnalysisResult | null;
  justification: string | null;
  approved_by: string | null;
  approved_at: string | null;
  revoke_justification: string | null;
  revoked_by: string | null;
  revoked_at: string | null;
}

/** V4.0 — cross-tool dedup record the backend stores on a keeper finding's
 *  raw_data['_correlation'] when several tools reported the same vulnerability. */
export interface CorrelationMember {
  finding_id: number;
  tool: string;
  rule_id: string;
  severity: string;
  line_number: number | null;
  message: string;
}

export interface Correlation {
  cluster_key: string;
  size: number;
  tools: string[];
  primary_tool: string;
  cwe: string | null;
  severity_max: string;
  members: CorrelationMember[];
}

/** Extract the cross-tool correlation from a finding, or undefined if the
 *  finding is a singleton (not corroborated by any other tool). */
export function getCorrelation(f: Finding): Correlation | undefined {
  const raw = f.raw_data as Record<string, unknown> | null;
  const c = raw?.['_correlation'] as Correlation | undefined;
  return c && typeof c === 'object' && c.size > 1 ? c : undefined;
}

/** V4.1 — how a finding's canonical severity was derived (raw_data._severity). */
export interface SeverityProvenance {
  original_label?: string | null;
  cvss?: number | null;
  cvss_kind?: string | null; // v3 | v2 | security-severity
  band_label?: string | null;
  band_score?: string | null;
  normalized?: string;
  source?: string; // max(label,score) | label | score | sarif-level | promoted-dast | default
  disagreement?: boolean;
  cvss_source?: string; // tool | derived-from-label | none
}

export function getSeverityInfo(f: Finding): SeverityProvenance | undefined {
  const raw = f.raw_data as Record<string, unknown> | null;
  const s = raw?.['_severity'] as SeverityProvenance | undefined;
  return s && typeof s === 'object' ? s : undefined;
}

export interface DedupCluster {
  finding_id: number;
  file_path: string;
  line_number: number | null;
  cwe: string | null;
  severity: string;
  tools: string[];
  size: number;
  primary_tool: string;
}

export interface SeverityPromotedRow {
  finding_id: number;
  tool: string;
  file_path: string;
  line_number: number | null;
  original_label: string | null;
  band_label: string | null;
  band_score: string | null;
  cvss: number | null;
  cvss_kind: string | null;
  normalized: string;
}

export interface SeverityStats {
  project_id: number | null;
  run_id: number | null;
  total: number;
  with_provenance: number;
  promoted: number;
  disagreements: number;
  by_source: Record<string, number>;
  cvss_real: number;
  cvss_derived: number;
  cvss_none: number;
  by_tool: Record<string, { total: number; promoted: number }>;
  top_promoted: SeverityPromotedRow[];
}

export interface DedupStats {
  project_id: number | null;
  run_id: number | null;
  unique_findings: number;
  raw_findings_estimate: number;
  cross_tool_duplicates_removed: number;
  clusters_merged: number;
  multi_tool_clusters: number;
  reduction_pct: number;
  by_tool_contribution: Record<string, number>;
  clusters: DedupCluster[];
}

// V4.4 — vulnerability-category (OWASP Top-10 2021) distribution.
export interface CategoryRow {
  finding_id: number;
  tool: string;
  file_path: string;
  line_number: number | null;
  severity: string;
  owasp_class: string;
  owasp_category: string;
}

export interface CategoryStats {
  project_id: number | null;
  run_id: number | null;
  total: number;
  with_class: number;
  uncategorized: number;
  by_class: Record<string, number>;
  top_classes: CategoryRow[];
}

// Human labels for OWASP class codes (FE display without hitting the backend).
export const OWASP_LABELS: Record<string, string> = {
  A01: 'A01 Broken Access Control',
  A02: 'A02 Cryptographic Failures',
  A03: 'A03 Injection',
  A04: 'A04 Insecure Design',
  A05: 'A05 Security Misconfiguration',
  A06: 'A06 Vulnerable & Outdated Components',
  A07: 'A07 Identification & Authentication Failures',
  A08: 'A08 Software & Data Integrity Failures',
  A09: 'A09 Security Logging & Monitoring Failures',
  A10: 'A10 Server-Side Request Forgery (SSRF)',
  A00: 'A00 Uncategorized',
};

// V4.4 — one-time integration bundle returned by POST /projects.
export interface IntegrationInfo {
  project_id: number;
  webhook_token: string;
  dashboard_url: string;
  secrets_to_set: { name: string; value: string; required?: string; note?: string }[];
  workflow_yaml: string;
  note: string;
}

export interface Project {
  id: number;
  name: string;
  github_url: string;
  last_processed_run_id: number | null;
  /** V3.7 — per-project uptime Monitor target. Empty = not monitored. */
  staging_url?: string;
}

export interface WorkflowRun {
  id: number;
  name: string;
  conclusion: string | null;
  status: string;
  created_at: string;
  updated_at?: string;
  head_branch: string;
  head_sha: string;
  run_number: number;
  html_url?: string;
}

export interface WorkflowArtifact {
  id: number;
  name: string;
  size_in_bytes: number;
}

export interface WorkflowJobStep {
  name: string;
  status: string; // queued | in_progress | completed
  conclusion: string | null; // success | failure | skipped | cancelled | null
  number: number;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface WorkflowJob {
  id: number;
  run_id: number;
  name: string;
  status: string;
  conclusion: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  html_url?: string;
  steps: WorkflowJobStep[];
}

export interface AnalysisResult {
  finding_id: number;
  vulnerability_id: string;
  explanation_vi: string;
  impact_vi: string;
  remediation_diff: string;
  severity: string;
  cwe_reference: string;
  confidence: string;
  // V4.2 — false-positive verdict + fix-diff grounding (anti-hallucination)
  false_positive_likelihood?: string; // HIGH | MEDIUM | LOW
  false_positive_reason?: string;
  grounded?: boolean;
  grounded_note?: string;
}

export interface AiStats {
  project_id: number | null;
  run_id: number | null;
  total: number;
  analyzed: number;
  fp_likelihood: { HIGH: number; MEDIUM: number; LOW: number };
  grounded: number;
  ungrounded: number;
  ai_revoked: number;
  top_false_positive: {
    finding_id: number;
    tool: string;
    file_path: string;
    line_number: number | null;
    severity: string;
    reason: string;
    grounded: boolean;
  }[];
}

// V4.3 — "lỗi này có thật không?" investigation (data-flow reasoning + evidence)
export type Verdict = 'TRUE_POSITIVE' | 'FALSE_POSITIVE' | 'UNCERTAIN';

export interface InvestigationStep {
  claim_vi: string;
  kind?: string; // source | propagation | sink | sanitizer
  file?: string;
  line_start?: number;
  line_end?: number;
  quote?: string;
  grounded?: boolean;
  grounded_note?: string;
}

export interface FPInvestigation {
  finding_id: number;
  verdict: Verdict | string;
  confidence: string;
  summary_vi: string;
  steps: InvestigationStep[];
  false_positive_likelihood?: string;
  grounded?: boolean;
  grounded_note?: string;
  source_available?: boolean;
  suggested_command?: string | null;
}

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export const SEVERITY_ORDER: Record<string, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

export interface CommandRequest {
  command: string;
  finding_id?: number;
  run_id?: number;
  justification?: string;
}

export interface CommandResponse {
  status: string;
  message: string;
  data?: Record<string, unknown>;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}
