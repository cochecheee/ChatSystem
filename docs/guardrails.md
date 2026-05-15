# AI Guardrails — 4 Layer Defense-in-Depth

> Mapping với báo cáo tiến độ docx ch.4.4.2: "Guardrail system hoạt động theo
> mô hình pipeline, trong đó mỗi request đi qua bốn lớp bảo vệ tuần tự".
> Nếu bất kỳ layer nào reject, request KHÔNG đi tiếp tới các layer sau hoặc
> LLM.

```
Request ─► L1 Auth ─► L2 Schema ─► L3 Content sanitization ─► L4 Prompt security ─► Gemini LLM
            │           │            │                           │
            └─ 401/403   └─ 422       └─ replace inline           └─ reject or sanitize
```

Test coverage: 24 cases (`tests/test_guardrails_scrubbing.py`, `tests/test_guardrails_injection.py`). Full suite 208/208 pass.

---

## Layer 1 — Authentication

Chỉ caller xác thực mới truy cập endpoint có thể chạm tới LLM hoặc dữ liệu nhạy cảm.

| Vector | Cơ chế | Module |
|---|---|---|
| CI webhook ingest | Bearer token `CI_WEBHOOK_TOKEN` so sánh constant-time | `api/artifacts.py:webhook_pipeline_complete` |
| ChatOps `/api/chat/*` | JWT HS256 + role (developer/security_lead/admin) qua `get_current_user` | `core/auth.py`, `api/chat.py` |
| `/artifacts/process` direct ingest | Optional API key header `X-API-Key=CI_API_KEY` | `api/artifacts.py:require_api_key` |
| Production fail-fast | Lifespan check `SECRET_KEY`, `CI_WEBHOOK_TOKEN`, `CORS_ORIGINS` không default/rỗng → refuse boot | `main.py:_enforce_production_safety` |

**Reject**: 401 (no token) hoặc 403 (token invalid / role không đủ).

---

## Layer 2 — Schema validation

Mọi body request đi qua Pydantic model — request có shape lạ bị chặn ngay tại edge, không cho tới logic.

| Endpoint | Pydantic model |
|---|---|
| `POST /projects` | `ProjectCreate` (`name`, `github_url` required) |
| `POST /webhook/pipeline-complete` | `WebhookRunPayload` (`run_id` int required, `extra="ignore"`) |
| `POST /artifacts/process` | `ProcessRequest` (`project_id`, `github_artifact_id`) |
| `POST /api/chat/command` | `CommandRequest` (whitelist `command` string + optional fields) |
| `POST /findings/{id}/explain` | path int validation |

**Reject**: 422 với chi tiết field nào fail.

**Auxiliary**: trong ChatOps, command name được kiểm tra qua `COMMAND_ROLES` whitelist — lệnh không có trong dict trả 400. Justification yêu cầu `≥ 20 ký tự` cho `/approve|/revoke`, feedback yêu cầu `≥ 5 ký tự`.

---

## Layer 3 — Content sanitization (`ScrubbingService`)

Áp dụng sau khi schema pass, trước khi ghi vào DB hoặc truyền sang LLM. Mục tiêu: **không bao giờ lưu PII / secret raw vào storage**.

Module: `core/guardrails.py:ScrubbingService`. Gọi tại:
- `SecurityProcessor._run` — scrub mọi artifact content trước khi normalize
- `LLMAnalysisService.analyze_finding` — scrub source code GitHub fetch về trước khi cache + đưa Gemini

| Pattern | Replacement | Lý do |
|---|---|---|
| Email `user@domain.tld` | `[EMAIL_SCRUBBED]` | GDPR + tránh leak commit author |
| IPv4 `x.x.x.x` | `[IP_SCRUBBED]` | Internal network info |
| `detect-secrets` flag (full line replace) | `[SECRET_SCRUBBED]` | AWS keys, GitHub PAT, JWT, generic high-entropy |

**Implementation**: `detect-secrets` scan file tạm → trả set line numbers → toàn bộ dòng replace bằng marker. Email/IP regex chạy sau → replace inline.

**Limitations**:
- Không scrub URL có embed credentials `https://user:pass@host`. Nếu CI artifact có loại này, line đó vẫn vào DB.
- Không scrub credit card number (không applicable SAST).

---

## Layer 4 — Prompt security (`InjectionGuardrail`)

Áp dụng ngay trước khi build prompt cho Gemini. Mục tiêu: **không cho finding content thay đổi system prompt** (indirect prompt injection — payload có thể đã ở trong open-source repo hoặc CVE description).

Module: `core/guardrails.py:InjectionGuardrail`. Gọi tại `LLMAnalysisService.analyze_finding` cho cả `message` và `code_context`.

### Check (reject path)

```python
def check(content: str) -> tuple[bool, str]:
    if len(content) > 2000:
        return False, "too long"
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(content):
            return False, f"injection: {pattern.pattern}"
    return True, ""
```

Patterns block:

```python
r"<script"                                 # XSS / HTML inject
r"ignore\s+(all\s+)?previous\s+instructions?"
r"forget\s+your\s+instructions?"
r"\bsystem\s+prompt\b"
r"\bjailbreak\b"
r"\bDAN\s+mode\b"
r"IGNORE\s+ALL"
r"\bSystem\.exit\b"
r"you\s+are\s+now\b.{0,30}\bAI\b"
```

Reject → caller skip Gemini call, log warning, không lưu `ai_analysis`.

### Sanitize (pass path)

Pass `check` rồi vẫn:
- Truncate xuống 2000 chars
- Strip control chars `\x00-\x08`, `\x0b\x0c`, `\x0e-\x1f`, `\x7f`

Trước khi đưa vào prompt template `USER_PROMPT_TEMPLATE`.

### System prompt isolation

Gemini `system_instruction` (xem `services/llm/prompts.py`) là tham số riêng biệt khỏi `contents` — finding content không thể override system role qua đường text concatenation.

Response từ Gemini cũng đi qua schema validation (`AnalysisOutput` Pydantic) — confidence được clamp về HIGH/MEDIUM/LOW, severity về 5 enum chuẩn.

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

Run: `pytest tests/test_guardrails_*.py -v`. 24/24 pass.

Auth + schema layer tests rải rác trong `test_chat_api.py` (auth bypass, role enforcement, schema 422) và `test_api_integration.py` (webhook token).

---

## Decision log

- **2026-04**: Added `detect-secrets` thay vì regex tự viết — bắt nhiều variant (AWS access key v4, GitHub PAT format mới).
- **2026-05-08 (Day 3)**: Verified guardrails 24/24 pass sau scaffolding refactor.
- **2026-05-15 (V2.7)**: Document 4-layer mapping rõ ràng theo docx ch.4.4.2. Code không đổi — auth + schema validation đã có sẵn ở edge, chỉ formalize trong docs để defense map 1:1.

---

## Tradeoff đã chấp nhận

- Guardrails false positive (block content lành tính có chứa từ "system prompt" trong message) > false negative (cho injection lọt). User báo cáo false positive qua dashboard log, devops nới regex sau.
- Pattern hardcoded để audit được (no self-learning).
- "Defense in depth" trên Gemini của Google đã có safety filter riêng; chat-system layer bổ sung, không thay thế.
