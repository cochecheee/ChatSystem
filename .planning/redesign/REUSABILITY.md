# REUSABILITY — Đóng gói thế nào để dự án khác dùng được

> Trả lời câu hỏi mày đặt ra: *"vấn đề là nó lấy kết quả SAST từ CI/CD nên các dự án khác khó dùng"*. Đây là phân tích sâu trước khi chốt option.

---

## 1. Vì sao reuse khó?

Mọi tool dạng "post-CI dashboard" đều có 2 contract phải fix:

1. **Input contract** — tool produce SAST artifact format gì, đặt tên gì, ở đâu (GitHub artifact / S3 / webhook payload).
2. **Output contract** — finding schema sau normalize, AI prompt template, audit policy.

Hiện tại chat-system **fix cứng cả 2**:
- Input: phải là 6 artifact tên cố định, từ GitHub Actions, theo workflow của ALOUTE.
- Output: schema OK nhưng không expose ngoài (no SDK).

→ Project khác có CI/CD khác (GitLab, Jenkins, Bitbucket; Maven thay vì Gradle; Trivy đặt tên artifact khác) → không tương thích.

---

## 2. Pattern industry chuẩn

Nghiên cứu cách Snyk / DefectDojo / GitHub Advanced Security làm:

| Tool | Cách reuse |
|---|---|
| **GitHub Advanced Security** | SARIF upload API — chuẩn hóa input format, không quan tâm tool gì sinh |
| **DefectDojo** | API REST `/import-scan` — accept SARIF/CSV/JSON tool-specific, có 100+ parser |
| **Snyk** | CLI `snyk monitor` — push từ bất kỳ CI nào, central dashboard |
| **SonarCloud** | `sonar-scanner` CLI — agnostic CI |

**Bài học**: thành công nằm ở **input chuẩn hóa qua một CLI hoặc HTTP endpoint duy nhất**, không phải scrape GitHub artifacts.

---

## 3. So sánh 2 option mày cho

### Option A — Docker Compose Template (per-project self-host)

**Cách dùng**:
```bash
# Repo của team X (ví dụ ALOUTE)
git submodule add https://github.com/cochecheee/sast-chat sast-chat
cp sast-chat/docker-compose.example.yml docker-compose.sast.yml
cp sast-chat/.env.example .env.sast
# edit .env.sast: GITHUB_TOKEN, GEMINI_API_KEY, OWNER, REPO, ARTIFACT_PATTERNS
docker compose -f docker-compose.sast.yml up -d
# dashboard ở http://localhost:8000
```

CI chỉ cần thêm 1 step:
```yaml
- name: Notify SAST Chat
  run: |
    curl -X POST "$SAST_CHAT_URL/webhook/pipeline-complete" \
      -H "Authorization: Bearer $SAST_CHAT_TOKEN" \
      -d @run-metadata.json
```

**Effort 1 tuần**: ✅ rất khả thi.

**Pros**:
- Đơn giản nhất, demo được trên ALOUTE end-to-end.
- Mỗi team kiểm soát data riêng (privacy + compliance).
- Không phải maintain SaaS server.
- Phù hợp đồ án — "đây là sản phẩm tao build, đây là cách dùng".

**Cons**:
- Reuse "chân thật" còn hạn chế — vẫn phụ thuộc GitHub Actions + tên artifact.
- Mỗi team phải có Gemini key (cost).
- Public webhook URL (ngrok / cloudflare tunnel) — barrier với non-tech.

**Để tăng tính tái sử dụng trong scope option A**:
1. **Tách config**: artifact names + patterns đưa vào `config/profiles/<tool>.yml` (semgrep.yml, codeql.yml, ...). Project mới chỉ cần chọn profile.
2. **Schema doc cho webhook payload** — viết `docs/integration.md` rõ JSON shape.
3. **Adapter pattern trong normalizer** — đã có (`BaseNormalizer`), thêm 2 normalizer ví dụ (Bandit cho Python, Brakeman cho Ruby) để chứng minh extensible.

---

### Option B — GitHub Action `cochecheee/sast-chat@v1` + central dashboard

**Cách dùng (project khác)**:
```yaml
# .github/workflows/sast.yml
- uses: cochecheee/sast-chat@v1
  with:
    sast-tools: 'semgrep,codeql,trivy'
    dashboard-url: ${{ secrets.SAST_CHAT_URL }}
    dashboard-token: ${{ secrets.SAST_CHAT_TOKEN }}
```

