# Demo Script — chat-system end-to-end

> Bài demo 12-15 phút cho hội đồng đồ án. Mục tiêu: chứng minh hệ thống thực sự hoạt động trên ALOUTE_Spring_Thymeleaf_RCE từ push code → SAST → AI fix → audit trail.

---

## Setup trước demo (làm trước 10 phút)

Theo thứ tự — xem `docs/preflight-checklist.md` chi tiết.

```powershell
# Terminal 1 — backend
cd D:\School\DoAnTotNghiep\chat-system\mcp
.venv\Scripts\activate
uvicorn src.main:app --reload --port 8000

# Terminal 2 — frontend
cd D:\School\DoAnTotNghiep\chat-system\dashboard
npm run dev

# Terminal 3 — public tunnel (để CI ALOUTE webhook về được)
D:/School/DoAnTotNghiep/ngrok-v3-stable-windows-amd64/ngrok.exe http 8000

# Browser tabs đã mở sẵn:
#   1. http://localhost:5173            (dashboard)
#   2. https://github.com/cochecheee/SAST_CICD/actions   (CI runs)
#   3. https://github.com/cochecheee/SAST_CICD          (repo)
```

---

## Phần 1 — Tổng quan hệ thống (2 phút)

**Slide / browser**: tab Overview của dashboard.

**Nói**:
> "Đây là chat-system, layer aggregation + AI giữa CI/CD SAST tools và developer. Khi developer push code, GitHub Actions chạy 6 SAST tool song song — Semgrep, CodeQL, SpotBugs, ESLint, Trivy, OWASP Dep-Check. Kết quả được normalize về 1 schema, enrich CWE/CVSS/OWASP, và đề xuất fix bằng AI tiếng Việt. Toàn bộ trong dashboard không cần Slack/Teams."

**Show**:
- 3 KPI cards: Open findings, Critical+High, AI analyzed
- Severity distribution chart
- Pipeline heatmap (nếu có)

---

## Phần 2 — Trigger CI từ chat (2 phút)

**Tab**: Chat.

**Action**: Login với role `security_lead` → gõ:
```
/scan
```

**Expected**:
- Chat trả: "Đã kích hoạt Security Scan mới trên nhánh main."
- Toast notification xuất hiện
- Mở tab GitHub Actions → run mới đang queued

**Nói**:
> "ChatOps thay vì click GitHub UI. Backend dùng GitHub API `dispatch_workflow` — same flow như security team thật sẽ dùng."

---

## Phần 3 — Chờ CI + xem Pipelines tab (2 phút)

**Tab**: Pipelines.

**Action**: Click vào run mới nhất (đang in_progress).

**Show**:
- Severity summary cho run đó
- Artifact list (semgrep-report, codeql-report, ...)
- Tool breakdown bar chart

**Nói**:
> "Mỗi run là 1 board riêng — không lẫn finding của run cũ. Khi CI xong, poller chat-system tự pull artifact mỗi 5 phút, hoặc CI POST webhook trả về luôn cho fast-path. Nút Reprocess chạy lại 1 run nếu pipeline đã complete nhưng processor lỗi giữa chừng."

> "Hôm nay tao đã trigger CI trước demo nên đã có data sẵn ở run #109."

(Nếu vẫn đang chạy CI, chuyển sang Phần 4 và quay lại sau.)

---

## Phần 4 — Vulnerabilities tab (3 phút)

**Tab**: Vulnerabilities.

**Show**:
- Filter severity → click "Critical" → còn 5-10 row
- Click 1 finding RCE/SSRF của ALOUTE (có thật trong repo)
- Detail pane hiện: severity, tool, file path, OWASP category

**Action**: Click "Ask AI".

**Expected**: AI panel mở, hiện loading 2-3s rồi:
- Explanation tiếng Việt
- Impact tiếng Việt
- Remediation diff (Unified Diff)
- CWE reference + Confidence

