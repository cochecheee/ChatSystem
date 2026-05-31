# Bug fixes — manual procedures

> Append-only log của các bug đã chẩn đoán + cách fix manual. Convention:
> mỗi bug có 1 section `## YYYY-MM-DD — <title>` với 4 phần: Symptom, Root
> cause, Fix (steps), Verify. Khi gặp bug mới → append section ở cuối, KHÔNG
> chỉnh sửa lịch sử section cũ.

---

## 2026-05-29 — SQL echo log spam ở local

### Symptom
```
INFO  [sqlalchemy.engine.Engine] [cached since 94.09s ago] ()
INFO  [sqlalchemy.engine.Engine] ROLLBACK
```
xuất hiện liên tục trong terminal uvicorn local.

### Root cause
`mcp/src/core/db.py`:
```python
engine = create_async_engine(settings.DATABASE_URL,
                              echo=settings.APP_ENV == "development", ...)
```
`.env` có `APP_ENV=development` → echo=True → SQLAlchemy in mọi statement + transaction event. "cached since" là statement-cache reuse (bình thường), ROLLBACK lặp = poller / FE polling fail rồi rollback.

### Fix — 3 cách

**Cách A — Đổi APP_ENV (production-safe nhưng sẽ trigger fail-fast guard)**

`mcp/.env`:
```ini
APP_ENV=production
```

⚠️ Gotcha: `main.py:_enforce_production_safety()` sẽ refuse start nếu một trong 3:
- `SECRET_KEY` còn default `change-me-in-production-min-32-chars`
- `CI_WEBHOOK_TOKEN` rỗng
- `CORS_ORIGINS` rỗng

Local đang fail cả 3. Nếu muốn dùng `APP_ENV=production` ở local, phải fill 3 biến đó trong `.env`.

**Cách B — Giữ dev mode, chỉ tắt echo (không commit)**

`mcp/src/core/db.py`:
```python
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # was: echo=settings.APP_ENV == "development"
    connect_args=_engine_connect_args(settings.DATABASE_URL),
)
```
Chỉ sửa local — không commit để giữ behavior gốc cho team.

**Cách C — Tìm root cause ROLLBACK (cleanest)**

Giữ echo, đọc backend log tìm dòng `ERROR` / `Exception` ngay trước mỗi ROLLBACK. Common cause: poller fail vì `GITHUB_TOKEN` empty, hoặc FE call endpoint sai param. Fix root cause → rollback hết → log sạch tự nhiên.

### Verify
- Restart uvicorn
- Refresh dashboard 1 phút, quan sát terminal: không còn dòng ROLLBACK lặp

---

## 2026-05-29 — Render Postgres thiếu 3 cột V3.6 sau khi push code

### Symptom
Sau khi push commits V3.5/V3.6 + MySQL patch lên `ft/imp-fe`, Render deploy thành công (health=200, openapi 41 paths) nhưng:
- `GET /projects` → 500
- `GET /findings` → 500
- `GET /findings/gate-count` → 500
- `GET /stats/overview` → 200 (vẫn work)

### Root cause
HEAD `Project` ORM model có 3 cột V3.6 chưa có trên Render Postgres:
- `archived_at` (V3.6 soft delete)
- `gate_critical_threshold` (V3.6 per-project gate)
- `gate_high_threshold` (V3.6 per-project gate)

Alembic migration không stamp được vì:
1. `init_db()` chạy `Base.metadata.create_all()` TRƯỚC → tạo `pipeline_runs`, `audit_log`, `webhook_deliveries`
2. Sau đó alembic `upgrade head` → migration script gọi `create_table('pipeline_runs')` → table đã exist → raise
3. Exception caught trong try/except → boot tiếp nhưng `alembic_version` table không stamp
4. ALTER TABLE statements ở phần sau migration script không bao giờ chạy

`/stats/overview` vẫn work vì chỉ count `findings` table (không touch `projects`).

### Fix — 3 cách connect tới Render Postgres

**Connection info (External Database URL)**
```
Host:     dpg-d82oif83kofs73d15mdg-a.singapore-postgres.render.com
Port:     5432
User:     mcp
Password: <từ Render Dashboard → mcp-db → Connect>
DB:       mcp_4v1y
SSL:      Require
```

**Cách A — Render PSQL shell**

1. https://dashboard.render.com → `mcp-db` → tab "Connect" → "PSQL Command"
2. Copy lệnh, paste vào terminal có psql:
   ```powershell
   winget install PostgreSQL.PostgreSQL   # nếu chưa có psql
   ```
