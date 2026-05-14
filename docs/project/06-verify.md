# 06 — Verify Checklist

Curl commands + expected output để verify từng tầng. Sắp theo phase V2.x: chạy theo thứ tự, mỗi section là 1 độc lập có thể skip nếu chưa cần.

> **TL;DR test full stack 1 lệnh**: ở dưới cùng có script all-in-one.

---

## A. SMOKE — Health 3 service (30 giây)

```powershell
# mcp (chat-system backend)
curl -m 60 https://mcp-l958.onrender.com/health
# ✅ {"status":"healthy"}

# sample-python (inheritor staging) — 22s cold start lần đầu
curl -m 60 https://sample-python-latest.onrender.com/health
# ✅ {"status":"ok"}

# dashboard (Static Site) — sau khi V2.5 sync
curl -m 30 -I https://dashboard-XXXX.onrender.com/
# ✅ HTTP/2 200
```

**Cold start tips**:
- mcp + sample-python free tier → sleep sau 15 phút idle → request đầu mất 22-30s
- dashboard Static Site KHÔNG cold start (CDN)

---

## B. V2.1 — Core SAST pipeline

### B.1. CORS

```powershell
curl -i -X OPTIONS https://mcp-l958.onrender.com/health `
  -H "Origin: http://localhost:5173" `
  -H "Access-Control-Request-Method: GET"
```

✅ `HTTP/2 200` với header `access-control-allow-origin: http://localhost:5173`
❌ `400 Disallowed CORS origin` → fix `CORS_ORIGINS` env trên Render

### B.2. Project row tồn tại

```powershell
curl https://mcp-l958.onrender.com/projects
```

✅ `[{"id":1,"name":"sample-python (sast-action demo)",...}]`

❌ `[]` → mcp restart làm mất DB (`/tmp/mcp.db` ephemeral). Tạo lại:
```powershell
curl -X POST https://mcp-l958.onrender.com/projects `
  -H "Content-Type: application/json" `
  -d '{"name":"sample-python (sast-action demo)","github_url":"https://github.com/cochecheee/sample-python"}'
```

### B.3. GitHub API connection

```powershell
curl "https://mcp-l958.onrender.com/github/runs?limit=3"
```

✅ Array 3 run gần nhất với status/conclusion/sha
❌ 401 → `GITHUB_TOKEN` sai. ❌ 404 → `GITHUB_OWNER`/`GITHUB_REPO` sai.

### B.4. End-to-end CI → ingest

```powershell
cd D:\School\DoAnTotNghiep\sample-python
git commit --allow-empty -m "test: V2.1 verify"
git push origin main
```

Đợi ~5 phút, check:

```powershell
# Lấy run_id mới nhất
$runId = (curl -s "https://mcp-l958.onrender.com/github/runs?limit=1" | ConvertFrom-Json)[0].id

# Force reprocess (cần thiết nếu webhook timed out do cold start)
curl -X POST "https://mcp-l958.onrender.com/github/runs/$runId/reprocess"
# ✅ {"status":"accepted",...}

# Đợi 30s, check finding count
Start-Sleep -Seconds 30
curl https://mcp-l958.onrender.com/stats/overview
# ✅ total > 100, by_tool có semgrep + trivy + bandit
```

---

## C. V2.2 — CD pipeline (build + deploy)

### C.1. Image trên Docker Hub

```powershell
curl -s "https://hub.docker.com/v2/repositories/tienbui482/sample-python/tags?page_size=5" | ConvertFrom-Json | Select -ExpandProperty results | Select name, last_updated
```

✅ Có 2 tag: `latest` + `<7-char-sha>` (matching commit gần nhất)

### C.2. Render auto-redeploy

Sau khi mày push commit vào `sample-python`:

1. Vào https://dashboard.render.com → service `sample-python`
2. Tab **Events** → mới nhất phải là "Deploy triggered via webhook"
3. Đợi build xong (~1-2 phút) → "Deploy succeeded"

### C.3. Staging vẫn alive sau redeploy

```powershell
curl -m 60 https://sample-python-latest.onrender.com/
# ✅ HTML với 4 vuln endpoint link
```

### C.4. Vuln endpoints fire correctly

```powershell
# SQL injection (Bandit B608 sẽ flag dòng này khi scan)
curl "https://sample-python-latest.onrender.com/user?id=1"
# ✅ <pre>[(1, 'alice', 'alice@example.com')]</pre>

# XSS reflection (Semgrep flag)
curl "https://sample-python-latest.onrender.com/greet?name=Tien"
# ✅ <h2>Hello, Tien!</h2>

# Cmd injection (Bandit B605)
curl "https://sample-python-latest.onrender.com/ping?host=127.0.0.1"
# ✅ <pre>ping rc=...</pre>
```