**Nói**:
> "Trước khi gọi Gemini, content qua 2 layer guardrails: scrub PII/secret + chặn prompt injection (`docs/guardrails.md`). 24 test cases."

> "Output structured JSON 7 fields, prompt template trong `mcp/src/services/llm/prompts.py`."

---

## Phần 5 — Approve flow (2 phút)

**Tab**: Chat (giữ Vulns tab note finding ID, ví dụ #5).

**Action**:
```
/approve 5
```

**Expected**: Dialog mở, yêu cầu justification ≥ 20 ký tự.

**Type**:
```
Đã review code — finding này thuộc dead code path không reach từ user input
```

**Click Confirm**.

**Expected**:
- "Finding #5 đã được phê duyệt bởi MinhTran."
- Toast "approved"
- Mở Vulns tab → finding #5 có badge "Approved" + audit trail (who/when/why)

**Nói**:
> "Audit trail đầy đủ — yêu cầu cho compliance. Min 20 ký tự để chống ai duyệt vô tội vạ. Role-based: developer không approve được."

---

## Phần 6 — SCA / Dependencies (2 phút)

**Tab**: Dependencies.

**Show**:
- Severity filter mặc định "≥ High" — cắt noise OS-CVE
- Mỗi row là 1 dependency (group theo package + version)
- Click 1 row → detail pane:
  - Recommended version (max FixedVersion across CVE)
  - Upgrade command (`# Update <pkg> to <ver> in your build file`)
  - List CVE trong dep, sort theo severity, có CVSS score

**Nói**:
> "Trivy container scan tạo ra hàng ngàn CVE OS-level — UI group lại theo `(package, version)` để actionable. Recommend dùng max fix version. Click có thể copy upgrade command thẳng vào terminal."

---

## Phần 7 — Free-form chat (1 phút)

**Tab**: Chat.

**Type**:
```
phân tích giúp tao finding số 7
```

**Expected**:
- AI trả lời bằng tiếng Việt
- Chip "Run /explain 7" hiện ra
- Click chip → tự động gọi `/explain 7`

**Nói**:
> "Natural language → suggested command. Backend gọi Gemini với context các finding gần đây. UX tốt hơn slash command thuần."

---

## Phần 8 — Reports + closing (1 phút)

**Tab**: Reports.

**Action**:
```
/report
```

**Expected**: HTML report download, mở browser tab mới với layout sẵn — total findings, by severity, top affected files.

**Closing nói**:
> "Tổng kết: hệ thống đã chứng minh shift-left security workflow đầy đủ trên repo Java Spring thật. Tất cả components tested (200 backend tests + Playwright E2E), đóng gói Docker (`docker compose up`), tài liệu integration cho repo khác trong `docs/`. Roadmap tiếp theo: multi-tenant runtime + DAST integration."

---

## Demo flow tóm tắt (cheatsheet)

```
1. Overview tab           → "Đây là chat-system, ..."   2'
2. Chat /scan             → Trigger CI                  2'
3. Pipelines run detail   → "Per-run board"             2'
4. Vulns + Ask AI         → "Guardrails + Gemini"       3'
5. Chat /approve <id>     → "Audit trail"               2'
6. Dependencies tab       → "Group + recommend"         2'
7. Free-form chat         → "Suggested command"         1'
8. Chat /report           → "HTML export"               1'

Total ~ 15'.
```

## Backup plan

Nếu live demo fail (ngrok rớt, CI pending quá lâu, AI rate-limit):

1. **Fallback screencast**: `docs/demo-recording.mp4` (mày record trước Day 7)
2. **DB snapshot**: `mcp/mcp.db.demo-backup` — nếu DB sạch sau reset, copy từ backup
3. **Pre-cached AI analysis**: 5-10 finding đã được /explain trước, không cần gọi Gemini live

Xem `docs/troubleshooting.md` cho từng failure mode.
