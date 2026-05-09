# Slide Outline — Đồ án tốt nghiệp Defense

> Skeleton 12-15 slide cho buổi bảo vệ đồ án (~20 phút). Mỗi slide có 1 message duy nhất + speaker note. Tay slide đẹp dùng PowerPoint/Canva sau, đây là khung nội dung.

---

## Slide 1 — Title

```
ĐỒ ÁN TỐT NGHIỆP

Hệ thống Tích hợp Bảo mật vào CI/CD Pipeline
với hỗ trợ AI cho Quy trình Khắc phục

Sinh viên:    Lê Bá Tiến Thành
GVHD:         <tên GVHD>
Ngày bảo vệ:  2026-05-XX
```

**Note**: 30 giây giới thiệu tên + tên đồ án. Không đọc bullet.

---

## Slide 2 — Vấn đề (Problem)

**Headline**: *Phát hiện lỗ hổng càng muộn càng đắt.*

3 bullet:
- SAST tools rời rạc — Semgrep / CodeQL / SpotBugs / Trivy / Dep-Check, mỗi tool 1 format khác nhau, dev khó triage.
- AI suggestion thị trường (Snyk, GitHub Copilot Security) tiếng Anh, hard-to-actionable cho team Việt.
- Compliance: thiếu audit trail "ai approve, lúc nào, lý do gì".

**Note**: Nhấn "shift left" — mọi giây sớm hơn = chi phí ít hơn. Đặt nền problem cho slide 3.

---

## Slide 3 — Mục tiêu (Goals)

| Mục tiêu | Đo bằng |
|---|---|
| 1 dashboard duy nhất cho 6 SAST tool | Aggregate normalize SARIF/XML/JSON → schema thống nhất |
| AI gợi ý fix bằng tiếng Việt + Unified Diff | `/explain`, `/fix` ChatOps |
| Audit trail đầy đủ | RBAC 3 roles + justification ≥ 20 ký tự |
| Đóng gói reusable | Docker image + composite Action + per-project integration endpoint |

**Note**: Đây là contract — slide 8 sẽ chứng minh đã đạt.

---

## Slide 4 — Kiến trúc tổng quan (Architecture)

```
GitHub Actions CI                MCP Gateway                Web Dashboard
─────────────────                ───────────                ─────────────
[Semgrep | CodeQL | ...]    →    Poller / Webhook    →    Overview / Pipelines
                                    ↓                         Vulnerabilities
                                Normalizer (lenient SARIF)    Dependencies
                                    ↓                         Chat (7 commands)
                                Enricher (CWE/CVSS/OWASP)     Reports
                                    ↓
                                Guardrails (PII + Injection)
                                    ↓
                                Gemini (Vietnamese, Diff)
```

**Note**: 1 phút walk-through. Highlight 2 boundary check (auth webhook, guardrails AI).

---

## Slide 5 — Tech Stack

| Layer | Choice | Lý do |
|---|---|---|
| Backend | FastAPI + SQLAlchemy async + aiosqlite | Async-native, 200+ pytest pass nhanh, demo-friendly |
| Frontend | React 19 + Vite 8 + TypeScript | HMR + Sentinel design system custom |
| AI | Google Gemini structured output | Vietnamese support, JSON mode chính xác |
| Auth | JWT + RBAC (developer / security_lead / admin) | Standard enterprise pattern |
| Packaging | Docker multi-stage + nginx proxy | Same-origin, plug-and-play |

**Note**: Tránh "tech stack porn" dài dòng. 30 giây.

---

## Slide 6 — Demo flow (live)

(Chuyển sang dashboard, theo `docs/demo-script.md` 8 phần ~10 phút)

1. Overview → "đã có data thật từ ALOUTE"
2. Chat `/scan` → trigger CI live
3. Pipelines → run-detail board
4. Vulnerabilities → Ask AI → diff
5. Chat `/approve` → audit trail
6. Dependencies → group + recommend
7. Free-form chat → suggested command
8. `/report` → HTML download

**Note**: Đây là 50% giá trị buổi bảo vệ. Đừng nói lý thuyết, click + show.

---

## Slide 7 — Đo đạc (Metrics)