---

## D. V2.3 — DAST (OWASP ZAP)

### D.1. Verify CI job `dast` chạy

Vào https://github.com/cochecheee/sample-python/actions → run mới nhất → phải có 3 job:
- ✅ `sast`
- ✅ `cd`
- ✅ `dast` (chạy ZAP baseline scan ~5 phút)

### D.2. DAST findings ingested

```powershell
curl "https://mcp-l958.onrender.com/findings?category=dast&limit=5"
```

✅ Array finding với `"tool":"owasp-zap"`, `severity` info/low/medium, `file_path` = "GET https://..."

```powershell
curl https://mcp-l958.onrender.com/stats/overview
```

✅ Có `dast_open > 0`, `by_tool` có `owasp-zap`

### D.3. Dashboard Runtime tab

Khi V2.5 dashboard live:
- Mở dashboard URL → click tab **Runtime (DAST)** ở sidebar
- ✅ Bảng list ZAP findings: severity, alert name, URL/method, CWE, evidence

---

## E. V2.4 — Monitor + alert

### E.1. Monitor enabled

```powershell
curl https://mcp-l958.onrender.com/monitor/summary
```

✅ `{"hours":24,"targets":[{"target_url":"https://sample-python-latest.onrender.com/health","checks":N,...}]}` với N > 0

❌ `{"targets":[]}` → `MONITOR_ENABLED=false` hoặc `MONITOR_TARGETS` empty → set env trên Render UI

### E.2. Manual ping

```powershell
curl -X POST "https://mcp-l958.onrender.com/monitor/ping"
```

✅ `{"checks_executed":N}` — N = số target trong `MONITOR_TARGETS`

### E.3. Uptime tăng dần

```powershell
curl https://mcp-l958.onrender.com/monitor/summary
Start-Sleep -Seconds 300   # đợi 1 cycle
curl https://mcp-l958.onrender.com/monitor/summary
```

✅ Cùng target, `checks` tăng (300s → 1 check mới), `uptime_pct` tiến gần 100%

### E.4. Alert list

```powershell
curl "https://mcp-l958.onrender.com/monitor/alerts"
```

✅ Array (rỗng nếu chưa có sự kiện down)

### E.5. Force down scenario (manual demo)

Nếu muốn thấy alert raise, tắt sample-python service trên Render → đợi ≥ 2 cycle (10 phút):

```powershell
# Sau 10 phút staging down:
curl "https://mcp-l958.onrender.com/monitor/alerts?kind=down"
```

✅ 1 alert mới với `kind=down`, `notified_at` có giá trị nếu SMTP đã configure

Bật lại service → sau 5 phút:
```powershell
curl "https://mcp-l958.onrender.com/monitor/alerts?kind=recovered"
```

✅ `recovered` alert + down alert có `acknowledged_at`

### E.6. Email (chỉ test khi SMTP configured)

Set 6 env var trên Render mcp:
```
SMTP_HOST=sandbox.smtp.mailtrap.io
SMTP_PORT=587
SMTP_USER=<mailtrap user>
SMTP_PASS=<mailtrap pass>
EMAIL_FROM=alerts@chat-system.local
EMAIL_TO=<your email>
```

Render auto-redeploy. Trigger down scenario như E.5 → check Mailtrap inbox.

### E.7. Dashboard Monitor tab

Khi V2.5 dashboard live:
- Sidebar → **Monitor** tab
- ✅ 1 card per target với uptime %
- ✅ Bảng alerts (rỗng hoặc list)
- ✅ Bảng "Recent pings (6h)" — cập nhật mỗi 30s
- Button **Ping now** → trigger /monitor/ping → table cập nhật

---

## F. V2.5 — Dashboard Static Site

### F.1. Service exists

```powershell
curl -I -m 30 https://dashboard-XXXX.onrender.com/
```

✅ `HTTP/2 200`, `Content-Type: text/html`

### F.2. SPA rewrite hoạt động

```powershell
curl -I -m 30 https://dashboard-XXXX.onrender.com/runtime
```

✅ `HTTP/2 200` (fallback rewrite to index.html)
❌ `HTTP/2 404` → render.yaml routes section sai

### F.3. CORS từ dashboard → mcp

Mở dashboard URL → browser DevTools Console phải KHÔNG có lỗi CORS khi fetch.

