# chat-system — Cột mốc từ đầu đến cuối

**Project**: AI-augmented DevSecOps platform cho thesis tốt nghiệp
**Timeline**: ~1 tháng (18/04 → 16/05/2026)
**Hiện trạng**: V3.1 production-live, 269/269 pytest, ALOUTE + sample-python multi-tenant trên Render
**Last updated**: 2026-05-16

---

## 🌱 Giai đoạn 1 — Khởi tạo + E2E V1 (18-26/04)

| Mốc | Việc |
|---|---|
| **18/04** | Tạo file plan đầu tiên — chỉ ý tưởng, chưa có code |
| **26/04** | Ship V1 end-to-end qua 6 phase liên tiếp trong 1 ngày: SAST normalizer, dashboard pages, pipeline run boards, NL chat, lenient SARIF parser, wire all API endpoints |

**Output V1**: mcp Python + dashboard React chạy local, có thể ingest SARIF, hiện findings, NL chat sơ khai.

---

## 🎨 Giai đoạn 2 — UI/UX hardening (28-29/04)

**Phase 01 — Design system foundation** (28/04):
- Tạo `AlertBanner`, `Badge`, `StatusDot`, `useAsyncAction`
- Bỏ Sonner toast, thêm notification badge ở Topbar
- Page cleanup: Reports, Settings, Vulns

**Phase 02 — Pipeline visibility** (29/04):
- Fix bug: `status=completed` hardcoded ở backend
- Thêm branch filter, RunSummaryStrip, TrendCard
- PIPE-05: per-run finding count cache, SeverityBar

**Phase 03 — Data pipeline + CVE isolation** (29/04):
- Fix `SarifNormalizer.relatedLocations` fallback
- Extend `DepCheckNormalizer` version fields + nested zip
- Add `GitHubClient.fetch_file_content` → LLM context có source code
- `CveSummaryPanel` + upgrade chip ở deps tab

**Phase 04** (29/04): Research AI auto-fix + chat command (chưa ship)

---

## 🏗 Giai đoạn 3 — V2 redesign sang DevSecOps template (08-12/05)

**Insight**: post-v0.1.0 đánh giá thật — "code chạy được nhưng không phải DevSecOps thật". Quyết định pivot sang **reusable template pattern**.

| Phase | Ship | Tính năng |
|---|---|---|
| **V2.0 plan** | 09/05 | DevSecOps template: CI → CD → runtime → monitor |
| **V2.1** | 09/05 | Split `action.yml` thành 3 composite (notify-dashboard, sast-suite, aggregate-sarif). Reusable workflow `sast-ci.yml`. Inheritor guide. |
| **V2.1.2** | 09/05 | Python Flask vulnerable sample (`sample-python`) làm inheritor demo |
| **V2 deploy** | 12/05 | Render Web Service x2 (mcp + dashboard) + Postgres free. Bỏ persistent disk (free tier không hỗ trợ). |

---

## 🚀 Giai đoạn 4 — V2.2 → V2.6 (14/05)

Ship 5 phase chỉ trong 1 ngày:

| Version | Tính năng |
|---|---|
| **V2.2 CD** | Docker build + push → Render Deploy Hook trigger staging |
| **V2.3 DAST** | OWASP ZAP baseline scan staging → `ZapNormalizer` → dashboard Runtime tab |
| **V2.4 Monitor** | Uptime checks (cron), Alert entity, email via SMTP/Mailtrap, Sentry DSN |
| **V2.5 Dashboard** | Static Site trên Render Blueprint |
| **V2.6 Persistence** | Postgres fix, BIGINT for run_id (INT4 overflow), migration check |

---

## 🎓 Giai đoạn 5 — V2.7 + V2.8 (15/05) — Defense-aligned core

### V2.7 — Docx alignment (8 gap đối chiếu báo cáo tiến độ 1)

