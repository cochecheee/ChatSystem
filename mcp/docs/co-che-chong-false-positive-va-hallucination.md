# Cơ chế chống False Positive & chống Hallucination (LLM) — tổng hợp chi tiết

> Tài liệu tham chiếu (ôn bảo vệ) trả lời hai câu hỏi:
> 1. Hệ thống **đã có cơ chế tránh false positive chưa? Cơ chế là gì?**
> 2. Với **hallucination của LLM**, đã dùng cách nào để giải quyết?
>
> Trả lời ngắn: **Có — cả hai đều là nhiều lớp phòng thủ chồng nhau (defense-in-depth)**, không phải một
> chỗ. Mọi phán quyết FP / mọi bản vá của AI đều bị **đối chiếu ngược lại mã nguồn thật bằng code
> (deterministic)**; thiếu bằng chứng thì **tự hạ cấp**; và **con người là người quyết định cuối**.
>
> Tài liệu này gộp V4.2 (analyze) + V4.3 (investigate) + Tier‑3 triage + prompt + schema. Doc V4.2 gọn
> hơn: `ai-false-positive-and-hallucination.md`. Mọi `file:line` đúng tại thời điểm viết — verify trước khi trích.

---

## A. CHỐNG FALSE POSITIVE — 5 lớp

Xếp theo dòng chảy: giảm nhiễu → phán đoán trên code thật → kỷ luật tự động → điều tra sâu → con người quyết.

### Lớp 1 — Giảm nhiễu đầu vào (gián tiếp)
Khử trùng lặp cross-tool (V4.0) + chuẩn hoá severity (V4.1) cắt cảnh báo trùng/sai bậc → giảm "FP giả
tạo do đếm trùng, over/under-rate". Không phải FP thật nhưng làm sạch đầu vào trước khi AI xét.

### Lớp 2 — LLM đánh giá FP **dựa trên MÃ NGUỒN THẬT, không đoán từ metadata**
Nguyên tắc cốt lõi, ép ở **cả prompt lẫn code**:

- **`prompts/v1/analyze.system.md:14`** — *"TRƯỚC TIÊN đánh giá false positive DỰA TRÊN mã nguồn thật
  được cung cấp (không đoán): đầu vào đã sanitize/validate trước khi tới sink chưa? sink có reachable
  với dữ liệu người dùng không? có phải test/example/mock?"* → điền `false_positive_likelihood`
  (HIGH|MEDIUM|LOW) + `false_positive_reason`.
- **`prompts/v1/triage.system.md:15,20-23`** — *"Be conservative: prefer NEEDS_REVIEW over a confident
  FALSE_POSITIVE... If NO source code is shown, you cannot verify the data flow — return NEEDS_REVIEW,
  never a confident FALSE_POSITIVE."*
- Trường `false_positive_likelihood` + validator clamp — `llm/schemas.py:15,36-41`.

### Lớp 3 — Batch triage: **auto-thu hồi có kỷ luật** (`services/llm/triage.py`)
`TriageService.triage_findings` (`triage.py:85`) chỉ tự động `REVOKED` khi thoả **cả ba** điều kiện:
1. Phân loại `FALSE_POSITIVE`, **và**
2. `confidence >= 0.8` (`confidence_threshold`, `triage.py:90,177-180`), **và**
3. **`code_seen == True`** — mô hình *thực sự đã nhìn thấy code* của finding đó (`triage.py:184-195`):

```python
if not dry_run and f is not None and is_fp_high and f.status != "REVOKED":
    # V4.2 — only auto-revoke when the model actually saw the code
    if code_seen.get(item.finding_id):
        f.status = "REVOKED"; f.revoked_by = invoked_by; ...
    else:
        withheld_no_code += 1            # KHÔNG thấy code → giữ cho người review
        action["withheld"] = "no_code_context"
```

`code_seen` dựng từ source cache hoặc fetch GitHub best-effort (giới hạn 15 file/lượt, dung thứ lỗi —
`triage.py:123-147`). **Không bao giờ suppress một finding chỉ từ metadata.** Prompt cũng buộc
NEEDS_REVIEW khi không có code.

