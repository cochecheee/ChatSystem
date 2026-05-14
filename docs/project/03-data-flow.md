# 03 — Data Flow End-to-End

## Vòng đời 1 finding

```
Developer push code (sample-python)
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│ STAGE 1 — GitHub Actions chạy security.yml (10 dòng)        │
│                                                              │
│ jobs:                                                        │
│   security:                                                  │
│     uses: cochecheee/sast-action/.github/workflows/          │
│            sast-ci.yml@master                                │
│     with:                                                    │
│       language: python                                       │
│     secrets:                                                 │
│       dashboard_url:   ${{ secrets.MCP_GATEWAY_URL }}        │
│       dashboard_token: ${{ secrets.MCP_WEBHOOK_TOKEN }}      │
│     permissions:                                             │
│       contents: read                                         │
│       security-events: write                                 │
│       actions: read                                          │
└──────────────────────────────────────────────────────────────┘
        │
        ▼ resolves reusable workflow
┌──────────────────────────────────────────────────────────────┐
│ STAGE 2 — sast-ci.yml (sast-action repo)                    │
│                                                              │
│   1. actions/checkout@v4                                     │
│   2. uses: ./actions/sast-suite      ── chạy SAST            │
│        ├── Semgrep    (universal, Docker)                    │
│        ├── Trivy-FS   (universal)                            │
│        ├── Bandit     (language=python)                      │
│        └── Safety<3   (language=python, từ requirements.txt) │
│   3. Upload artifact 'sast-reports-<run_number>'             │
│      zip chứa: semgrep.sarif, trivy-fs.sarif, bandit.sarif,  │
│      safety.json                                              │
│   4. uses: ./actions/notify-dashboard                        │
│      └── POST {dashboard_url}/webhook/pipeline-complete      │
│          Authorization: Bearer {dashboard_token}             │
│          Body: {run_id, run_number, repo, ref, sha, ...}     │
└──────────────────────────────────────────────────────────────┘
        │
        │ HTTPS POST
        ▼
┌──────────────────────────────────────────────────────────────┐
│ STAGE 3 — mcp ingest (Render Web Service)                   │
│   https://mcp-l958.onrender.com/webhook/pipeline-complete   │
│                                                              │
│   POST handler:                                              │
│     1. Verify Bearer token == settings.CI_WEBHOOK_TOKEN      │
│     2. Lookup/create Pipeline row (project_id từ env, run_id)│
│     3. Spawn FastAPI BackgroundTask: SecurityProcessor      │
│        │                                                     │
│        ├── GitHubClient.list_artifacts(run_id)               │
│        ├── Filter theo profile 'github-actions-default':    │
│        │     exact: spotbugs-report, semgrep-report, ...    │
│        │     prefix: trivy-image-scan-, sast-reports-       │
│        ├── Download zip artifact                            │
│        ├── Unzip vào temp dir                               │
│        ├── For each .sarif/.json:                           │
│        │     ├── Normalizer.parse(file) → list[Finding]      │
│        │     │   (đọc SARIF tool.driver.name → infer tool)   │
│        │     │   (extract: severity, file_path, line, rule)  │
│        │     ├── Dedup theo (tool, rule_id, file, line)      │
│        │     └── Insert Finding với category=sast|deps       │
│        └── Update Pipeline.status = "processed"              │
└──────────────────────────────────────────────────────────────┘
        │
        │ (lazy, khi user click finding)
        ▼
┌──────────────────────────────────────────────────────────────┐
│ STAGE 4 — AI Fix tiếng Việt                                  │
│   GET /findings/{id}/analysis  hoặc  POST /analysis         │
│                                                              │
│   1. Check Finding.analysis_cache → return nếu hit          │
│   2. GitHubClient.fetch_file_content(finding.file_path)     │
│   3. Extract context: 15 dòng trước + sau finding.line      │
│   4. ScrubbingService.scrub(context)                        │
│        └── Mask PII, secret, API key trước khi gửi LLM      │
│   5. build_prompt(finding, scrubbed_context, lang="vi")     │
│   6. GeminiClient.generate(prompt, schema=AnalysisOutput)   │
│        └── gemini-2.5-flash, structured JSON output          │
│   7. Parse + validate AnalysisOutput                        │
│   8. Cache vào Finding.analysis_cache (JSON column)         │
│   9. Return {explanation_vi, severity_reasoning, fix_diff,  │
│              cwe_refs, references}                          │
└──────────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────────────────────┐
│ STAGE 5 — Dashboard React                                    │
│   localhost:5173 (dev)  hoặc  Static Site URL (V2.5)        │
│                                                              │
│   Pages:                                                     │
│   • Overview      KPI tổng + chart per tool                  │
│   • Pipelines     List run + status                          │
│   • Vulnerabilities  category=sast, filter severity/tool     │
│   • SCA           category=deps, gom theo (package, version) │
│   • Chat          ChatOps + AI Q&A natural language          │
│   • Reports       Export PDF                                 │
│   • Settings      Project config + integration snippet       │
│                                                              │
│   Fetch base: import.meta.env.VITE_API_URL                   │
│   CORS: server allow_origins includes localhost:5173         │
└──────────────────────────────────────────────────────────────┘
```

