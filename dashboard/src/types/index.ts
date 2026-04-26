export interface Finding {
  id: number;
  artifact_id: number;
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
}

export interface Project {
  id: number;
  name: string;
  github_url: string;
  last_processed_run_id: number | null;
}

export interface WorkflowRun {
  id: number;
  name: string;
  conclusion: string | null;
  status: string;
  created_at: string;
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

export interface AnalysisResult {
  finding_id: number;
  vulnerability_id: string;
  explanation_vi: string;
  impact_vi: string;
  remediation_diff: string;
  severity: string;
  cwe_reference: string;
  confidence: string;
}

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';

export const SEVERITY_ORDER: Record<string, number> = {
  critical: 0, high: 1, medium: 2, low: 3, info: 4,
};
