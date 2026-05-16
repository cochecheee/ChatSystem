# Phase V3.3 — Auth hardening + Overview AI summary

**Branch**: `ft/imp-fe` (continue)
**Date**: 2026-05-16
**Driver**: 2 issue user phản hồi sau V3.2:
1. **Anonymous vẫn thấy hết data** — V3.2 chỉ gate finding actions (approve/revoke/explain) + member CRUD. Reads (`/projects`, `/findings`, `/stats/*`, `/github/runs`) vẫn cho phép request không auth.
2. **Cần module summary trên Overview** — Gemini phân tích tóm tắt vắn tắt findings hiện tại cho hội đồng nhìn 5 giây hiểu trạng thái.

## Phần A — Auth hardening (bug fix, không phải feature)

### Vấn đề

Hiện trạng (`/openapi.json` check):
| Endpoint | Auth | Leak data? |
|---|---|---|
| `GET /projects` | none | Có — list all projects + URLs |
| `GET /findings` | none | Có — list all findings từ mọi project |
| `GET /findings/{id}` | none | Có |
| `GET /stats/overview` | none | Có |
| `GET /stats/latest-scan` | none | Có |
| `GET /github/runs` | none | Có — workflow runs metadata |
| `GET /findings/gate-count` | none | Có (nhưng CI cần — special case) |
| `POST /webhook/pipeline-complete` | CI_WEBHOOK_TOKEN | OK |
| `POST /findings/{id}/explain` | JWT + RBAC (V3.2 fix) | OK |
| `POST /api/chat/command` (approve/revoke) | JWT + RBAC (V3.2 fix) | OK |

Cả 6 endpoint trên = anonymous read, ngược lại tinh thần RBAC.

### Plan

1. **Default require auth on read endpoints** + kill-switch để rollback dễ:
   - `ANONYMOUS_READ_ENABLED: bool = False` (default off — chặt)
   - Khi false: thêm `Depends(get_current_user)` vào mọi GET trên `/projects`, `/findings`, `/stats/*`, `/github/runs/*`
   - Khi true (legacy): bypass, behave như V2.x

2. **Special case: `/findings/gate-count`** — security-gate composite CI gọi không auth:
   - Option (a) Giữ anonymous (counts là số non-sensitive)
   - Option (b) Accept `Authorization: Bearer <CI_WEBHOOK_TOKEN>` thay JWT
   - Đề xuất **(b)** — đồng nhất với webhook auth pattern, security-gate đã có `dashboard_url` secret nên dễ pass token

3. **Project visibility filter** khi RBAC on (đã có ở V3.0):
   - `GET /projects` → trả `[]` cho user không có membership (đã làm)
   - Mở rộng: `GET /findings`, `/stats/overview`, `/github/runs` cũng filter theo user.memberships
   - Logic: nếu user.role != "admin" AND RBAC on → chỉ trả data của project user là member

4. **Frontend handle 401**:
   - Auth-aware fetch wrapper: bắt 401 → trigger LoginModal auto-open
   - Topbar Sign-in button đã có (V2.9 polish)

5. **Tests**:
   - 6 endpoints × 2 cases (anonymous + authed) = 12 test
   - +3 tests cho per-project filter (developer thấy project 1 only, không thấy project 2 findings)
   - +1 test cho gate-count accept webhook token

**Effort**: 4-5h
**Risk**: trung — breaking change cho client cũ. Mitigate bằng kill-switch `ANONYMOUS_READ_ENABLED`.

## Phần B — Overview AI Summary (feature nhỏ, tận dụng Gemini có sẵn)

### Goal

Card top trên Overview page render 1 paragraph + 3-5 bullet tóm tắt trạng thái bảo mật hiện tại, dùng Gemini. Defense viewer scan 5 giây hiểu ngay.

### Visual contract — rich-formatted card

Mục tiêu: defense viewer scan **5 giây** hiểu trạng thái. Không phải bức tường text.

Layout 4 section, mỗi section là 1 strip có icon + heading + content:

