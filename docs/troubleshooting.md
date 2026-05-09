# Troubleshooting — Demo failures

> Bug có thể xảy ra trong demo + fix nhanh trong 1-2 phút. Đọc trước Day 5.

---

## 1. Dashboard không load / blank

**Symptom**: http://localhost:5173 → page trắng.

**Check**:
1. Backend có chạy? `curl http://localhost:8000/health`
2. DevTools Console → CORS error?
3. DevTools Network → `/stats/overview` status?

**Fix**:
- Backend down → restart `uvicorn`
- CORS error (nếu deploy qua tunnel) → check `mcp/src/main.py` allow origins, hoặc dùng nginx proxy (Day 4)
- 500 server error → xem backend log → thường là DB chưa migrate (`migrate_v2.py`)

---

## 2. Chat tab — không gọi được API

**Symptom**: Gõ `/scan` → "Network error" / "401 Unauthorized".

**Check**:
1. Đã login chưa? (nút Login góc phải Chat header)
2. Token có ở localStorage? DevTools → Application → Local Storage → `chat_token`
3. Backend log thấy gì khi click?

**Fix**:
- Chưa login → click Login → chọn role
- Token hết hạn (480 phút) → logout + login lại
- Backend không nhận token → check `SECRET_KEY` trong `.env` không đổi giữa restart

---

## 3. `/explain` ra lỗi 500

**Symptom**: AI panel "Lỗi phân tích" / Gemini timeout.

**Check**: backend log có `429` (rate limit) hoặc `503` (Gemini overload)?

**Fix nhanh**:
- Dùng pre-cached finding ID (đã `/explain` trước demo)
- Hoặc retry — code đã có exponential backoff 3 lần
- Hoặc đổi sang `GEMINI_MODEL=gemini-2.5-flash-lite` (cheaper) trong `.env` + restart

**Demo workaround**: nói "Gemini đang rate-limit, chuyển sang finding khác đã cache" — pivot sang finding pre-cached.

---

## 4. `/scan` — "GitHub dispatch failed"

**Symptom**: Chat trả 502.

**Check**:
1. `GITHUB_TOKEN` còn valid? (PAT có thể đã expire)
2. PAT có scope `workflow`?
3. `cochecheee/SAST_CICD` đang busy với run khác?

**Fix**:
- Token expire → tạo PAT mới ở https://github.com/settings/tokens, paste vào `.env`, restart
- Scope thiếu → tạo PAT mới với `repo + workflow` checkbox
- Đang busy → demo skip `/scan`, nói "đã trigger CI từ trước, click sang Pipelines tab xem"

---

## 5. CI ALOUTE chạy nhưng dashboard không có data

**Symptom**: GitHub Actions run xanh nhưng dashboard tab Pipelines vẫn cũ.

**Check** theo thứ tự:

```powershell
# 1. Poller có chạy không?
curl http://localhost:8000/health

# 2. Có project row?
curl http://localhost:8000/projects | python -m json.tool

# 3. Run mới có trong list?
curl http://localhost:8000/github/runs | python -m json.tool

# 4. Force reprocess
curl -X POST http://localhost:8000/github/runs/<RUN_ID>/reprocess
```

**Fix**:
- Poller stuck → restart backend (uvicorn reload)
- Webhook miss + poll interval 5 phút → đợi hoặc trigger reprocess thủ công
- Artifact 410 Gone → run quá cũ, retention expired (30 ngày) — trigger CI mới

---

## 6. Vulnerabilities tab rỗng dù DB có data

**Symptom**: API `/stats/overview` cho thấy 100+ findings nhưng tab trắng.

**Lý do**: Vulns hardcode `category=sast` → loại Trivy/Dep-Check (DEPS_TOOLS). Nếu chỉ có Trivy data → tab rỗng là đúng.

**Fix**: Click sang tab "Dependencies" (SCA) — sẽ thấy data.

Hoặc: trigger CI mới để có Semgrep/CodeQL/SpotBugs/ESLint findings.

---

## 7. ngrok URL đổi sau khi restart

**Symptom**: Webhook POST từ CI fail vì URL cũ không còn.

**Fix tức thì**:
```powershell
# Lấy URL ngrok mới
$NEW_URL = (Invoke-RestMethod http://localhost:4040/api/tunnels).tunnels[0].public_url
# Update GitHub Secret
gh secret set MCP_GATEWAY_URL -R cochecheee/SAST_CICD -b $NEW_URL
```

**Phòng ngừa**: dùng ngrok paid với reserved domain (URL cố định).

---

## 8. `/approve` ra 422 "Justification phải có ít nhất 20 ký tự"

**Symptom**: Dialog gõ ngắn → reject.

**Đây không phải bug** — đó là validation cố ý. Gõ tối thiểu 20 ký tự (đếm cả space). Demo dùng câu mẫu sẵn ở `demo-script.md` Phần 5.

---

## 9. SCA tab "loading…" không dừng

**Symptom**: spinner mãi.

**Check**: DevTools Network → `/findings?category=deps&limit=500` status?

**Fix**:
- 500 server → backend log
- Timeout (DB query chậm với 8000+ row) → reset DB hoặc giảm `limit` trong Sca.tsx (đang 500)
- Nếu DB rỗng → đúng, tab sẽ hiện "No dependency vulnerabilities"

---

## 10. Báo cáo IEEE / slide cần cập nhật cuối phút

Demo xong nếu phát hiện stat sai (ví dụ "200 tests" → giờ là 201) → KHÔNG sửa slide live. Nói:
> "Số tests đã tăng từ 162 baseline lên 200+ trong quá trình refactor — chính xác hôm demo là <X>."

Hội đồng quan tâm hệ thống chạy được, không phải con số chính xác đến đơn vị.

---

## 11. Trục trặc network trong phòng demo

**Plan B**: dùng screencast `docs/demo-recording.mp4` thay live demo. Pause + nói chú thích.

**Plan C**: hoàn toàn offline screenshots ở slide.

---

## Quick reset tất cả (10 giây)

```powershell
cd D:\School\DoAnTotNghiep\chat-system\mcp
.venv\Scripts\python -m scripts.reset_db --apply

# Stop everything
Get-Process | Where-Object {$_.ProcessName -in 'uvicorn','node','ngrok'} | Stop-Process -Force

# Restart fresh
.venv\Scripts\activate
uvicorn src.main:app --reload --port 8000   # T1
cd ../dashboard; npm run dev                  # T2
ngrok http 8000                               # T3
```

Restore DB từ snapshot:
```powershell
Copy-Item mcp\mcp.db.demo-backup mcp\mcp.db -Force
```
