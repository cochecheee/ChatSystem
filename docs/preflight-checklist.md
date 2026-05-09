# Preflight Checklist — Trước khi demo

> Chạy hết checklist này trước demo 30 phút. Dùng kèm `docs/demo-script.md`.

---

## 1. Environment

- [ ] Python 3.13 venv ở `mcp/.venv` đã activate
- [ ] Node 20+ (`node --version`)
- [ ] `mcp/.env` đầy đủ:
  - [ ] `GITHUB_TOKEN` (scope: repo + workflow)
  - [ ] `GITHUB_OWNER=cochecheee`, `GITHUB_REPO=SAST_CICD`
  - [ ] `GEMINI_API_KEY`
  - [ ] `SECRET_KEY` (32+ chars)
  - [ ] `CI_WEBHOOK_TOKEN`
- [ ] `dashboard/node_modules` đã install (`npm install`)

## 2. Database

- [ ] DB schema mới — chạy migrate nếu cần:
  ```powershell
  cd mcp
  .venv\Scripts\python -m scripts.migrate_v2
  ```
  Mong đợi: "All columns already present" (idempotent) hoặc "Added columns: …" (lần đầu).

- [ ] Có Project row đã backfill:
  ```powershell
  curl http://localhost:8000/projects | python -m json.tool
  ```
  Mong đợi: `has_github_token: true`, `has_gemini_api_key: true`.

- [ ] Có data fresh từ CI mới (không phải Trivy 8280 cũ):
  ```powershell
  curl http://localhost:8000/stats/overview | python -m json.tool
  ```
  Kiểm `by_tool` có đủ semgrep/codeql/spotbugs/eslint (không chỉ Trivy).

  Nếu DB còn dirty → reset:
  ```powershell
  .venv\Scripts\python -m scripts.reset_db --apply
  ```
  Sau đó chạy `/github/runs/{latest}/reprocess` từ Swagger UI để pull lại artifact mới.

## 3. CI ALOUTE

- [ ] Last run đã `success`: https://github.com/cochecheee/SAST_CICD/actions
- [ ] Run mới nhất có artifacts (semgrep-report, codeql-report, ...) — chưa expire (retention 30 ngày)
- [ ] Webhook secrets đã set ở repo target:
  - `MCP_GATEWAY_URL` — đặt = ngrok URL bên dưới
  - `MCP_WEBHOOK_TOKEN` — match với `CI_WEBHOOK_TOKEN` trong `.env`

## 4. Public tunnel

```powershell
D:/School/DoAnTotNghiep/ngrok-v3-stable-windows-amd64/ngrok.exe http 8000
```

- [ ] URL ngrok hiện ở terminal (HTTPS forwarding)
- [ ] Update `MCP_GATEWAY_URL` ở GitHub Secrets nếu URL đổi:
  ```powershell
  gh secret set MCP_GATEWAY_URL -R cochecheee/SAST_CICD -b "https://abc-123.ngrok-free.app"
  ```
- [ ] Test webhook:
  ```powershell
  curl -X POST "https://abc-123.ngrok-free.app/webhook/pipeline-complete" `
    -H "Content-Type: application/json" `
    -H "Authorization: Bearer $env:CI_WEBHOOK_TOKEN" `
    -d '{"run_id": 999, "pipeline_status": "test"}'
  ```
  Mong đợi: `202 Accepted`.

## 5. Backend + Frontend

- [ ] Backend chạy: `uvicorn src.main:app --reload --port 8000`
  - [ ] http://localhost:8000/health → `{"status":"ok"}` (hoặc tương đương)
  - [ ] http://localhost:8000/docs → Swagger UI hiển thị

- [ ] Frontend chạy: `npm run dev`
  - [ ] http://localhost:5173 — dashboard load không error
  - [ ] DevTools Console không có error đỏ
  - [ ] Sidebar 7 page hiện đầy đủ (Overview/Pipelines/Vulnerabilities/Dependencies/Chat/Reports/Settings)

## 6. Auth

- [ ] Click Chat tab → dialog login → chọn role `security_lead` → token được set
- [ ] Verify token:
  ```powershell
  curl http://localhost:8000/api/chat/auth/me -H "Authorization: Bearer <copied token>"
  ```

## 7. Pre-cached AI analysis (optional safety net)

Để demo không phụ thuộc Gemini quota, run trước 5-10 finding:

```powershell
# Get top 5 critical/high findings
curl "http://localhost:8000/findings?severity=critical&limit=5" | python -m json.tool > preselected.json

# Trigger /explain cho từng cái
$ids = (5, 7, 12, 15, 20)
foreach ($id in $ids) {
    Invoke-RestMethod -Uri "http://localhost:8000/findings/$id/explain" -Method POST
    Write-Host "Cached finding $id"
}
```

Demo gọi `/explain` lần sau sẽ trả từ DB ngay (`status=ai_analyzed`), không gọi Gemini.

## 8. Chuẩn bị slide / browser

- [ ] Browser fullscreen
- [ ] Zoom 110-125% (cho phòng lớn)
- [ ] Tabs đã pre-open theo `demo-script.md`
- [ ] Theme dashboard: Light (rõ hơn projector tối)
- [ ] DevTools đóng (tránh lộ error log)

## 9. Backup

- [ ] Screencast `docs/demo-recording.mp4` (record trước Day 7)
- [ ] DB snapshot: `cp mcp/mcp.db mcp/mcp.db.demo-backup`
- [ ] Slide PDF backup mở trong tab khác

---

## Checklist tóm tắt — In ra giấy

```
□ .env đầy đủ
□ Backend running on :8000, /health OK
□ Frontend running on :5173, no console errors
□ ngrok URL set ở GitHub Secrets
□ Webhook test 202
□ DB có findings từ CI mới (không 8280 Trivy cũ)
□ 5 findings đã pre-cached AI analysis
□ Login Chat tab thành công, role=security_lead
□ Browser tabs pre-opened
□ Screencast backup ready
```