```
┌──────────────────────────────────────────────────────────────────────┐
│  ┌─────┐                                                              │
│  │ AI  │  Project Risk Posture                                  ⟳ ↗ │
│  │ ◆◆  │  cochecheee/SAST_CICD · run #25948847479 · 14:23           │
│  └─────┘                                                              │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  📊 Overview                                                          │
│  Project ALOUTE có **184 finding** đang tracked. Mức nghiêm           │
│  trọng tập trung ở **14 CRITICAL** và **82 HIGH** — chiếm 52%        │
│  pipeline. AI đã phân tích 5/184 (2.7%) — cần triage thêm để         │
│  giảm noise.                                                          │
│                                                                       │
│  🚨 Top Risks                                              [3 of 184] │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ ●● CRITICAL  java/path-injection      FileUploadService.java   │ │
│  │     CSRF protection disabled, RCE possible via Spring SpEL     │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │ ●● CRITICAL  CVE-2022-1471            snakeyaml 1.30           │ │
│  │     Known DoS vulnerability — upgrade ≥ 2.0                    │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │ ● HIGH       java/ssrf                UrlPreviewController.java │ │
│  │     SSRF qua user-supplied URL, missing host allowlist         │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                       │
│  💡 Recommended Actions                                               │
│  1. **Fix 14 critical trước** — pipeline đang block deploy           │
│  2. Chạy `/triage` cho 82 high → AI phân loại FP/TP                  │
│  3. Upgrade snakeyaml → bun loose nhất trong deps                    │
│                                                                       │
│  📈 Pipeline Health: 12/15 runs pass (80%)  ✓ Trending stable        │
│                                                                       │
├──────────────────────────────────────────────────────────────────────┤
│  Generated by Gemini 2.5 Flash · cached 10m · TTL 5m remaining       │
└──────────────────────────────────────────────────────────────────────┘
```

**Visual elements**:
- **Severity dots**: `●●` critical (red), `●` high (orange), `◐` medium, `○` low — match Vulns page color tokens
- **Inline code**: rule_id và CVE-id bọc `<code>` mono font
- **File paths**: bold + truncate dài
- **Bold inline numbers**: `**14 CRITICAL**` highlight stat
- **Markdown render**: Backend trả markdown; FE dùng `react-markdown` (đã trong deps? cần check) hoặc custom renderer đơn giản (bold + code + list)

### Schema response từ BE (structured output từ Gemini)

```typescript
interface AiSummaryResponse {
  project_id: number | null;
  run_id: number | null;
  generated_at: string;       // ISO timestamp
  cached: boolean;
  cache_ttl_remaining: number; // seconds
  model: string;               // "gemini-2.5-flash"

  // Markdown-formatted sections — FE render đẹp
  overview_md: string;          // 2-3 câu, markdown
  top_risks: Array<{
    severity: 'critical' | 'high' | 'medium';
    rule_id: string;
    file_path: string;
    one_line_reason: string;    // Gemini-generated, Vietnamese
    finding_id: number;          // click-through to Vulns detail
  }>;
  recommendations_md: string;   // 1-3 numbered actions, markdown

  // Computed metrics (not AI-generated, deterministic)
  pipeline_health: {
    runs_total: number;
    runs_passed: number;
    pass_rate_pct: number;
    trend: 'improving' | 'stable' | 'degrading';
  };
}
```

**Tại sao chia `overview_md` + `top_risks` + `recommendations_md` thay vì 1 blob?**:
- Top risks là structured (severity, rule_id, file) → FE render card riêng có click-through
- Overview + recommendations là free-text → markdown đủ flexibility
- Defense viewer thấy structure rõ ràng, không phải 1 paragraph dài

### Gemini prompt (system instruction)

```
You are a senior application security analyst writing a 30-second briefing
for a tech lead. Output JSON matching the schema below.

Input: stats summary + top 10 critical/high findings + recent run pass rate.

Rules:
- Vietnamese language for all narrative fields.
- overview_md: 2-3 sentences, mention exact numbers from stats.
- top_risks: pick 3 most impactful from input. one_line_reason in Vietnamese,
  ≤ 20 words, MUST cite the actual vulnerability mechanism (e.g., "SSRF qua
  user-supplied URL", not just "security issue").
- recommendations_md: numbered list, 1-3 items, actionable verbs
  ("Fix", "Upgrade", "Triage"), tie to specific finding counts.
- Pipeline health is computed by backend — DO NOT generate.

Be terse. No filler. No marketing tone.
```

### Frontend rendering

`<OverviewAiSummary />` component structure:

```tsx
<Card>
  <Header icon="ai-orb" title="Project Risk Posture" subtitle={...} actions={<Refresh/>} />
  <Section icon="📊" title="Overview">
    <Markdown>{data.overview_md}</Markdown>
  </Section>
  <Section icon="🚨" title="Top Risks" badge={`${data.top_risks.length} of ${total}`}>
    {data.top_risks.map(r => <RiskRow key={r.finding_id} {...r} onClick={openFinding}/>)}
  </Section>
  <Section icon="💡" title="Recommended Actions">
    <Markdown>{data.recommendations_md}</Markdown>
  </Section>
  <Section icon="📈" title="Pipeline Health" inline>
    {data.pipeline_health.runs_passed}/{data.pipeline_health.runs_total} pass
    <TrendBadge value={data.pipeline_health.trend} />
  </Section>
  <Footer>Generated by {data.model} · cached · TTL {ttl}s</Footer>
</Card>
```

**Markdown subset rendered** (no library, ~30 lines custom):
- `**bold**` → `<strong>`
- `` `code` `` → `<code class="mono">`
- `1. item` numbered list
- `- item` bullet list
- newlines preserved