### Lớp 4 — Điều tra chuyên sâu `investigate_finding` (V4.3, `services/llm/service.py:422`)
Kích hoạt bằng lệnh `/verify <id>` hoặc câu hỏi chat "lỗi này có thật không?". Lần luồng
`source → propagation → sanitizer → sink` trên code thật, trả **3 trạng thái**
`TRUE_POSITIVE | FALSE_POSITIVE | UNCERTAIN`:

- **Không có source → UNCERTAIN** (`service.py:465-474`) — *không bao giờ FP từ metadata*.
- Finding phụ thuộc/CVE → UNCERTAIN + hướng đối chiếu version (`service.py:447-462`).
- **Advisory-only**: `_persist_investigation` chỉ lưu vào `raw_data['fp_investigation']`, **KHÔNG đổi
  `finding.status` / `finding.ai_analysis`** (`service.py:432-433, 542-549`).

### Lớp 5 — Con người giữ quyết định cuối (human-in-the-loop)
AI chỉ **đề xuất** (chip `/revoke` cho FP, `/fix` cho TP — `service.py:528-532`); con người mới bấm.
- `/revoke` + `/approve` bắt **justification** (≥20 ký tự), ghi **audit** vào bảng `finding_actions`.
- **RBAC**: chỉ `security_lead`+ được `/revoke`/`/approve`; `developer` chỉ `/explain`/`/verify`.
- **Carry-forward**: REVOKED (Tier‑1 hash) + suppression rule (Tier‑2 pattern) để FP đã duyệt không
  hiện lại ở lần quét sau (`processor.py` auto-triage).

---

## B. CHỐNG HALLUCINATION của LLM — 6 lớp (+ guardrail)

Ý tưởng xuyên suốt: **mọi khẳng định phải "neo" (grounded) vào mã nguồn thật; nếu không neo được thì
hạ tin cậy / hạ kết luận, không trình ra như thật.** Tức là **không tin lời LLM** — kiểm lại bằng code.

### Lớp 1 — Chỉ phân tích trên source thật fetch được
Không lấy được code → analyze/triage/investigate đều trả UNCERTAIN/NEEDS_REVIEW
(`service.py:465`, `triage.py:184`, `triage.system.md:22`). Cắt gốc việc "bịa từ tên rule/metadata".

### Lớp 2 — Prompt cấm bịa + buộc trích dẫn nguyên văn
- `analyze.system.md:19-20` — *"TUYỆT ĐỐI không bịa mã không có trong ngữ cảnh... các dòng ngữ cảnh/xoá
  PHẢI neo đúng vào mã nguồn thật đã cho (nếu không chắc dòng nào tồn tại thì đừng đưa vào diff)."*
- `investigate.system.md:17,22-23` — *"TUYỆT ĐỐI không bịa mã, không suy đoán về code không được cho
  thấy"*; `quote` = **COPY NGUYÊN VĂN**; `code_ref` = **SỐ DÒNG THẬT** hiển thị bên trái mã nguồn.

### Lớp 3 — Kiểm chứng grounding hậu kỳ (bằng code, không tin lời mô hình)
Hai hàm deterministic tự đối chiếu output với source đã fetch:

- **`verify_diff_grounding(remediation_diff, source_code)`** — `service.py:67-102`. Tách các dòng "neo"
  (context/removed, bỏ dòng `+`) của bản vá, đòi **≥60%** xuất hiện trong source thật; bản vá tham chiếu
  mã không có thật → fail.
```python
hits = sum(1 for a in anchors if a in src_joined)
ratio = hits / len(anchors)
if ratio >= 0.6: return True, f"diff khớp {hits}/{len(anchors)} dòng neo..."
return False, "... có thể AI bịa mã không có thật"
```
- **`verify_investigation_grounding(steps, source_code)`** — `service.py:139-181`. Mỗi bước lập luận,
  `quote` phải nằm trong **đúng dải dòng đã trích** (khớp mạnh) hoặc **trong toàn source** (khớp yếu,
  chống lệch cửa sổ); tổng **≥60%** bước-có-trích-dẫn mới coi là grounded.

### Lớp 4 — Hạ tin cậy / hạ kết luận khi KHÔNG neo được (MẤU CHỐT)
- `analyze_finding`: bản vá ungrounded → **confidence ép về `LOW`** + `grounded_note` cảnh báo
  (`service.py:379-385`).
- `investigate_finding`: **FALSE_POSITIVE mà không grounded → HẠ về `UNCERTAIN`** + confidence LOW
  (`service.py:520-526`):
