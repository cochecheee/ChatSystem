# OPEN QUESTIONS — Cần mày confirm trước/trong khi triển khai

> Những điểm tao chưa rõ, hoặc có nhiều cách làm và mày phải chốt. Đặt theo thứ tự cần trả lời sớm.

---

## Cần trả lời TRƯỚC khi bắt đầu Day 1

### Q1. Multi-project có thực sự cần không?

Có 2 hướng:

- **A. Single-tenant** — 1 instance phục vụ 1 project (ALOUTE). Project khác clone + deploy instance riêng. Đây là *Docker Compose template* model.
- **B. Multi-tenant nhẹ** — 1 instance phục vụ nhiều `Project`, mỗi project có own GitHub creds + Gemini key.

PLAN hiện viết theo B (Day 2 dành 1 ngày). Nếu chọn A:
- Tiết kiệm 1 ngày (Day 2 trống → đẩy lên buffer).
- Demo "tái sử dụng" yếu hơn — chỉ demo "deploy được nhiều instance riêng".

**Câu hỏi**: hội đồng có hỏi *"nếu công ty có 50 microservice thì sao?"* không? Nếu CÓ → chọn B. Nếu KHÔNG quan tâm scale → A đủ.

→ Tao recommend B nhẹ (chỉ extract config, không multi-tenant auth full).

---

### Q2. Demo target thứ 2 (Python/Node) có cần không?

REUSABILITY.md đề cập "demo phụ" với 1 repo Python + Bandit để chứng minh extensible. Day 6 dự kiến viết example profile, không demo thực.

**Câu hỏi**: mày muốn demo thật repo Python thứ 2 không? Nếu CÓ:
- Cần thêm 0.5-1 ngày: dựng repo Python dummy có RCE/SQLi sample, viết workflow Bandit, wire vào dashboard.
- Tăng thuyết phục "thực sự tái sử dụng".

Nếu KHÔNG: chỉ document profile, không demo live.

→ Tao recommend KHÔNG (rủi ro overrun) — trừ khi mày thấy hội đồng gắt về reuse.

---

### Q3. Mức độ "đóng gói chuyên nghiệp" tới đâu?

Có 3 cấp:
1. **Cấp tối thiểu**: docker-compose + .env.example + README. Đủ cho thesis.
2. **Cấp trung**: + image push lên Docker Hub `cochecheee/sast-chat:latest`, + CI build image trên GitHub Actions của chính chat-system.
3. **Cấp cao**: + Helm chart, + GitHub release v0.1.0, + GitHub Action wrapper.

PLAN viết theo cấp 1. Cấp 2 thêm 0.5 ngày (Day 7 buffer). Cấp 3 thêm 1.5 ngày → vượt scope tuần.

→ Tao recommend cấp 1 (đủ thesis), bonus cấp 2 nếu Day 7 dư.

---

## Cần trả lời TRƯỚC Day 5 (demo wire-up)

### Q4. ALOUTE secrets — mày đã có sẵn chưa?

Day 5 cần các secrets sau cho ALOUTE workflow:
- `NVD_API_KEY` (Dependency-Check) — đăng ký free tại nvd.nist.gov.
- `SONAR_TOKEN`, `SONAR_ORGANIZATION`, `SONAR_PROJECT_KEY` (SonarCloud) — có thể skip Gate 2 nếu chưa có.
- `DOCKER_USERNAME`, `DOCKER_PASSWORD` (Docker Hub) — có thể skip stage Docker.
- `MCP_GATEWAY_URL`, `MCP_WEBHOOK_TOKEN` — sẽ tạo khi deploy chat-system Day 5.

**Câu hỏi**: mày đã có những token nào? Nếu thiếu → Day 5 phải tweak workflow ALOUTE để bypass.

→ Tao recommend trước Day 5 mày check liệt kê tất cả secret có sẵn.

---

### Q5. Public URL cho webhook khi demo

ALOUTE CI cần POST về `MCP_GATEWAY_URL` — phải là URL public.

Lựa chọn:
- **ngrok free** — URL đổi mỗi lần restart, OK cho demo.
- **cloudflared tunnel** — URL cố định nếu có domain Cloudflare, ổn định hơn.
- **Deploy thật lên VPS / Render / Railway** — chuyên nghiệp, demo ổn nhất.

→ Tao recommend cloudflared nếu có domain, ngrok nếu không. Deploy VPS chỉ làm nếu Day 7 dư.

---

## Câu hỏi sản phẩm / scope

### Q6. AI prompt language — chỉ tiếng Việt hay bilingual?

Hiện hardcode tiếng Việt. Project khác (đặc biệt nếu có dev nước ngoài) sẽ muốn tiếng Anh hoặc bilingual.

→ Trong scope 1 tuần KHÔNG fix. Note vào roadmap V2.

### Q7. Có giữ free-form chat (natural language → suggested command) không?

Hiện có. Code đơn giản nhưng risk: Gemini hallucinate command sai → confuse user.

→ Tao recommend giữ vì là feature demo dễ ấn tượng. Note: thêm test case Vietnamese phrasing để verify accuracy.

### Q8. Audit trail xuất CSV / báo cáo compliance không?

Hiện chỉ có HTML report. Compliance team thật sẽ muốn CSV / PDF.

→ Trong scope 1 tuần KHÔNG fix. Có thể đề cập trong slide như "future work".

### Q9. Dashboard có cần dark mode polish không?

Hiện có dark/light toggle (App.tsx L20, L82-86). Sentinel design có 2 theme nhưng mock pages cắt rồi — kiểm tra theme còn ổn cho 6 page real?

→ Day 7 polish bao gồm verify theme.

---

## Câu hỏi về thesis / bảo vệ

### Q10. Bài thuyết trình có cần animation / video, hay slide tĩnh đủ?

PLAN Day 7 chỉ outline slide + screencast backup. Nếu cần production quality → cần thêm 0.5-1 ngày sau Day 8.

→ Hỏi mày: deadline thuyết trình chính xác là khi nào? "1 tuần" này có bao gồm rehearse + slide đẹp không hay chỉ code?

### Q11. Đồ án có yêu cầu báo cáo viết (Word / PDF) bao nhiêu chữ?

Tao thấy có `CHAPTER3_IEEE_FORMAT_EXTENDED.md` trong ALOUTE → có vẻ mày đang viết báo cáo IEEE format. Tuần này có cần update phần "Implementation" không?

→ Note: tao chưa biết status báo cáo viết. Cần mày confirm.

### Q12. Có giảng viên hướng dẫn cần check progress giữa tuần không?

Nếu có meeting Day 3-4 → cần demo giữa kỳ → có thể phải swap thứ tự ngày.

→ Hỏi mày.

---

## Tổng kết — Câu hỏi cần trả lời hôm nay

1. **Q1**: A (single-tenant) hay B (multi-tenant nhẹ)?
2. **Q2**: Có demo repo Python thứ 2 không?
3. **Q3**: Cấp đóng gói 1 / 2 / 3?
4. **Q11**: Cần update báo cáo viết tuần này không?
5. **Q12**: Có meeting GVHD giữa tuần không?

Trả lời 5 câu này tao sẽ adjust PLAN-1WEEK.md cho khớp.