Nếu có lỗi `Disallowed CORS origin` → thêm dashboard URL vào `CORS_ORIGINS` env trên mcp service Render.

### F.4. Visual smoke (dashboard manual)

Tabs phải render được data:
- **Overview**: KPI cards có số
- **Pipelines**: list run từ GitHub
- **Vulnerabilities**: list SAST finding
- **Dependencies**: gom CVE theo package
- **Runtime (DAST)**: ZAP finding bảng
- **Monitor**: uptime card + alert list

---

## G. End-to-end full stack — 1 script

```powershell
# Set base URLs
$mcp = "https://mcp-l958.onrender.com"
$staging = "https://sample-python-latest.onrender.com"

Write-Host "1. mcp health:" -ForegroundColor Cyan
curl -s -m 60 "$mcp/health"
Write-Host ""

Write-Host "2. staging health:" -ForegroundColor Cyan
curl -s -m 60 "$staging/health"
Write-Host ""

Write-Host "3. stats overview:" -ForegroundColor Cyan
curl -s "$mcp/stats/overview" | ConvertFrom-Json | Format-List total, sast_open, deps_open, dast_open, sast_critical_high, deps_critical_high, dast_critical_high

Write-Host "4. by tool:" -ForegroundColor Cyan
$ov = curl -s "$mcp/stats/overview" | ConvertFrom-Json
$ov.by_tool

Write-Host "5. monitor uptime:" -ForegroundColor Cyan
curl -s "$mcp/monitor/summary" | ConvertFrom-Json | Select-Object -ExpandProperty targets | Format-Table target_url, checks, uptime_pct, avg_latency_ms

Write-Host "6. recent alerts:" -ForegroundColor Cyan
$alerts = curl -s "$mcp/monitor/alerts?limit=5" | ConvertFrom-Json
if ($alerts.Count -eq 0) { Write-Host "  no alerts (good)" -ForegroundColor Green } else { $alerts | Format-Table kind, severity, title, raised_at }

Write-Host "7. GitHub runs (3 mới nhất):" -ForegroundColor Cyan
curl -s "$mcp/github/runs?limit=3" | ConvertFrom-Json | Select-Object run_number, status, conclusion, display_title | Format-Table
```

Lưu thành `D:\School\DoAnTotNghiep\verify.ps1`, chạy `.\verify.ps1` mỗi khi muốn smoke test.

---

## Troubleshoot quick map

| Symptom | Likely cause | Check |
|---|---|---|
| `curl /health` timeout | Cold start Render free tier | Retry với `-m 60` |
| `Disallowed CORS origin` | `CORS_ORIGINS` thiếu | Render mcp env |
| Invalid workflow file | Permissions/secrets schema | [05-reusable-workflow.md](05-reusable-workflow.md) |
| 0 findings sau CI pass | Profile không match artifact | `mcp/config/profiles/github-actions-default.yml` |
| Project rỗng sau redeploy | SQLite ephemeral, mcp restart | Re-tạo qua POST /projects |
| Bearer token mismatch | `CI_WEBHOOK_TOKEN` != `MCP_WEBHOOK_TOKEN` | Render env + GitHub secret |
| Gemini API 403 | Key expired/quota | Generate key mới ở Google AI Studio |
| Monitor `targets:[]` | `MONITOR_ENABLED=false` hoặc `MONITOR_TARGETS` empty | Render env |
| Email không gửi | `SMTP_HOST` empty | Render env (skip nếu chưa cần) |
| Dashboard 404 | Render Blueprint chưa Sync sau push render.yaml | Click Sync ở Render UI |
| ZAP findings 0 | DAST job chưa chạy hoặc `dast: false` | sample-python security.yml |

Chi tiết hơn ở [docs/troubleshooting.md](../troubleshooting.md).

---

## Cheat sheet — đường tắt cho từng kịch bản

| Tao muốn... | Lệnh |
|---|---|
| Smoke test 5 endpoint | `curl $mcp/health; curl $staging/health; curl $mcp/stats/overview` |
| Re-ingest 1 run cụ thể | `curl -X POST $mcp/github/runs/<run_id>/reprocess` |
| Trigger monitor ngay | `curl -X POST $mcp/monitor/ping` |
| Force trigger CI mới | `git commit --allow-empty -m "test" && git push` ở sample-python |
| Pre-warm cold start | `curl -m 60 $mcp/health; curl -m 60 $staging/health` |
| Tạo lại Project sau reset | `curl -X POST $mcp/projects -d ...` (xem B.2) |
| Acknowledge alert | `curl -X POST $mcp/monitor/alerts/<id>/ack` |
