# Phase V3.1 — False Positive Learning Loop

**Branch**: `ft/imp-fe` (continue)
**Date**: 2026-05-16
**Goal**: Khi developer mark 1 finding là False Positive, hệ thống **nhớ** và auto-suppress lần next run — pipeline pass mà không cần code change. Đây là feature core cho real-world SAST adoption: SAST nào cũng noisy, không có learning loop = developers ignore tool.

**Driver**: User feedback "data lặp đi lặp lại" — vì mỗi run re-detect same FP. Cần loop:
```
run 1: 184 findings → developer revoke 80 FP
run 2: 184 findings → auto-skip 80 đã revoke → chỉ 104 cần triage
run 3: 184 findings → auto-skip 80 → chỉ 104 → if same → pipeline pass
```

## Industry context (defense talking points)

| Approach | Trade-off | Adopted by |
|---|---|---|
| Source-level annotation (`// codeql[ignore]`, `# noqa`) | Persistent + code-reviewed nhưng pollutes code | CodeQL, ESLint, Semgrep |
| External suppression file (`.semgrepignore`, `dependency-check-suppressions.xml`) | Centralized but XML/regex syntax painful | OWASP Dep-Check, SonarCloud |
| Dashboard-side revoke (this phase) | UX-friendly + audit trail in DB but tool-agnostic | Snyk, GitHub Advanced Security |
| AI-assisted triage (this phase, Tier 2) | Reduce manual effort 50-80% but needs LLM cost budget | Snyk DeepCode, Endor Labs |

→ V3.1 = combo "dashboard revoke" + "AI assist". Phù hợp thesis defense về AI-augmented DevSecOps.

## Current state (V3.0 ending)

**Có sẵn**:
- `Finding.status`: `pending_review` | `ai_analyzed` | `APPROVED` | `REVOKED`
- `Finding.dedup_hash` (rule_id + file_path + scrubbed_message)
- `/findings/{id}/revoke` endpoint + audit (`revoked_by`, `revoke_justification`, `revoked_at`)
- `/findings/{id}/explain` → Gemini analyze 1 finding, return severity reassessment + confidence
- `Finding.ai_analysis` JSON field (cached LLM output)

**Thiếu**:
- Mỗi run re-process tạo Finding rows mới với cùng `dedup_hash` nhưng `status=pending_review` (reset)
- Security Gate (sast-action composite) count tất cả critical/high không quan tâm REVOKED
- Không có bulk revoke / pattern suppression
- AI explain manual 1-by-1 → không scale với 184 finding

## Plan — 4 tier, ship incrementally

### Tier 1 — Cross-run dedup auto-revoke (smallest, ship đầu)

**Đổi**: khi ingest finding mới, nếu `dedup_hash` đã có 1 row `REVOKED` trước đó → set `status=REVOKED` ngay + copy `revoke_justification` + `revoked_by="auto-suppressed"`.

**Files**:
- `mcp/src/services/processor.py::_build_findings` — sau khi tạo Finding objects, query DB bulk cho `dedup_hash IN (...) AND status='REVOKED'`, mark inherit.
- `mcp/src/repositories/finding_repo.py` — add `find_revoked_hashes(hashes: set[str]) -> dict[hash, dict]`.
- Test: ingest run 1 → revoke 5 → ingest run 2 same content → 5 auto-revoked.

**Effort**: 2h

### Tier 2 — Suppression rules (pattern-based)

**Đổi**: thêm bảng `suppression_rules`:
```sql
CREATE TABLE suppression_rules (
    id           SERIAL PRIMARY KEY,
    project_id   INTEGER REFERENCES projects(id),
    rule_id      VARCHAR(255),        -- e.g. "java/path-injection", NULL = any rule
    file_glob    VARCHAR(1024),       -- e.g. "src/test/**", NULL = any path
    tool         VARCHAR(100),        -- e.g. "trivy", NULL = any
    severity_max VARCHAR(20),         -- e.g. "medium" → suppress medium-and-below match
    reason       TEXT NOT NULL,
    created_by   VARCHAR(255) NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now(),
    expires_at   TIMESTAMPTZ NULL     -- temp suppression, audit trail
);
```

**Ingest path**:
- Query active suppression_rules for project
- For each new Finding, match against rules: rule_id (exact or null) AND file_glob (fnmatch) AND tool (exact or null) AND severity (≤ severity_max)
- If matched → `status=REVOKED`, `revoke_justification=f"Auto-suppressed by rule #{rule.id}: {rule.reason}"`