```python
if verdict == "FALSE_POSITIVE" and not overall:
    verdict = "UNCERTAIN"; confidence = "LOW"; fpl = "MEDIUM"
    grounded_note += " — hạ về UNCERTAIN vì bằng chứng chưa neo được vào mã thật"
```
→ **Không bao giờ trình một phán quyết FP dựa trên bằng chứng bịa.**

### Lớp 5 — Schema validator "chốt chặn" giá trị bịa (`llm/schemas.py`)
Pydantic clamp mọi giá trị ngoài tập cho phép về mặc định an toàn:
- `verdict` lạ → `UNCERTAIN` (`:82-87`); `confidence`/`false_positive_likelihood` lạ → `LOW`
  (`:36-41,89-94`); `severity` lạ → `MEDIUM` (`:18-25`); `kind` lạ → `""` (`:67-72`).
- Mô hình "chế" enum ngoài tập cũng bị quy về mặc định thận trọng, không lọt ra ngoài.

### Lớp 6 — "Khi không chắc phải chọn UNCERTAIN" + minh bạch trên UI
- `investigate.system.md:27` — *"Khi không chắc, PHẢI chọn UNCERTAIN — không đoán FALSE_POSITIVE."*
- FE hiện badge từng bước **"✓ khớp mã thật" / "⚠ chưa neo được"** và badge bản vá **"✓ đã đối chiếu mã
  nguồn thật" / "⚠ chưa neo được — độ tin cậy thấp"** → người xem thấy rõ phần nào được neo, hệ thống
  không trình mã bịa như thật.

### Bổ trợ — Guardrail L3/L4
Trước khi đưa context vào LLM: L3 scrub secret/PII + L4 chặn prompt-injection (`service.py:478-483`).
Giảm hallucination/lệch hướng do context bị đầu độc.

---

## Bảng tóm tắt

| Vấn đề | Cơ chế chính | Nơi (file:line) |
|---|---|---|
| FP | Đánh giá FP **trên code thật**, không từ metadata | prompts + `service.py:465`, `triage.py` |
| FP | Auto-revoke chỉ khi FP + conf≥0.8 + **đã thấy code** | `triage.py:177-195` |
| FP | Điều tra 3-trạng thái, **advisory-only** (không tự đổi status) | `service.py:422-554` |
| FP | Con người duyệt (justification + RBAC + audit) + carry-forward | `command_service.py`, `processor.py` |
| Hallucination | **Grounding** bản vá + từng bước lập luận (ngưỡng ≥60%) | `service.py:67`, `service.py:139` |
| Hallucination | Ungrounded → hạ confidence / hạ FP→UNCERTAIN | `service.py:384-385`, `service.py:522-526` |
| Hallucination | Không source → UNCERTAIN (không phán từ metadata) | `service.py:465`, `triage.py:184` |
| Hallucination | Schema clamp giá trị lạ về mặc định thận trọng | `llm/schemas.py:18-94` |

## Thông số quan trọng (để trả lời phản biện)
- Ngưỡng grounding: **0.6** (60% dòng neo / bước trích dẫn phải có trong source) — `service.py:98,179`.
- Ngưỡng auto-revoke triage: **confidence ≥ 0.8** — `triage.py:90`.
- Giới hạn fetch source trong triage: **15 file/lượt** (bounded, tránh rate-limit) — `triage.py:128`.
- Cửa sổ context: analyze ±15 dòng (`_extract_context`); investigate cả file nếu ≤400 dòng, else ±40
  dòng, đánh số dòng tuyệt đối (`_extract_wide_context`, `service.py:120`).

## Câu chốt khi bảo vệ
> "Hệ thống **không tin lời LLM**: mọi kết luận false-positive và mọi bản vá đều được **đối chiếu ngược
> với mã nguồn thật bằng code (deterministic grounding)**; khi bằng chứng chưa neo được thì hệ thống
> **tự hạ độ tin cậy / hạ kết luận về UNCERTAIN** thay vì trình ra như đúng; và **con người giữ quyền
> quyết định cuối** với justification, phân quyền và nhật ký kiểm toán."

Liên quan: memory `ai-fp-hallucination-v42`, `chat-fp-investigation-v43`; doc `ai-false-positive-and-hallucination.md`.