**RiskRow component**: severity dot + rule_id (mono) + file_path (truncated mid) + reason
on click → navigate to Vulns page với `?finding=<id>` (đã có pattern).

### Loading states

- Initial load: skeleton card với 3 placeholder lines + shimmer animation
- Refresh: nút ⟳ spin + dim content nhưng giữ visible
- Error: red banner inline "AI summary unavailable: <message>" + retry button
- Empty (no findings): card chỉ show 1 line "Không có finding nào trong project này — hệ thống sạch ✓"

### Backend

**Endpoint**: `GET /findings/ai-summary?project_id=&run_id=`

**Service**: `mcp/src/services/llm/summary.py` (mới)
- Aggregate inputs: `count_with_filters(severity=critical/high)`, recent 10 crit/high findings (rule_id + file_path), `count_ai_analyzed`, latest run pass rate
- Build prompt — Vietnamese, structured output:
```python
class SummaryOutput(BaseModel):
    overview: str           # 1-2 câu
    key_risks: list[str]    # 3-5 bullet
    recommendations: str    # 1-2 câu
```
- Gemini call (re-use per-project credentials path từ V2.8)
- **Cache** trong DB hoặc in-memory: key = (project_id, run_id_or_latest), TTL 10 phút, tránh gọi Gemini mỗi page refresh

**Cache strategy**: simple in-memory dict `{(pid, rid): (output, generated_at)}` — đủ cho thesis scope. Khi production cần Redis.

**Endpoint params**:
- `project_id` (optional)
- `run_id` (optional — default latest run with findings)
- `force_refresh=true` (skip cache, regenerate)

**Auth**: JWT required (phần A đã gate)

### Frontend

**Component**: `dashboard/src/components/OverviewAiSummary.tsx`
- Card ở đầu Overview (trên KPI grid)
- Show loading skeleton trong khi chờ Gemini (~3-5s lần đầu)
- Show generated_at + nút refresh
- Auto-load khi `activeProjectId` change
- Auto-cache trên FE level: lưu output trong React state, không hit API lại trong session

**Layout integration**:
```
[ AI Summary card ]
[ KPI grid ]
[ Donut by severity ]
[ Top rules triggered + Recent crit/high ]
```

**Effort**: 4-5h backend + 2-3h frontend

## Sequencing recommendation

| Order | Việc | Lý do |
|---|---|---|
| 1 | Phần A.1 — gate read endpoints với kill-switch | Quick win, ship đầu |
| 2 | Phần A.2 — gate-count accept webhook token | Pair với A.1 để CI không break |
| 3 | Phần A.3 — per-project visibility filter | Mở rộng tier V3.0 |
| 4 | Phần A.4+5 — FE 401 handling + tests | Hoàn thiện A |
| 5 | Phần B BE — AI summary endpoint + cache | Bắt đầu feature |
| 6 | Phần B FE — Overview card | Demo-ready |

**Total**: 10-13h
**Target pytest**: 276 → 292 (+16: 12 auth + 1 gate-count + 3 filter)

## Decision points

1. **Kill-switch default**: `ANONYMOUS_READ_ENABLED=false` (chặt) vs `true` (legacy). Đề xuất **false** — V3.3 là quality phase, ưu tiên security.

2. **Per-project filter scope** trên `/findings` và `/stats`:
   - Option A: Filter implicit theo user.memberships khi RBAC on (không cần pass project_id explicit). Backward compat tốt.
   - Option B: Force user pass `project_id` query param khi RBAC on, 400 nếu không pass.
   - Đề xuất **A** — không break dashboard hiện hữu.

3. **AI summary cache**:
   - Option A: In-memory dict (đơn giản, mất khi restart)
   - Option B: Cache trong `Finding.ai_analysis` field một row đặc biệt
   - Option C: New table `ai_summaries`
   - Đề xuất **A** — thesis scope, Redis là overkill

4. **Force refresh button trên FE**: có nút "Regenerate" không?
   - Đề xuất **có** — defense viewer có thể demo "live AI" bằng cách click

5. **Auto-refresh interval**:
   - Đề xuất KHÔNG poll — chỉ load khi vào page hoặc switch project. Mỗi 10 phút TTL trên BE cache. Người dùng bấm refresh nếu cần.

## Acceptance criteria

Sau khi ship:
- [ ] `curl /projects` không auth → 401
- [ ] `curl /findings?project_id=2` không auth → 401
- [ ] `curl /findings?project_id=2 -H "Authorization: Bearer <jwt>"` (user outsider) → 403 hoặc empty
- [ ] `curl /findings?project_id=2 -H "Authorization: Bearer <jwt>"` (member) → data
- [ ] `curl /findings/gate-count` với CI token → 200
- [ ] Overview load → AI summary card render trong ~5s lần đầu, ~50ms lần 2 (cache)
- [ ] Switch project trong topbar → summary refresh
- [ ] Click refresh nút → cache bust, regenerate