3. Khi vào prompt `mcp_4v1y=>`:
   ```sql
   ALTER TABLE projects ADD COLUMN gate_critical_threshold INTEGER NOT NULL DEFAULT 0;
   ALTER TABLE projects ADD COLUMN gate_high_threshold INTEGER NOT NULL DEFAULT 5;
   ALTER TABLE projects ADD COLUMN archived_at TIMESTAMP WITH TIME ZONE NULL;
   \d projects
   \q
   ```

**Cách B — pgAdmin GUI**

1. Tải https://www.pgadmin.org/download/pgadmin-4-windows/
2. Add server với info trên (SSL Mode = Require)
3. Right click `projects` table → Query Tool → chạy 3 ALTER

**Cách C — DBeaver (cross-platform)**

1. Tải https://dbeaver.io/download/
2. New Connection → PostgreSQL → SSL tab = Required → fill info
3. SQL Editor → paste 3 ALTER → Ctrl+Enter

### Verify
```powershell
$tok = (Invoke-RestMethod -Method POST 'https://mcp-l958.onrender.com/api/chat/auth/token' -ContentType 'application/json' -Body '{"username":"smoke","role":"admin"}').access_token
$H = @{Authorization="Bearer $tok"}
Invoke-RestMethod 'https://mcp-l958.onrender.com/projects' -Headers $H | ConvertTo-Json -Depth 3
```
Phải trả về JSON list 2 projects thay vì 500.

---

## 2026-05-29 — `alembic_version` table không tồn tại trên Render Postgres

### Symptom
Trên Render, mỗi lần restart container log có:
```
Alembic upgrade failed — continuing without migration
```
Schema migration không apply, deploy nào cũng cần manual ALTER.

### Root cause
Liên quan tới Bug #2 ở trên. Khi alembic `upgrade head` fail giữa chừng, nó không stamp `alembic_version` table. Lần boot tiếp theo coi DB là "fresh" → thử apply migration từ đầu → fail tương tự → loop.

### Fix — 2 cách