**Endpoints**:
```
GET    /projects/{id}/suppressions
POST   /projects/{id}/suppressions     (security_lead+)
DELETE /projects/{id}/suppressions/{rule_id}
POST   /findings/{id}/revoke-with-rule (auto-extract rule_id+file → propose rule)
```

**UI**:
- Vulns page → row context menu: "Revoke this" / "Revoke all matching (creates rule)"
- Settings → Project → tab "Suppressions" — list + add/remove

**Effort**: 6-8h

### Tier 3 — AI-assisted batch triage

**Đổi**: nút "AI Triage" trên Vulns page — gửi danh sách finding (rule_id, file_path, snippet) lên Gemini với prompt:
```
You are a security engineer. Classify each finding below as:
- TRUE_POSITIVE (real vulnerability, must fix)
- FALSE_POSITIVE (tool noise, safe to ignore)
- NEEDS_REVIEW (cannot decide from context alone)

For each, return JSON: {finding_id, classification, confidence (0-1), reason}.

Findings:
[id=123, tool=trivy, rule=CVE-2024-XX, file=app/legacy/old.js, message=...]
[id=124, tool=codeql, rule=java/path-injection, file=src/test/...
...
```

**Logic**:
- Batch 10-20 findings per LLM call
- Findings classified FALSE_POSITIVE + confidence > 0.8 → auto-revoke với reason "AI flagged as FP: <reason>"
- Findings classified TRUE_POSITIVE → status stays, ai_analysis populated
- NEEDS_REVIEW → no change, just stored opinion

**Files**:
- `mcp/src/services/llm/triage_service.py` (new) — batch prompt + parse
- `mcp/src/api/chat.py` — `POST /api/chat/command` add command `/triage [run_id|project_id]`
- UI: button on Vulns page "AI triage selection" → modal with confidence threshold slider

**Cost guardrail**: Gemini free tier 60 req/min. Batch 20/call → 1200 findings/min. Throttle to 10/min for safety.

**Effort**: 8-12h

### Tier 4 — Gate integration

**Đổi**: `sast-action/actions/security-gate/action.yml` hiện count tất cả critical/high. Change to fetch from mcp:
```yaml
- name: Fetch mcp gate verdict
  run: |
    curl -fsS "${MCP_URL}/findings?project_id=${PROJECT_ID}&run_id=${RUN_ID}&status_not=REVOKED" \
      | jq '[.[] | select(.severity == "critical" or .severity == "high")] | length'
```

→ Gate chỉ count finding **chưa revoke**. Pipeline pass khi:
- Critical (chưa revoke) = 0
- High (chưa revoke) < threshold

**Cần thêm endpoint**:
```
GET /findings?project_id=X&run_id=Y&exclude_status=REVOKED
```

(Hoặc add `?gate_count=true` returning chỉ count + breakdown)

**Effort**: 3-4h

## Acceptance criteria (defense demo)

Demo flow:
1. ALOUTE run X → 184 findings → mcp ingest
2. Developer login → Vulns page → bulk select 50 trivy findings có rule "CVE-XXXX-low-priority" → click "Revoke all matching" → tạo suppression rule
3. ALOUTE run X+1 (push commit empty) → 184 findings ingest → 50 auto-revoked qua suppression rule → 134 active
4. UI Vulns hiển thị badge "50 auto-suppressed by rule"
5. Security Gate query `/findings?status_not=REVOKED` → critical=0, high<threshold → pass → CD chạy → deploy

## Risk + mitigation

| Risk | Mitigation |
|---|---|
| Over-suppression: dev revoke real vuln by accident | Audit log `revoked_by + reason + at`, weekly report unrevoked-and-still-present |
| AI hallucination → auto-revoke true positive | Confidence threshold ≥ 0.8, only top-tier (TRUE_POSITIVE auto-revoke disabled), log AI suggestions separately |
| Suppression rule too broad | Require security_lead+ role for rule creation, expires_at default 90 days |
| Schema migration on production DB | Test on local SQLite + Postgres, ship behind flag |

## Sequencing recommendation

| Order | Tier | Why first |
|---|---|---|
| 1 | Tier 1 (auto-revoke cross-run) | Quick win, no schema, immediate effect |
| 2 | Tier 4 (gate integration) | Closes the loop — revoke actually unblocks deploy |
| 3 | Tier 2 (suppression rules) | Real-world feature, biggest UX impact |
| 4 | Tier 3 (AI triage) | Polish for defense, requires Gemini cost |

**Min-viable demo**: Tier 1 + Tier 4 = 5-6h work, end-to-end loop visible.
**Full feature**: 19-26h. Có thể defer Tier 3 sau thesis.