1. Thêm **CodeQL** vào sast-suite (Java semantic analysis)
2. **Security Gate** composite — block CI khi critical>0 / high>5
3. **4-layer guardrail** (Auth JWT + Schema Pydantic + Content scrub + Prompt injection)
4. **MCP server** với 8 tool (list_findings, explain_finding, approve_finding, …) — Anthropic protocol
5. 4 commands mới (`/status`, `/results`, `/help`, `/feedback`)
6. `CommandFeedback` entity (audit)
7. Live verify CI run `25928357264` GREEN — 182 findings incl 4 CodeQL
8. Live bug fix: scrubber làm corrupt JSON SARIF (email regex ăn `\n` JSON escape) → split scrub thành pre-parse + post-parse-per-field

### V2.8 — Multi-tenant runtime (1 mcp serve N inheritor)

- Pre-flight P1-P7: DB backup, audit webhook callers, fallback path, feature flag `MULTI_TENANT_ENABLED`, fixtures, Fernet, persist 9 field
- **Routing** theo `payload.repository` → lookup Project bằng github_url
- **Per-project GitHubClient + GeminiClient** cache by (api_key, model)
- **Fernet encrypt-at-rest** cho github_token + gemini_api_key (prefix `gAAAA` heuristic cho backward compat)
- **Parallel poller** với `asyncio.gather + Semaphore(3)` — iterate active projects
- Merge `verify-work` → `ft/imp-fe` (`ac469a1`)

---

## 🔐 Giai đoạn 6 — V2.9 + V3.0 (16/05 sáng)

### V2.9 — Multi-project UI

- `ProjectContext` provider + `useActiveProjectParam()` hook
- `<ProjectSelector />` dropdown ở topbar (All / per-project)
- Mọi hook chia sẻ (`useFindings`, `useOverviewStats`, `useRuns`) auto-merge active project
- Backend: `?project_id=` filter trên `/findings`, `/stats/overview`, `/stats/latest-scan`, `/github/runs`
- Per-page dropdown (Vulns, Sca, Reports, Pipelines) vẫn ưu tiên, fall back ambient
- **Fix UX**: lift LoginOverlay ra global (Chat-only → topbar Sign-in button + chip)

### V3.0 — Per-project RBAC

- Bảng `project_members(project_id, username, role)` — composite PK, role lattice viewer < developer < security_lead < owner
- JWT `memberships` claim snapshot at login
- `require_project_access(min_role)` dependency factory (path/query auto-resolve `project_id`)
- Member CRUD endpoints (owner-only invite, admin bypass)
- `GET /projects` filter theo membership khi `RBAC_PER_PROJECT=true`
- Kill-switch default OFF — không break existing demo
- Inline `<ProjectMembers />` panel trong Settings

---

## 🤖 Giai đoạn 7 — V3.1 (16/05 chiều) — FP Learning Loop

**Driver**: user phản hồi "data lặp đi lặp lại" — mỗi run re-detect same FP, không có cơ chế học.

**4 tier ship tuần tự**:

| Tier | Function |
|---|---|
| **1** — Auto-revoke cross-run | `FindingRepository.find_revoked_hashes` → new ingest inherits REVOKED từ dedup_hash match cùng project |
| **4** — Gate integration | `/findings/gate-count` excludes REVOKED + `?run_id` + `?exclude_revoked` filters. sast-action composite query mcp khi `mcp_project_id` input set. |
| **2** — Suppression rules | Bảng `suppression_rules(rule_id, file_glob, tool, severity_max, TTL)`. Matcher với fnmatch + severity rank. UI manager. |
| **3** — AI batch triage | `POST /findings/triage` → Gemini classify TP/FP/NR với confidence, auto-revoke FP confidence≥0.8. Dry-run preview mode. UI modal. |

**Live smoke trên ALOUTE**: triage 5 findings → Gemini classify 5/5 TRUE_POSITIVE với reasoning Vietnamese (CSRF disabled, SSRF, XSS, path traversal, snakeyaml DoS — đúng spec ALOUTE).

---

## 📊 Số liệu tổng