**Cách A — SQL trực tiếp (kết hợp với Bug #2)**

Cùng SQL session với Bug #2, chạy thêm:
```sql
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);
INSERT INTO alembic_version (version_num) VALUES ('bdf2034e591c');
SELECT * FROM alembic_version;
```

Output mong đợi:
```
 version_num
--------------
 bdf2034e591c
```

**Cách B — `alembic stamp` CLI (cleaner)**

```powershell
cd D:\School\DoAnTotNghiep\chat-system\mcp
$env:DATABASE_URL="postgresql+asyncpg://mcp:<password>@dpg-d82oif83kofs73d15mdg-a.singapore-postgres.render.com/mcp_4v1y"
.venv\Scripts\python.exe -m alembic stamp head
```

Alembic tự tạo bảng + insert revision đúng.

### Verify
```sql
SELECT version_num FROM alembic_version;
```
Phải trả về `bdf2034e591c`. Lần boot Render tiếp theo, log sẽ thấy `Alembic upgrade head completed` (no-op vì đã ở head).

---

## 2026-05-29 — UPDATE: Root cause thật của Bug 2 + Bug 3 là Dockerfile

### Symptom
2 bug ngay trên (V3.6 columns missing + alembic_version not stamped) — **cùng root cause, fix 1 dòng**.

### Root cause thật
`mcp/Dockerfile` runtime stage copy `src/`, `config/`, `scripts/` nhưng **KHÔNG copy `alembic.ini` + `migrations/`**:

```dockerfile
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/
# alembic.ini + migrations/ — missing!
```

Khi container boot, `_run_alembic_upgrade()` trong `core/db.py` check:
```python
ini_path = repo_root / "alembic.ini"
if not ini_path.exists():
    log.warning("alembic.ini not found at %s — skipping", ini_path)
    return
```
→ File không có → silent skip → migration **không bao giờ chạy** trên Render → 3 cột V3.6 không apply + `alembic_version` table không tạo.

`/stats/overview` vẫn work vì chỉ count `findings` table; những endpoint touch `projects` (SELECT include cột chưa có) → 500.

(Manual SQL fix ở Bug 2 vẫn đúng — nó patch symptom. Nhưng root cause là Dockerfile.)

### Fix — sửa 1 dòng + push

`mcp/Dockerfile`:
```dockerfile
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY alembic.ini ./alembic.ini
COPY migrations/ ./migrations/
```

Commit + push `ft/imp-fe` → Render rebuild image → container có alembic files → `_run_alembic_upgrade()` thấy ini → `env.py` (đã được V3.6/A1 wire inject `DATABASE_URL` từ `settings`) → connect Render Postgres → migration script idempotent (uses `_table_exists` / `_column_exists`) → tạo 3 cột V3.6 + tables thiếu + stamp `alembic_version=bdf2034e591c`.

### Verify (sau ~74s từ push)
```
projects=2 gate=c=0/h=231
findings total=1316 sample=codeql/info
Tables (13): + alembic_version, audit_log, pipeline_runs, webhook_deliveries
projects columns: + gate_critical_threshold, gate_high_threshold, archived_at
alembic_version: bdf2034e591c
```

Commit hash: `14cac73 fix(deploy): include alembic.ini + migrations/ in Docker image`

### Bài học
- Khi thêm Alembic vào project hiện có (V3.6/A1), phải nhớ patch Dockerfile copy migration files. Không thì migration code không bao giờ chạy trong container.
- Khi `_run_alembic_upgrade()` "fail silent" (log warning rồi tiếp), nên thêm metric/alert. Hiện chỉ log INFO/WARNING — dễ miss.
- Manual SQL ALTER ở Bug 2 chỉ patch symptom. Lần deploy sau Render rebuild image vẫn missing alembic files → migration không chạy → cứ vài tháng phải fix tay nếu chưa fix Dockerfile.

---

## 2026-05-29 — `/findings/ai-summary` trả 500 + browser hiện "CORS blocked"

### Symptom
- Dashboard Overview hiện banner đỏ: `AI summary unavailable: TypeError: Failed to fetch`
- DevTools console: `Access to fetch at 'http://localhost:8000/findings/ai-summary?...' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present on the requested resource`
- Network: `GET /findings/ai-summary?... net::ERR_FAILED`

### Root cause
**Browser CORS error là misleading** — vấn đề thật là BE crash 500 không kèm CORS header → browser blame CORS.

Diagnose bằng repro script trực tiếp:
```
ClientError: 400 INVALID_ARGUMENT
{'error': {'code': 400, 'message': 'API key not valid. Please pass a valid API key.',
  'status': 'INVALID_ARGUMENT', 'details': [{...
  'reason': 'API_KEY_INVALID', 'domain': 'googleapis.com'}]}}
```

Google Gemini từ chối API key trong `.env` (key sai 1 ký tự). `summary.py:379` `_llm_caller(gemini, prompt)` raise `ClientError` → propagate qua FastAPI route → 500 raw không có CORS header → browser blame CORS.

Verify CORS thực tế:
```
OPTIONS preflight: 200
access-control-allow-origin: http://localhost:5173   ✓
access-control-allow-credentials: true                ✓
```
→ CORS config đúng. Vấn đề là **BE crash sau preflight thành công**.

### Fix — 2 phần

**Phần A (immediate): fix GEMINI_API_KEY trong `.env`**

Verify key đúng bằng curl:
```powershell
curl.exe -H "x-goog-api-key: $env:GEMINI_API_KEY" `
  "https://generativelanguage.googleapis.com/v1beta/models" | Select-Object -First 5
```

Nếu trả `API_KEY_INVALID` → key sai. Lấy key mới từ https://aistudio.google.com/app/apikey → paste vào `.env`:
```ini
GEMINI_API_KEY=AIzaSy...<đúng 39 ký tự>
```
Restart uvicorn.

**Phần B (defensive, nên thêm sau): BE handle ClientError gracefully**

`api/artifacts.py:findings_ai_summary` hiện không catch exception → 500 raw. Cải thiện:
```python
@router.get("/findings/ai-summary")
async def findings_ai_summary(...):
    try:
        result = await svc.generate(session, ...)
        return result.model_dump()
    except Exception as exc:
        log.warning("AI summary failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"AI service unavailable: {type(exc).__name__}",
        )
```

503 vẫn được CORS middleware add header → FE thấy proper JSON error → render "AI summary unavailable" với thông báo cụ thể thay vì "TypeError: Failed to fetch".

### Verify
1. Sau khi fix key + restart: reload Overview tab → banner đỏ biến mất, AI summary card hiển thị `overview_md` + `top_risks` + `recommendations`
2. Cố tình invalidate key (thêm chữ): banner đỏ vẫn hiện, nhưng dashboard không crash + console hiện 503 thay vì CORS error

### Bài học
- Khi browser report "CORS blocked: no Allow-Origin header", check trước xem BE có actually return response không (maybe crash 500). Dùng curl/PowerShell hit endpoint trực tiếp với header `Origin:` để bypass CORS, xem raw response.
- Mọi endpoint gọi external service (Gemini, GitHub) phải wrap try/except → return proper HTTP error (503/502) thay vì crash 500. CORS middleware chỉ inject header khi handler return response — exception bypass middleware.

---

## 2026-05-31 — FP feature pack A+B+C: đánh dấu FP từ UI, suppress shortcut, gate verdict BE

### Symptom (gap, không phải bug)
Trước khi feature pack này: việc đánh dấu finding là "không phải lỗi" để future scans bỏ qua chỉ làm được qua ChatOps `/revoke <id>` slash command — UX kém với 234+ findings. Backend V3.1 4-tier FP loop đã đầy đủ (Tier 1+2+3 auto + Tier 4 gate count) nhưng FE chưa wire button.

### Implementation
**A. Revoke button trong Vulns detail pane** (`pages/Vulns.tsx`)
- Add nút "Đánh dấu không phải lỗi" cạnh "Ask AI" (chỉ hiện khi `status !== 'REVOKED'`)
- Click mở `RevokeDialog` (đã sẵn có) → confirm gọi `POST /api/chat/command` với `/revoke + finding_id + justification`
- BE enforce `security_lead+` role + min 20-char justification
- Success → callback `onRevoked()` bump parent state → list re-fetch → row badge flip "Rev" + detail pane shows AUDIT TRAIL

**B. Suppression shortcut sau revoke** (`pages/Vulns.tsx`)
- Sau `handleRevoke` success, set `suppressOpen=true` → custom dialog hiện preview rule_id + file_glob + tool + 90d expiry
- Click "Tạo rule" → `POST /projects/{id}/suppressions` với prefilled fields
- Tier 2 SuppressionRule sẽ auto-REVOKE mọi finding tương lai match cùng pattern (xem `repositories/suppression_repo.py:rule_matches`)
- Khác Tier 1: Tier 1 chỉ match dedup_hash chính xác (file edit 1 dòng → hash đổi → không inherit). Tier 2 match pattern → robust với code changes.

**C. Gate verdict server-side** (`api/artifacts.py:findings_gate_count`)
- Trước: trả raw `{critical, high, medium, low}` — CI phải tự so threshold
- Sau: đọc `Project.gate_critical_threshold` + `gate_high_threshold` (V3.6 cols), trả thêm:
  - `policy: {gate_critical_threshold, gate_high_threshold}`
  - `verdict: "pass" | "fail"`
  - `blocking_reasons: string[]`
- CI chỉ cần check `verdict === "pass"` → pass/fail, không cần threshold logic client-side

### Verify (end-to-end Chrome DevTools E2E)
1. Login admin trên dashboard
2. Vulnerabilities tab → click finding #1170 ("Running flask app with host [IP_SCRUBBED]")
3. Click "Đánh dấu không phải lỗi" → modal mở, fill justification ≥20 char → "Thu hồi"
4. List badge flip "Rev", detail pane → Status REVOKED + AUDIT TRAIL hiển thị `Revoked by smoke-admin · 5/31/2026, 4:22:04 AM` + justification quoted
5. Suppression dialog FP-B tự pop → click "Tạo rule"
6. `GET /projects/1/suppressions` xác nhận:
   ```
   { id: 1, rule_id: "...", file_glob: "app.py", tool: "semgrep oss",
     created_by: "smoke-admin", expires_at: "2026-08-29T04:26:06" }
   ```
7. Gate verdict check: `GET /findings/gate-count?project_id=1` →
   ```json
   {"critical":0,"high":231,"policy":{"gate_critical_threshold":0,"gate_high_threshold":5},
    "verdict":"fail","blocking_reasons":["high=231 exceeds threshold 5"]}
   ```

### Known issues + future enhancements
- Suppression dialog dùng `finding` hiện tại — nếu list re-fetch và auto-select finding khác giữa revoke và dialog open, preview hiển thị rule của finding KẾ TIẾP. Không phải lỗi blocking (rule vẫn hợp lệ) nhưng UX subtle. Fix: capture `lastRevokedFinding` snapshot vào state.
- Chưa có bulk revoke (FP-D). Multi-select checkbox + batch justification — effort ~3h.
- AI Triage (Tier 3) đã có button nhưng không auto-suggest tạo Tier 2 rule sau khi N findings cùng rule_id bị revoked. Effort ~3h.
- Toast/notification lib chưa wire (Sonner trong dep nhưng unused). Hiện success/error message inline trong dialog. Có thể bổ sung sau.

### Bài học
- Backend V3.1 đã có FP loop đầy đủ — chỉ thiếu UI wire. Audit codebase trước khi quote effort: agent map-codebase tiết kiệm thời gian.
- ChatOps `/revoke` slash command + JWT là natural extension point — không cần endpoint REST riêng. Reuse `POST /api/chat/command` giảm code surface.
- Gate verdict ở BE thay vì CI client: CI runner thì stateless, threshold thay đổi trong dashboard không cần redeploy sast-action. Cleaner separation.

