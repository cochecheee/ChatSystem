# ANALYSIS — Hiện trạng chat-system (2026-05-08)

> Phân tích sâu trước khi đề xuất tái triển khai. Mục tiêu: trả lời câu hỏi *"sản phẩm này thực sự đóng góp gì, có tái sử dụng được không?"*

---

## 1. Tóm tắt sản phẩm

**Bản chất**: Một dashboard + chat AI assistant gắn vào output của một CI/CD SAST pipeline. Không phải một SAST tool — nó là **lớp aggregation + AI explanation** đứng trên các tool có sẵn.

**Pipeline thực tế (theo `ALOUTE_Spring_Thymeleaf_RCE/.github/workflows/ci.yml`)**:

```
push → build → [semgrep, codeql, eslint, spotbugs, dep-check, trivy-fs] (parallel)
              → sonarqube (Gate 1: SARIF threshold + Gate 2: SonarCloud QG)
              → docker build + trivy image scan
              → notify.py POST /webhook/pipeline-complete to MCP_GATEWAY_URL
                                           ↓
                       MCP Gateway (FastAPI) — chat-system backend
                          ↓ poller pulls artifacts từ GitHub API
                          ↓ normalize SARIF/XML/JSON → Finding
                          ↓ enrich CWE/CVSS/OWASP
                          ↓ Gemini analysis (on-demand /explain)
                                           ↓
                       React Dashboard (Vulns / Pipelines / Chat / Reports)
```

**Đóng góp thực sự**:
1. **Aggregation** — gom 6 format SAST khác nhau về một schema thống nhất (`Finding`).
2. **AI explanation** — dịch finding kỹ thuật sang tiếng Việt + đề xuất `remediation_diff`.
3. **Human-in-the-loop audit** — RBAC (developer / security_lead / admin) + audit trail cho approve/revoke.
4. **ChatOps** — 7 slash command + natural-language → suggested command.

**Phần KHÔNG phải đóng góp** (chỉ là wrapper):
- SAST scanning — toàn bộ là tool có sẵn (Semgrep, CodeQL, ...).
- Quality Gate — đã có SonarCloud + script `gate1_sarif_check.py` riêng trong ALOUTE.
- Security gating — branch protection do GitHub Settings xử lý.

---

## 2. Đo đạc codebase

### Backend (`mcp/src`) — 2440 LOC

| File | LOC | Đánh giá |
|---|---|---|
| `services/normalizer.py` | 535 | Cần — đây là core value. Lenient SARIF parser handle 6 tool. |
| `api/artifacts.py` | 310 | Cần. Endpoints cho project/finding/github runs. |
| `services/command_service.py` | 224 | Cần. 7 ChatOps handlers. |
| `api/chat.py` | 213 | Cần. Chat + command endpoints. |
| `services/processor.py` | 186 | Cần. Orchestrator. **NHƯNG hardcode tên artifact (`_SECURITY_ARTIFACT_NAMES`) → blocker reuse.** |
| `services/github_client.py` | 174 | Cần. |
| `services/report_service.py` | 153 | Giữ. |
| `services/stats_service.py` | 153 | Giữ. |
| `services/enricher.py` | 143 | Giữ — CWE/OWASP enrichment. |
| `services/poller.py` | 98 | Giữ. |
| `services/config_service.py` | 77 | Đánh giá lại — overlap với `core/config.py`? |
| `core/auth.py + db.py + guardrails.py + config.py` | ~400 | Cần. |
| `api/analysis.py + stats.py + config.py` | ~163 | Giữ. |
| `services/llm/*` | ~? | Cần — Gemini wrapper + structured schema. |

**Verdict backend**: Tinh gọn rồi. Vấn đề lớn nhất là **single-repo assumption** (`settings.GITHUB_OWNER/REPO` là singleton trong `core/config.py`) và **artifact name hardcode**.

### Frontend (`dashboard/src/pages`) — 5494 LOC

| Page | LOC | Real / Mock | Verdict |
|---|---|---|---|
| `Vulns.tsx` | 786 | **Real** | Giữ — page giá trị nhất. |
| `Pipelines.tsx` | 702 | **Real** | Giữ. |
| `Settings.tsx` | 455 | Real | Giữ — config repo. |
| `Overview.tsx` | 367 | **Real** | Giữ. |
| `Chat.tsx` | 380 | **Real** | Giữ — core feature. |
| `Reports.tsx` | 238 | Real | Giữ. |
| `Dast.tsx` | **930** | **MOCK** | **Cắt** — không có DAST backend, chỉ là demo cho hội đồng. |
| `Secrets.tsx` | **469** | **MOCK** | **Cắt** — TruffleHog/Gitleaks không có integration. |
| `Sca.tsx` | **417** | **MOCK** | **Cắt** — đã có Dependency-Check trong Vulns rồi, page này trùng. |
| `PRBot.tsx` | **386** | **MOCK** | **Cắt** — mâu thuẫn với *human-in-the-loop* (không auto-PR). |
| `Governance.tsx` | **305** | **MOCK** | **Cắt** — chỉ là decoration. |
| `Repos.tsx` | **59** | **MOCK** | **Cắt** (hoặc gộp vào Settings). |

