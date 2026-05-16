# RBAC + Multi-Tenant Debug Plan

**Date**: 2026-05-16
**Symptoms**:
1. SAST_CICD (project id=2) shows zero findings on dashboard
2. RBAC gate does not deny non-member users — everyone sees both projects

## Root cause hypothesis

Both symptoms are explained by Render env vars not being effective:

| Var | Required value | Current evidence |
|---|---|---|
| `MULTI_TENANT_ENABLED` | `true` | `last_processed_run_id=None` cho ALOUTE — poller chưa iterate, webhook fallback env |
| `RBAC_PER_PROJECT` | `true` | `random-stranger` user thấy đủ 2 projects qua `GET /projects` |
| `FERNET_KEY` | set | Không block runtime; absence chỉ làm credentials plaintext |

Possible failure modes:
- A. User chưa add var trên Render
- B. Đã add nhưng spell sai (`MULTI_TENANT_ENABLE` thiếu `D`, etc.)
- C. Đã add đúng nhưng Render chưa restart instance (chỉ "Save & Deploy" mới reload env)
- D. Đã add + restart nhưng release đang chạy là V2.8 cache (như case lúc trước)

## Plan — 4 phase, fix theo thứ tự

### Phase 1 — Diagnostic endpoint (BE) — 15'

Ship `/health/flags` exposing flag state để curl verify Render config without UI access:

```
GET /health/flags
{
  "multi_tenant_enabled": false,
  "rbac_per_project": false,
  "fernet_configured": false,
  "version_marker": "v3.0"
}
```

Non-secret, safe to expose. Lets user/me/CI verify in 1s.

### Phase 2 — Flip flags (user action) — 2'

1. Render dashboard → service `mcp` → Environment
2. Add/edit 3 vars:
   - `MULTI_TENANT_ENABLED=true`
   - `RBAC_PER_PROJECT=true`
   - `FERNET_KEY=8xnfnyQlJZ7ZUZ0rE_5hdGjSHt5UocPgvTniqyCk-d0=` (sync:false)
3. Save → Render auto-restart (~1 phút)
4. Verify: `curl https://mcp-l958.onrender.com/health/flags` — phải thấy `true`

### Phase 3 — Trigger ALOUTE ingestion — 5'

Sau khi MULTI_TENANT_ENABLED=true:

**Path A — Wait for poller** (5 phút interval):
Poller sẽ iterate ALOUTE project, fetch workflow runs, ingest artifacts. Tự động.

**Path B — Manual webhook fire** (instant):
```powershell
$body = @{
    run_id = <latest-aloute-run-id>
    repository = 'cochecheee/SAST_CICD'
    pipeline_status = 'passed'
} | ConvertTo-Json
Invoke-RestMethod -Uri 'https://mcp-l958.onrender.com/webhook/pipeline-complete' `
    -Method Post -Body $body -ContentType 'application/json' `
    -Headers @{ Authorization = 'Bearer <CI_WEBHOOK_TOKEN>' }
```

**Path C — Trigger CI run** (slow but realistic):
Push 1 commit empty vào ALOUTE repo → CI chạy → notify step gửi webhook → route đúng project 2.

### Phase 4 — Verify RBAC active — 3'

Sau khi RBAC_PER_PROJECT=true + restart:

```bash
# Random user → phải thấy [] khi GET /projects
TOK=$(curl -X POST .../api/chat/auth/token \
  -d '{"username":"random","role":"developer"}' \
  -H 'Content-Type: application/json' | jq -r .access_token)
curl .../projects -H "Authorization: Bearer $TOK"
# Expected: []

# viewer-demo → thấy project 1 only
TOK=$(curl -X POST .../api/chat/auth/token \
  -d '{"username":"viewer-demo","role":"developer"}' ...)
curl .../projects -H "Authorization: Bearer $TOK"
# Expected: [{"id":1,...}]

# cochecheee owner → cả 2
# admin → cả 2
```

## Common pitfalls

1. **Stale JWT** — Token có memberships snapshot tại issue time. Nếu admin thêm `alice` làm member SAU khi alice đã login, JWT của alice chưa có membership đó. Solution: alice phải logout + login lại.

2. **Browser cache** — Dashboard cache `/projects` response. Hard refresh (Ctrl+Shift+R) sau khi flip flag.

3. **localStorage activeProjectId** — Nếu user đã set active project 2 trong topbar, sau flip RBAC và họ mất membership → dropdown vẫn nhớ ID cũ + có thể request fail. ProjectContext.refresh() đã handle drop active khi list không match.

4. **Webhook auth** — `CI_WEBHOOK_TOKEN` ở Render phải khớp `MCP_WEBHOOK_TOKEN` ở SAST_CICD Settings → Secrets. Mismatch → 403, không log finding.

## Future-proofing (out of scope for thesis demo)

- Refresh-token flow để revoke session khi admin kick member
- WebSocket push để re-fetch project list khi memberships change
- Audit log: log mọi membership grant/revoke + 403 attempts