| Metric | Cuối V1 | Cuối V2.6 | Cuối V2.8 | Cuối V3.0 | **Cuối V3.1** |
|---|---|---|---|---|---|
| Pytest | ~80 | ~180 | 242 | 252 | **269** |
| Endpoint | ~12 | ~25 | 30 | 33 | **37** |
| Lines of code | ~3K | ~8K | ~15K | ~17K | **~19K** |
| Active phase docs | 6 | 12 | 18 | 23 | **27** |

---

## 🏗 Hiện trạng production (16/05/2026)

```
chat-system @ ft/imp-fe (39cfa43)
├── mcp backend  → https://mcp-l958.onrender.com (V3.1 endpoints live)
├── dashboard    → https://dashboard-zyy0.onrender.com (V3.1 UI build)
└── inheritors:
    ├── sample-python @ main (1132 findings — Python+CVE+DAST)
    └── SAST_CICD/ALOUTE @ main (184 findings — Java+Spring RCE vuln)

sast-action @ master (402e8b2) — composite library cho inheritors
SECRETS.txt — gitignore, single source of truth (PAT, Gemini key, Fernet key)
```

**Render env vars active**:
- `MULTI_TENANT_ENABLED=true` (V2.8)
- `FERNET_KEY=8xnfnyQl...` (V2.8, sync:false)
- `RBAC_PER_PROJECT` — chưa flip true (kill-switch off để debug)

---

## 🎤 Defense narrative (5 phút)

1. Show 2 inheritor (Python + Java) cùng dùng 1 reusable workflow → DevSecOps template
2. Login admin → switch project trong topbar → mọi page filter đúng
3. ALOUTE Vulns 184 findings → click "AI Triage" → Gemini Vietnamese reasoning
4. Apply revokes → gate-count drop → push commit → CI pass → CD deploy
5. Defense talking points: multi-tenant + per-project RBAC + AI-augmented FP loop + Anthropic MCP protocol + 4-layer guardrail

---

## 💪 Strong points (mạnh để bảo vệ thesis)

- **Real-world architecture**: multi-tenant + RBAC + Fernet + gate integration đủ industry-grade
- **AI angle thật, không gimmick** — Gemini structured output, batch, confidence threshold
- **100% tests xanh xuyên suốt** — chưa từng regress qua 7 giai đoạn
- **Live evidence** — không phải mock screenshot, mọi feature có CI run thật

## ⚖ Trade-off (phòng câu hỏi phản biện)

- Demo login không password — vì thesis scope; sản phẩm thật cần OAuth/LDAP
- JWT memberships snapshot 8h — stale ngay sau khi admin kick member; production cần refresh-token flow
- Fernet single-key — key rotate phá ciphertext, không có versioning
- AI triage không có human-in-the-loop required cho TRUE_POSITIVE — quá tự tin có thể auto-revoke real vuln (đã mitigate bằng threshold + only auto-revoke FP, không auto-approve TP)

---

## 🗂 Phase doc index

Toàn bộ chi tiết kỹ thuật theo phase, đọc theo thứ tự:

| Phase | File |
|---|---|
| V1 → V2 redesign | `.planning/redesign/PHASE-V2.md` |
| V2.5/V2.6 | `.planning/redesign/PHASE-V2.md` (cuối file) |
| V2.7 docx alignment | `.planning/redesign/PHASE-V2.7-DOCX-ALIGNMENT.md` |
| V2.8 multi-tenant | `.planning/redesign/PHASE-V2.8-MULTI-TENANT.md` |
| V2.9 multi-project UI | `.planning/redesign/PHASE-V2.9-MULTI-PROJECT-UI.md` |
| V3.0 per-project RBAC | `.planning/redesign/PHASE-V3.0-PROJECT-RBAC.md` |
| V3.1 FP learning loop | `.planning/redesign/PHASE-V3.1-FP-LEARNING.md` |
| ALOUTE CI fix | `.planning/redesign/ALOUTE-CI-FIX.md` |
| RBAC debug runbook | `.planning/redesign/RBAC-DEBUG.md` |
| Docx delta (V2.7) | `.planning/redesign/DOCX-DELTA-V2.7.md` |