**Mock pages tổng**: **2566 LOC = 47% of all page code is theatre.** Sentinel design là tốt nhưng nửa giao diện là show-bài.

---

## 3. Đánh giá tính hữu ích

### Có thực sự ích lợi không?

**CÓ — với điều kiện phải có CI/CD SAST chạy sẵn.** Cụ thể:

| Use case | Có ích không? | Lý do |
|---|---|---|
| Team Java/Spring có CI/CD | ✅ Cao | Aggregate 6 tool + AI fix gợi ý — tiết kiệm thời gian triage. |
| Team chỉ chạy SAST local | ❌ | Tool cần GitHub Actions artifacts → không local-friendly. |
| Solo developer | ⚠️ Thấp | Setup overhead (Gemini key, GitHub token, FastAPI server, dashboard) > value. |
| Compliance team cần audit trail | ✅ Cao | RBAC + justification ≥ 20 ký tự là điểm sáng. |
| Replace SonarCloud | ❌ | Không thay thế được Quality Gate; là layer bổ sung. |

### Phần nào thực sự độc đáo?

1. **Vietnamese AI remediation** với `remediation_diff` Unified Diff → rất specific cho bối cảnh dev VN, đây là điểm khác biệt với Snyk/Sonar.
2. **ChatOps trong dashboard** thay vì Slack/Teams — giảm context-switch, demo tốt cho đồ án.
3. **Lenient SARIF parser** — chấp nhận biến thể thực tế, isolate per-file errors. Codebase open-source ít tool xử lý SARIF kiểu này tốt.

### Phần nào trùng / yếu?

1. **Reports HTML** — SonarCloud đã có, không nổi bật.
2. **Pipelines page** — overlap với GitHub Actions UI native.
3. **Mock pages (DAST/SCA/Secrets/PRBot/Governance/Repos)** — lừa gạt scope; reviewer kỹ tính sẽ trừ điểm.
4. **Free-form chat → suggest command** — wrapper mỏng quanh Gemini. Có giá trị thuyết trình nhưng kỹ thuật đơn giản.

---

## 4. Đánh giá tính tái sử dụng

### Câu hỏi: "Project khác có dùng được không?"

Hiện tại **KHÔNG**, vì 4 lý do:

1. **Single-repo assumption** — `core/config.py` set `GITHUB_OWNER` + `GITHUB_REPO` từ `.env`, một instance chỉ phục vụ 1 repo.
2. **Hardcoded artifact names** — `processor.py:21-33` whitelist tên artifact phải là `semgrep-report`, `codeql-report`, ... Project nào không đặt đúng tên là bị bỏ qua.
3. **Hardcoded workflow contract** — backend giả định CI sẽ POST `/webhook/pipeline-complete` với `run-metadata.json` payload cụ thể. Đây là contract ngầm, không có schema doc.
4. **Setup nặng** — Gemini API key + GitHub PAT + Python venv + Node + ngrok (theo `run.txt`) — không có ai muốn "thử".

### Khi tái cấu trúc, mức nỗ lực để 1 project mới onboard?

| Phương án | Onboard effort | Maintenance | Phù hợp đồ án? |
|---|---|---|---|
| **A. Docker Compose template** (per-project self-host) | 30 phút (clone + .env + paste workflow YAML) | Mỗi team tự lo | ✅ Khả thi 1 tuần |
| **B. GitHub Action `cochecheee/sast-action@v1` + central dashboard** | 5 phút (add 1 step vào workflow) | Tao maintain Action | ⚠️ Tham vọng, khó nhưng impressive |
| **C. SaaS multi-tenant** | < 5 phút | Tao maintain server | ❌ Quá to cho 1 tuần |

**Khuyến nghị**: chi tiết trong `REUSABILITY.md`.

---

## 5. Risk & Hidden Cost

- **Gemini API quota** — dashboard prod dùng phải lo cost. Đồ án OK với free tier.
- **GitHub PAT scope** — `repo + workflow` là quyền lớn; team không thoải mái cấp cho instance bên ngoài.
- **SQLite single-file** — không scale, fine cho per-project self-host.
- **Webhook public URL** — cần ngrok / reverse proxy → barrier cho non-technical team.
- **Sentinel design đẹp nhưng phức tạp** — 5494 LOC pages là dấu hiệu UI overengineered cho 1 đồ án.

---

## 6. Kết luận

| Câu hỏi | Đáp án |
|---|---|
| Có hữu ích không? | **Có**, cho team có CI/CD sẵn. Specific cho dev VN. |
| Có thừa thãi gì không? | **47% UI code là mock**. Một số service overlap (`config_service` vs `core/config`). |
| Có đóng gói tái sử dụng được không? | **Hiện tại không**, cần refactor 3 điểm: multi-project, artifact contract, packaging. |
| Đáng tái triển khai không? | **Đáng** — phần backend (normalizer + AI + audit) đủ giá trị, đóng gói lại sẽ ra product thật. |

→ Xem `REDUNDANCY.md` (cắt gì), `REUSABILITY.md` (đóng gói thế nào), `PLAN-1WEEK.md` (lịch ngày).
