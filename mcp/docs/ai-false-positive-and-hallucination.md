# AI: đánh giá false positive & chống hallucination khi đề xuất fix — V4.2

> Trả lời: *"Khi AI phân tích, nó có phát hiện được đây là false positive để tránh đào sâu và sửa nhầm
> không? Và làm sao không bịa (hallucinate) bản vá?"* — cùng cách hiển thị tiến trình này lên dashboard.

## 1. Phát hiện false positive NGAY trong lúc phân tích

Trước đây `analyze_finding` luôn sinh giải thích + `remediation_diff` mà không hỏi "đây có phải lỗi
thật không". V4.2: mỗi lần phân tích 1 finding, AI **đánh giá false positive TRƯỚC**, dựa trên **mã
nguồn thật** đã fetch (`service.py` lấy ±15 dòng quanh dòng lỗi):

- Prompt (`prompts/v1/analyze.system.md`) buộc AI xét: input đã sanitize upstream chưa? sink có
  reachable với dữ liệu người dùng không? có phải test/example code không?
- Kết quả có 2 trường mới (`llm/schemas.py::AnalysisOutput`, lưu trong `ai_analysis` JSON — không cần
  migration): `false_positive_likelihood` (HIGH|MEDIUM|LOW; HIGH = nhiều khả năng FP) +
  `false_positive_reason` (1 câu tiếng Việt).
- Khi HIGH → dashboard hiện banner ⚠️ "Khả năng là false positive: CAO — <lý do>" (FindingDetail) để
  dev **cân nhắc trước khi đào sâu sửa**.

## 2. Chống hallucination khi đề xuất fix (grounding verification)

Bản vá (`remediation_diff`) do LLM sinh trước đây đi thẳng vào kết quả, không ai kiểm nó có **neo vào
mã thật** không. V4.2 thêm `verify_diff_grounding(diff, source_code)` (`llm/service.py`):

- Bóc các dòng ngữ cảnh/xoá (non-`+`) của diff → chuẩn hoá khoảng trắng → kiểm tra tỉ lệ xuất hiện
  trong file nguồn thật. `≥60%` neo được → **grounded**; ít hơn → **ungrounded** (nghi AI bịa mã).
- `analyze_finding` chạy verify (chỉ cho SAST/`analyze`; CVE là nâng version manifest nên bỏ qua), set
  `grounded` + `grounded_note`, và **hạ `confidence` xuống LOW khi ungrounded**.
- Dashboard hiện badge trên diff: `✓ đã đối chiếu mã nguồn thật` / `⚠ chưa neo được — tin cậy thấp`.

## 3. FP triage & auto-revoke: siết bằng "phải thấy code"

Batch triage (`llm/triage.py`) tự động **REVOKE** finding (loại khỏi gate) khi AI phân loại
`FALSE_POSITIVE` + confidence ≥ ngưỡng. Trước đây triage chỉ xem **metadata** (rule/msg/file) — chứng
cứ yếu nhất nhưng hành động mạnh nhất. V4.2:

- **Feed code vào triage**: mỗi finding SAST kèm ±context mã nguồn (cache-first, else best-effort fetch
  GitHub, giới hạn 15 file/lần, chịu lỗi). Prompt: "không thấy code → NEEDS_REVIEW, không được FP tự tin".
- **Siết auto-revoke**: chỉ tự REVOKE khi `FALSE_POSITIVE` + `confidence ≥ threshold` + **đã thấy code**
  (`code_seen`). Không thấy code → giữ lại cho người (đếm `withheld_no_code`), không suppress.

## 4. Các lớp phòng thủ có sẵn (nền tảng)

- **Grounding bằng mã thật**: phân tích/triage dựa trên source fetch được, không đoán chung chung.
- **Structured output**: `AnalysisOutput`/`TriageBatch` (pydantic `response_schema`) — severity/
  confidence/FP-likelihood bị **clamp** về tập hợp lệ; không parse tự do.
- **Guardrails** (`core/guardrails.py`, `layer_on`): L3 scrub secret/PII khỏi source trước khi gửi LLM;
  L4 injection guard chặn **indirect prompt injection** từ mã repo không tin cậy (message + code_context).
- **Prompt kỷ luật**: "không bịa mã/không phỏng đoán"; CVE prompt: "không bịa chi tiết CVE/CVSS".
- **Con người trong vòng lặp**: `dry_run` xem trước; mọi REVOKE ghi `revoke_justification` + audit
  (`finding_actions`).

## 5. Hiển thị lên dashboard (tiến trình xử lý)

- **FindingDetail** (panel AI): banner FP + badge grounding trên bản vá.
- **Trang "Xử lý dữ liệu"** (`pages/Processing.tsx`): thêm bước **"AI: FP + grounding"** lấy từ
  `GET /findings/ai-stats` — số đã phân tích, phân bố FP-likelihood, số fix grounded vs ungrounded, số
  AI tự thu hồi, và danh sách **top false-positive** (click mở finding) để dev khỏi đào nhầm.

## 6. Ảnh hưởng & kiểm thử

- **Thay đổi hành vi**: siết auto-revoke → ít REVOKE tự động hơn (nhiều NEEDS_REVIEW) → gate có thể thấy
  nhiều finding hơn chút, đổi lại **giảm mạnh rủi ro suppress nhầm lỗ hổng thật**. Kết hợp carry-forward
  (`processor.py`) + [[severity-normalization-v41]] + [[cross-tool-dedup-v4]].
- Endpoints: `GET /findings/ai-stats` (+ `severity-stats`, `dedup-stats`).
- Tests: `tests/test_grounding.py` (grounded/hallucinated/ai-stats), `tests/test_fp_learning.py`
  (auto-revoke chỉ khi thấy code, withhold khi không), `tests/test_llm_service.py`. Full suite 456 pass.