## Webhook payload schema

```json
POST /webhook/pipeline-complete
Authorization: Bearer <CI_WEBHOOK_TOKEN>
Content-Type: application/json

{
  "run_id": 25772737815,
  "run_number": "7",
  "repository": "cochecheee/sample-python",
  "ref": "refs/heads/main",
  "sha": "7638d9cdf87fe835ef5e2685eba2f93b42c54dce",
  "actor": "cochecheee",
  "event": "push",
  "pipeline_status": "passed",
  "timestamp": "2026-05-13T01:35:43Z"
}
```

`run_id` là field BẮT BUỘC. Các field khác tolerated nếu missing.

Response: `202 Accepted` (xử lý async). Xem [docs/webhook-schema.md](../webhook-schema.md) cho chi tiết.

## Finding schema (output Stage 3)

```python
class Finding:
    id: int
    pipeline_id: int
    tool: str               # 'semgrep' | 'trivy' | 'bandit' | 'spotbugs' | ...
    category: str           # 'sast' | 'deps' | 'dast' (V2.3+)
    severity: str           # 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'INFO'
    rule_id: str            # eg 'B608' (Bandit), 'java/sql-injection' (CodeQL)
    title: str
    description: str
    file_path: str
    line_number: int | None
    status: str             # 'open' | 'approved' | 'revoked'
    raw_data: dict          # original SARIF JSON node
    analysis_cache: dict    # AI fix JSON (lazy populated)
    created_at, updated_at
```

## AnalysisOutput schema (output Stage 4)

```python
class AnalysisOutput:
    explanation_vi: str       # giải thích bằng tiếng Việt
    severity_reasoning: str   # vì sao severity ở mức X
    fix_diff: str             # unified diff suggested fix
    cwe_refs: list[str]       # ['CWE-89', ...]
    references: list[str]     # URL OWASP, CVE, docs
    fix_confidence: float     # 0.0-1.0
```

## Fallback: Poller (khi webhook fail)

Nếu CI POST webhook fail (network, cold start, ...) → mcp có cơ chế **poller**:

```
mcp/services/poller.py:
  - APScheduler chạy mỗi POLLING_INTERVAL_SECONDS (default 300s)
  - GET GitHub API: list workflow runs từ {POLLING_WORKFLOW_NAME} branch={POLLING_BRANCH}
  - So sánh với Project.last_processed_run_id
  - Nếu có run mới → tự gọi SecurityProcessor.process_run(run_id)
```

→ Đảm bảo finding cuối cùng vẫn vào dashboard, dù trễ 5 phút.
