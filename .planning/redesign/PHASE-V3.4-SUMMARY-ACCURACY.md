# Phase V3.4 — AI summary data accuracy

**Branch**: `ft/imp-fe` (continue)
**Date**: 2026-05-16
**Driver**: User audit live V3.3 trả "9.1% pass rate degrading" + 5 risks toàn snakeyaml — feel hallucination dù số tổng (184/14/82) đúng. Root cause là 3 bug trong `summary.py`, không phải Gemini bịa.

**Scope**: data integrity only. Không thêm tính năng mới. Không UI redesign.

## 3 bug cần fix

### BUG-1 — pipeline_health pass-rate vô nghĩa

**File**: `mcp/src/services/llm/summary.py::_gather_stats`

**Code hiện**:
```python
runs_passed = max(1, runs_total - critical)  # crude but stable
pass_rate = round((runs_passed / runs_total * 100), 1)
```

**Sai vì**: `critical` là số finding, không phải số run fail. ALOUTE có 11 runs (1 chạy 14 critical) → formula trả 1/11 = 9.1%. Reality: hầu hết runs PASS conclusion=success, chỉ có findings.

**Fix options**:

| Option | Cost | Pros | Cons |
|---|---|---|---|
| A. Query `gh.list_workflow_runs()` lấy real conclusion | +1 GitHub API call/summary | Real data | +500ms latency, count toward rate limit |
| B. Persist `Artifact.conclusion` khi webhook nhận run-metadata | DB migration | No extra API call, cache hit instant | Schema change, history null |
| C. Bỏ pipeline_health khỏi card | 0 | Removes wrong data | Mất 1 trong 4 section, card nhìn thiếu |
| D. Compute từ data hiện có: `runs_passed = runs_total - runs_having_critical` | 0 | Honest about what we know | Vẫn ko phản ánh thật vì run có thể pass dù có finding |

**Đề xuất**: **(A)** — cache trong SummaryService.cache cùng với LLM output. 1 GitHub call/10 phút/project là quota acceptable. Defense viewer sẽ thấy số khớp với GitHub Actions tab.

**Effort**: 1h

### BUG-2 — Total vs active number

**File**: `mcp/src/services/llm/summary.py::_gather_stats` + prompt

**Code hiện**:
```python
total = await repo.count_with_filters(**common)       # includes REVOKED
active_total = await repo.count_with_filters(exclude_revoked=True, **common)
# prompt sends both, but Gemini defaults to "total"
```

**Sai vì**: Sau khi user triage revoke 50 FP, "184 phát hiện" misleading. Số dùng cho decision = active (134), không phải lịch sử (184).

**Fix**: 
- Pass thẳng **active counts** vào prompt (critical/high/medium counted với `exclude_revoked=True`)
- Prompt thêm: "Numbers are ACTIVE findings (excluding revoked false positives). Total ever-seen is X — mention only if > active by significant margin."
- Card UI sub-line thêm: "184 total · 134 active · 50 revoked" để thấy được kill rate

**Effort**: 30'

### BUG-3 — Top risks lack diversity

**File**: `mcp/src/services/llm/summary.py::_gather_stats` + prompt

**Code hiện**: Sort `top_findings.sort(key=lambda f: (sev_order, -f.id))[:8]` — top 8 critical/high theo severity → 5 cùng snakeyaml.

**Fix**:
- Pre-group findings BE-side trước khi gửi Gemini:
  - Group key: `(tool, rule_family)` where `rule_family = rule_id.split('/')[0]` or first 2 segments
  - Pick top-1 per group (highest severity, lowest id = most recent)
  - Limit to 8 diverse seeds → Gemini chọn 3-5 final
- Prompt thêm: "Pick the MOST DIVERSE 3-5 risks — distinct libraries / vulnerability classes / file paths."

**Concrete grouping for ALOUTE**:
- All 5 snakeyaml CVEs → 1 group "snakeyaml DoS" → return 1 representative (highest severity, most recent CVE)
- path-injection in FileUploadService → 1 group
- CSRF disable in security config → 1 group
- SSRF in url-preview → 1 group
- XSS in template → 1 group
→ Gemini sees 5+ diverse groups → returns diverse top_risks

**Effort**: 1.5h

## Sequencing

| # | Bug | Effort | Pytest delta |
|---|---|---|---|
| 1 | BUG-2 active counts (quick) | 30' | +1 |
| 2 | BUG-3 diversity grouping | 1.5h | +2 |
| 3 | BUG-1 real pipeline conclusion từ GitHub | 1h | +1 |
| 4 | Cache invalidation: clear cache trên FE refresh để thấy fix luôn | 15' | — |

**Total**: ~3h. Pytest 300 → 304.

## Acceptance criteria

Live verify sau fix:

```bash
curl /findings/ai-summary?project_id=2 -H "Authorization: Bearer <admin>" | jq

# Pipeline_health should reflect REAL conclusions:
# {
#   "runs_total": 11,
#   "runs_passed": 10,         # match what GitHub Actions tab shows
#   "pass_rate_pct": 90.9,
#   "trend": "stable"
# }

# top_risks should be diverse libraries:
# [
#   {severity: critical, rule_id: "java/path-injection", ...},   # not snakeyaml
#   {severity: critical, rule_id: "CVE-2022-25857", ...},       # snakeyaml (1 only)
#   {severity: high, rule_id: "java/csrf-disabled", ...},
#   {severity: high, rule_id: "java/ssrf", ...},
#   {severity: medium, rule_id: "java/xss", ...}
# ]

# overview_md should reference ACTIVE count, not historical total:
# "Hiện có **134 finding** đang active (50 đã revoke). Tập trung ở 14 critical..."
```

## Out of scope (defer to next phase)

- Streaming AI summary (typewriter effect) — UX polish, not data accuracy
- AI summary cho "all projects" view — currently only per-project
- Multi-language toggle (English fallback) — Vietnamese only by spec
- Retry button khi Gemini timeout — error path đã có, có thể polish sau

## Risk

- **A.1 GitHub API call** có thể rate-limit khi 5000 req/hour quota tiêu hết. Mitigate: cache 10 phút TTL = 6 call/hour/project = an toàn xa.
- **A.3 grouping** có thể group quá thô → bỏ sót đa dạng. Mitigate: test với ALOUTE real data, tune group key nếu cần.