Action sẽ:
1. Run các SAST tool trong list (hoặc pickup SARIF từ artifact đã có).
2. Normalize tại runtime.
3. POST findings (already-normalized) vào dashboard API.

**Effort 1 tuần**: ⚠️ rất tham vọng. Cần:
- Viết Action TypeScript / composite action (~1 ngày).
- Refactor backend nhận normalized findings thay vì scrape artifact (~1 ngày).
- Multi-project + multi-tenant ở backend (auth per project token) (~1.5 ngày).
- Test end-to-end trên ALOUTE + 1 repo Python (~1 ngày).
- Còn lại: cắt mock + UI polish + thesis prep.

**Pros**:
- Industry-standard, "thực sự reusable", hội đồng đánh giá cao.
- Onboard 5 phút.
- Không phụ thuộc GitHub artifact format → portable hơn.

**Cons**:
- 1 tuần rất chật — risk fail demo cao.
- Multi-tenant auth + UI cho list project = thêm scope.
- Cần host dashboard chạy 24/7 (không phải localhost).

---

## 4. Recommendation — Hybrid pragmatic

> **Chọn A làm core. Ship A trong 1 tuần. Pre-build foundation cho B.**

**Lý do**:
1. Đồ án 1 tuần — risk delivery > risk reuse depth. A đảm bảo demo end-to-end.
2. Sự thật là **reuse "thực sự"** chỉ chứng minh khi có ít nhất 2 project khác stack chạy đồng thời. Trong 1 tuần khó có thời gian wire repo Python/Node thứ 2 để chứng minh B.
3. A vẫn cho phép **trình bày được "tính tái sử dụng"** nếu đóng gói gọn (Docker + profile config + schema doc).
4. Nếu thừa thời gian (cuối tuần), refactor 1 phần thành Action — bonus.

**Cụ thể đóng gói trong option A**:

```
sast-chat/
├── docker-compose.yml            # 1 file run tất cả
├── docker-compose.example.yml    # template cho project khác
├── .env.example                  # schema + comment
├── config/
│   └── profiles/
│       ├── github-actions-default.yml   # tên artifact mặc định cho CI ALOUTE
│       ├── github-actions-spring.yml    # variant cho Spring Maven
│       └── README.md                    # cách viết profile
├── docs/
│   ├── integration.md            # how to plug in từ project khác
│   ├── webhook-schema.md         # JSON shape /webhook/pipeline-complete
│   ├── adapter-guide.md          # cách viết Normalizer cho tool mới
│   └── deploy.md                 # docker / cloudflare tunnel
├── scripts/
│   └── ci-snippet.yml            # paste vào workflow của project bất kỳ
├── mcp/                          # backend (đã có, refactor)
├── dashboard/                    # frontend (đã có, cắt mock)
└── README.md                     # quickstart 5 phút
```

**Để chứng minh "tái sử dụng" cho hội đồng**:
1. Demo chính: chạy trên ALOUTE_Spring_Thymeleaf_RCE end-to-end.
2. Demo phụ (nếu có thời gian): show config profile cho Spring Maven hypothetical (hoặc tạo dummy repo Python với Bandit, dùng profile `python-bandit.yml`).
3. Trong slide: "Để onboard project mới: clone, edit profile, paste 1 step CI, done — 30 phút."

---

## 5. Decision matrix tóm tắt

| Tiêu chí | Option A (Docker) | Option B (GitHub Action) | Hybrid (recommend) |
|---|---|---|---|
| Onboard time team mới | 30 phút | 5 phút | 30 phút |
| 1 tuần khả thi? | ✅ | ⚠️ Risky | ✅ |
| Reuse "thực sự" | Trung bình | Cao | Trung bình + foundation |
| Demo end-to-end ổn? | ✅ | ⚠️ | ✅ |
| Hội đồng ấn tượng? | OK | Cao nếu xong | OK + kế hoạch tương lai rõ |
| Risk fail demo | Thấp | Cao | Thấp |

→ **Chốt: Option A + chuẩn bị foundation cho Option B**. Kế hoạch chi tiết trong `PLAN-1WEEK.md`.