| Metric | Số |
|---|---|
| Tools tích hợp | 6 (Semgrep, CodeQL, SpotBugs, ESLint, Trivy, Dep-Check) |
| Backend tests | 200/200 pytest pass |
| Guardrails coverage | 24 cases (scrubbing + injection) |
| Frontend pages | 7 real, 0 mock (cắt 47% UI code so với baseline) |
| Bundle size | 305 KB JS / 86 KB gzip |
| Docker image size | mcp ~180 MB, dashboard ~45 MB |
| Demo target | [cochecheee/SAST_CICD](https://github.com/cochecheee/SAST_CICD) |

**Note**: Số "47% cắt UI mock" là điểm sáng tự critique — show nỗ lực không show fluff.

---

## Slide 8 — Tính tái sử dụng (Reusability)

3 mức onboard cho project mới:

| Mức | Cách | Effort |
|---|---|---|
| **A. Self-host** | `docker pull` + `.env` + paste 1 step CI | 30 phút |
| **B. Composite Action** | `uses: cochecheee/chat-system@v0.1.0` 1 dòng | 5 phút |
| **C. Per-project integration endpoint** | UI hiển thị copy-paste snippet + secret names | < 5 phút |

**Note**: Slide critical cho hội đồng hỏi "thực sự reusable hay không?". Show `GET /projects/{id}/integration` live nếu kịp thời.

---

## Slide 9 — Giới hạn (Limitations) — *honest*

3 bullet:
- Single-tenant runtime ở v0.1.0 — multi-project là scaffolding (DB/repo ready), runtime sang v0.2.
- DAST chưa tích hợp thật — note trong roadmap (OWASP ZAP).
- Plain-text credentials (mã hoá Fernet sang v0.2).

**Note**: Hội đồng RẤT thích thí sinh tự critique. Đừng giấu.

---

## Slide 10 — Roadmap V2

- Multi-tenant runtime flip-on (loop projects ở poller).
- DAST adapter (OWASP ZAP).
- GitLab + Bitbucket adapters dùng cùng webhook contract.
- Encrypted credential store.
- Per-project AI prompt overrides (bilingual EN/VI).

**Note**: 30 giây. Show "đồ án không kết thúc ở đây".

---

## Slide 11 — Q&A (placeholder)

**Câu hỏi dự đoán + trả lời chuẩn bị sẵn**:

1. *"Sao không dùng SonarQube luôn?"* → SonarQube mạnh nhưng UI rộng, AI không có tiếng Việt, không có ChatOps. chat-system là layer phía trên SonarQube, không thay thế (workflow ALOUTE vẫn có Gate 2 SonarCloud).

2. *"AI hallucinate sai diff thì sao?"* → Audit trail bắt buộc human approve. AI chỉ recommend, không auto-PR. `/approve` cần justification ≥ 20 chars.

3. *"Số 8000 CVE Trivy có bug không?"* → Real data từ container scan OS layer. UI group lại theo dependency + filter ≥ high default → còn ~50 actionable.

4. *"Reusability thế nào nếu CI khác (GitLab, Jenkins)?"* → Webhook contract chuẩn — GitLab/Jenkins POST cùng JSON shape. Adapter Java/Node trong roadmap V2.

5. *"Bảo mật API key plain-text?"* → Đã thừa nhận trong slide 9. v0.2 dùng Fernet symmetric encryption với `SECRET_KEY`.

6. *"Test coverage bao nhiêu phần trăm code?"* → 200 backend cases, focus integration test. Không đo % coverage vì pytest-cov không enforce trong CI hiện tại — tradeoff mục tiêu thesis.

---

## Slide 12 — Closing

```
Cảm ơn hội đồng đã lắng nghe.

Repository:  github.com/cochecheee/chat-system
Demo target: github.com/cochecheee/SAST_CICD
Docker Hub:  cochecheee/sast-chat-{mcp,dashboard}
```

**Note**: Pause 5 giây cuối, đợi câu hỏi.

---

## Cheat-sheet thời gian

```
Slide 1-2 (intro)         ~ 1' 30"
Slide 3-5 (goals/arch)    ~ 2' 30"
Slide 6 (live demo)       ~ 10'
Slide 7-10 (metrics/etc)  ~ 4'
Slide 11-12 (Q&A/close)   ~ 2'
─────────────────────────────────
Total                       ~ 20'
```

Demo ăn nhiều thời gian nhất — mọi slide còn lại pace được.

---

## Visual asset checklist (làm sau outline)

- [ ] Architecture diagram (slide 4) — Mermaid hoặc Excalidraw
- [ ] Screenshots demo (slide 7) — 4 ảnh: Overview, Vulns + AI, Pipelines run-detail, Dependencies grouped
- [ ] Logo / theme tokens consistent với Sentinel design (cam #ED7D31, off-white)
- [ ] Font slide khớp dashboard (Inter Tight)
