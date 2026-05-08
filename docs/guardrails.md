# AI Guardrails

> Mọi finding content gửi đến Gemini phải qua 2 layer guardrails. Đây là phần "shift left" cho AI — không tin source artifact (CI có thể bị compromise) và không tin nội dung CVE description (có thể có injection).

Module: `mcp/src/core/guardrails.py`. Test coverage: 24 cases (`tests/test_guardrails_scrubbing.py`, `tests/test_guardrails_injection.py`).

---

## Layer 1 — Scrubbing (`ScrubbingService`)

Áp dụng trước khi normalize, mục tiêu: **không lưu PII/secret vào DB**. Mọi artifact content (SARIF / XML / JSON) được scrub trước khi parse.

### Patterns được scrub

| Pattern | Replacement | Lý do |
|---|---|---|
| Email (`user@domain.tld`) | `[EMAIL_SCRUBBED]` | GDPR + tránh leak commit author |
| IPv4 (`x.x.x.x`) | `[IP_SCRUBBED]` | Tránh leak internal IP |
| Bất kỳ secret nào `detect-secrets` flag (full line) | `[SECRET_SCRUBBED]` | AWS keys, API tokens, private keys, JWT, generic high-entropy strings |

### Implementation

`detect-secrets` scan file tạm → trả set line numbers chứa secret → toàn bộ dòng đó replace bằng marker. Email/IP regex chạy sau → replace inline.

### Limitations

- Không scrub URL có embed credentials (`https://user:pass@host`). Nếu CI artifact có loại này, line đó sẽ vào DB. Mitigation: review artifact format từ tool sinh ra.
- Không scrub credit card number (không applicable cho SAST findings).

---

## Layer 2 — Injection prevention (`InjectionGuardrail`)

Áp dụng ngay trước khi build prompt cho Gemini. Mục tiêu: **không cho phép finding content thay đổi system prompt**.

### Check

Reject content nếu:

1. Length > **2000 chars** (DoS + token cost protection).
2. Match bất kỳ regex sau:

   ```python
   r"<script"                                 # XSS payload
   r"ignore\s+(all\s+)?previous\s+instructions?"  # classic prompt injection
   r"forget\s+your\s+instructions?"
   r"\bsystem\s+prompt\b"
   r"\bjailbreak\b"
   r"\bDAN\s+mode\b"
   r"IGNORE\s+ALL"
   r"\bSystem\.exit\b"
   r"you\s+are\s+now\b.{0,30}\bAI\b"
   ```

Trả `(False, reason)` → caller skip Gemini call, log warning, không lưu kết quả AI.

### Sanitize

Khi content pass check, vẫn truncate xuống 2000 chars + strip control chars (`\x00-\x08`, `\x0b\x0c`, `\x0e-\x1f`, `\x7f`) trước khi đưa vào prompt template.

---

## Test coverage

```
tests/test_guardrails_scrubbing.py — 4 cases
  ✓ scrubs single line containing AWS-style secret
  ✓ scrubs multiple secret lines
  ✓ scrubs email + IP combined with normal text
  ✓ preserves clean code unchanged

tests/test_guardrails_injection.py — 20 cases
  ✓ check rejects 9 injection patterns (parametrized)
  ✓ check rejects oversized content (> 2000 chars)
  ✓ check passes safe SAST finding
  ✓ check passes normal SQL injection finding wording
  ✓ sanitize truncates long content
  ✓ sanitize removes control chars
  ✓ sanitize preserves newlines + tabs
  ✓ sanitize short content unchanged
```

Run: `pytest tests/test_guardrails_*.py -v`. Hiện 24/24 pass (verify cuối Day 3).

---

## Decision log

- **2026-04**: Added `detect-secrets` thay vì regex tự viết. Lý do: regex tự viết miss nhiều variant (AWS access key v4, GitHub PAT format mới).
- **2026-05-08 (Day 3)**: Verified guardrails 24/24 pass sau Day 2 scaffolding refactor. Không thay đổi logic. Khi multi-tenant runtime kích hoạt (Day 6+) cần add test case cho mock injection trong `Project.gemini_api_key` field — không expose qua API hiện tại nhưng nếu sau này có UI input thì scrub trước khi save.

---

## Tradeoff đã chấp nhận

Guardrails false positive (block content lành tính có chứa từ "system prompt" trong message) > false negative (cho injection lọt). User báo cáo false positive qua dashboard log, devops nới regex sau.

Không có self-learning — pattern hardcoded để audit được. Đây là "defense in depth" trên Gemini của Google đã có safety filter riêng; chat-system layer là defense bổ sung, không thay thế.
