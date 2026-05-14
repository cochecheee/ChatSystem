# 06 — Verify Checklist

Curl commands + expected output để verify từng tầng. Chạy theo thứ tự từ trên xuống.

## 1. MCP health

```powershell
# Có thể mất 30-60s nếu cold start
curl -m 60 https://mcp-l958.onrender.com/health
```

✅ `{"status":"healthy"}`

## 2. CORS

```powershell
curl -i -X OPTIONS https://mcp-l958.onrender.com/health `
  -H "Origin: http://localhost:5173" `
  -H "Access-Control-Request-Method: GET"
```

✅ `HTTP/2 200` với header `access-control-allow-origin: http://localhost:5173`

❌ `HTTP/2 400 Disallowed CORS origin` → `CORS_ORIGINS` env chưa include origin này.

## 3. Project tồn tại

```powershell
curl https://mcp-l958.onrender.com/projects
```

✅ `[{"id":1,"name":"sample-python (sast-action demo)",...}]`

❌ `[]` → tạo lại:

```powershell
curl -X POST https://mcp-l958.onrender.com/projects `
  -H "Content-Type: application/json" `
  -d '{
    "name": "sample-python (sast-action demo)",
    "github_url": "https://github.com/cochecheee/sample-python"
  }'
```

## 4. GitHub API connection (mcp → GitHub)

```powershell
curl "https://mcp-l958.onrender.com/github/runs?limit=3"
```

✅ Array với 3 run gần nhất của sample-python (status, run_id, conclusion, ...)

❌ `401 Unauthorized` → `GITHUB_TOKEN` env sai/expired
❌ `404 Not Found` → `GITHUB_OWNER`/`GITHUB_REPO` env sai

## 5. CI sample-python chạy

Trigger:
```powershell
cd D:\School\DoAnTotNghiep\sample-python
git commit --allow-empty -m "ci: smoke verify"
git push origin main
```

Đợi 3-5 phút, vào https://github.com/cochecheee/sample-python/actions → run cuối cùng phải:
- ✅ status: `completed`
- ✅ conclusion: `success`
- ✅ workflow file: `.github/workflows/security.yml`

Click vào job → step `Notify chat-system dashboard` phải có log `accepted=true` hoặc HTTP 202.

## 6. Webhook đến mcp

```powershell
# Lấy run_id mới nhất
$run = curl -s "https://mcp-l958.onrender.com/github/runs?limit=1" | jq '.[0].id'

# Force reprocess
curl -X POST "https://mcp-l958.onrender.com/github/runs/$run/reprocess"
```

✅ `{"status":"accepted","run_id":...}` HTTP 202

Đợi 15-30 giây cho background task xử lý.

## 7. Finding ingested

```powershell
curl https://mcp-l958.onrender.com/stats/overview
```

✅ `{"total":N,"by_tool":{"semgrep":...,"trivy":...,"bandit":...,"safety":...},...}` với N > 0

```powershell
curl "https://mcp-l958.onrender.com/findings?category=sast&limit=5"
```

✅ Array 5 finding với schema:
```json
{
  "id": 1,
  "tool": "bandit",
  "severity": "MEDIUM",
  "rule_id": "B608",
  "file_path": "app.py",
  "line_number": 60,
  "title": "Possible SQL injection vector...",
  ...
}
```

## 8. Dashboard

```powershell
cd D:\School\DoAnTotNghiep\chat-system\dashboard
npm install     # lần đầu
npm run dev
```

Mở http://localhost:5173:
- ✅ Overview tab: KPI tổng số (`total > 0`)
- ✅ Vulnerabilities tab: list finding category=sast
- ✅ Click 1 finding → modal hiện AI fix (gọi Gemini lần đầu, cache lần sau)

## 9. AI fix end-to-end

```powershell
# Tìm 1 finding id
$id = curl -s "https://mcp-l958.onrender.com/findings?limit=1" | jq '.[0].id'

# Trigger analysis
curl -X POST "https://mcp-l958.onrender.com/findings/$id/analyze"
```

✅ `{"explanation_vi":"...","fix_diff":"...","cwe_refs":[...],"references":[...]}`

❌ `500 Internal Server Error` với log Gemini API error → check `GEMINI_API_KEY` env

## Troubleshoot quick map

| Symptom | Likely cause | Check |
|---|---|---|
| `curl /health` timeout | Cold start | Retry với `-m 60` |
| `Disallowed CORS origin` | `CORS_ORIGINS` thiếu | Render env var |
| Invalid workflow file | Permissions/secrets schema | [05-reusable-workflow.md](05-reusable-workflow.md) |
| 0 findings sau CI pass | Profile không match artifact | `mcp/config/profiles/github-actions-default.yml` |
| Bearer token mismatch | `CI_WEBHOOK_TOKEN` != `MCP_WEBHOOK_TOKEN` | Render env + GitHub secret |
| Gemini API 403 | Key expired/quota | Generate key mới ở Google AI Studio |

Chi tiết hơn ở [docs/troubleshooting.md](../troubleshooting.md).
