# Phase 3: LLM Orchestrator Integration - Research

**Researched:** 2026-04-16 (Updated)
**Domain:** Large Language Model (LLM) Integration for Security Analysis
**Confidence:** HIGH

## Summary

Dự án tích hợp Gemini API để tự động phân tích lỗ hổng từ các công cụ SAST và đề xuất mã sửa lỗi (remediation). Nghiên cứu tập trung vào việc sử dụng SDK chính thức mới nhất của Google, tối ưu hóa Prompt Engineering cho bài toán bảo mật, quản lý ngữ cảnh mã nguồn lớn, và đảm bảo đầu ra an toàn, chính xác bằng tiếng Việt.

**Primary recommendation:** Sử dụng **`google-genai`** SDK (thay thế `google-generativeai` đã deprecated) với Structured Output (Pydantic trực tiếp) để ép buộc Gemini trả về dữ liệu có cấu trúc. Tích hợp `slowapi` để xử lý rate limiting.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `google-genai` | >=1.73.1 | Truy cập Gemini API | SDK mới chính thức từ Google, thay thế `google-generativeai` đã deprecated. Hỗ trợ Pydantic trực tiếp. |
| `pydantic` | >=2.0 | Schema validation | Tiêu chuẩn công nghiệp để định nghĩa và xác thực cấu trúc dữ liệu JSON. |
| `slowapi` | >=0.1.9 | Rate Limiting | Middleware tích hợp FastAPI để kiểm soát tốc độ gọi API Gemini. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|--------------|
| `python-dotenv` | >=1.0.0 | Quản lý API Key | Lưu trữ `GEMINI_API_KEY` an toàn trong môi trường local. |

### Deprecated (KHÔNG dùng)
| Library | Lý do |
|---------|-------|
| `google-generativeai` | Đã bị Google deprecated. Thay bằng `google-genai`. |
| `typing_extensions.TypedDict` | Không cần nữa — `google-genai` nhận Pydantic model trực tiếp. |

**Installation:**
```bash
pip install google-genai pydantic slowapi python-dotenv
```

## Architecture Patterns

### Recommended Project Structure
```
mcp/src/services/llm/
├── client.py        # Gemini API client wrapper (google-genai)
├── prompts.py       # Prompt templates & system instructions (tiếng Việt)
├── schemas.py       # Pydantic models for structured output
├── validator.py     # Response validation and cleaning logic
└── service.py       # LLMAnalysisService orchestrator
```

### Pattern 1: Structured Output với Pydantic (google-genai)
**What:** Truyền Pydantic model trực tiếp vào `response_schema` thay vì TypedDict.
**When to use:** Luôn luôn — đảm bảo AI trả về JSON đúng cấu trúc ở mức token decoding.
**Example:**
```python
# Source: google-genai SDK docs
from google import genai
from google.genai import types
from pydantic import BaseModel

class AnalysisOutput(BaseModel):
    vulnerability_id: str
    explanation_vi: str
    impact_vi: str
    remediation_diff: str
    severity: str
    cwe_reference: str
    confidence: str

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

response = client.models.generate_content(
    model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=AnalysisOutput,
        system_instruction=SYSTEM_INSTRUCTION,
    )
)
result = AnalysisOutput.model_validate_json(response.text)
```

### Pattern 2: Model Selection qua Environment Variable
**What:** Model name đọc từ env var để dễ dàng thay đổi mà không cần sửa code.
**Example:**
```python
# .env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash   # hoặc gemini-2.5-pro

# client.py
model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
```

### Pattern 3: Rate Limiting với slowapi
**What:** Kiểm soát số lượng request đến Gemini API để tránh vượt quota.
**Example:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Trong service: thêm local rate limiting
# Max 10 AI analysis requests per minute
@limiter.limit("10/minute")
async def analyze_vulnerability(...):
    ...
```

### Pattern 4: Retry với Exponential Backoff
**What:** Tự động retry khi gặp lỗi 429 (quota exceeded) hoặc 503 (overload).
**Example:**
```python
import asyncio

async def call_with_retry(client, prompt, max_retries=3):
    for attempt in range(max_retries):
        try:
            return await client.generate(prompt)
        except Exception as e:
            if "429" in str(e) or "503" in str(e):
                wait = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait)
            else:
                raise
    raise RuntimeError("Gemini API không phản hồi sau 3 lần thử")
```

### Pattern 5: Surgical Context Injection
**What:** Chỉ gửi đoạn code xung quanh lỗ hổng (30 dòng: 15 trên + 15 dưới) thay vì toàn bộ file.
**Anti-Pattern to Avoid:**
- **Whole-file dump:** Tăng chi phí token, làm loãng kết quả phân tích.
- **No-context analysis:** Chỉ gửi message của SAST tool — AI sẽ hallucinate vì không biết logic cụ thể.

## Output Schema (Cập nhật)

```python
class AnalysisOutput(BaseModel):
    vulnerability_id: str        # ID tham chiếu lỗ hổng (từ SAST finding)
    explanation_vi: str          # Giải thích lỗ hổng bằng tiếng Việt
    impact_vi: str               # Mô tả tác động bằng tiếng Việt
    remediation_diff: str        # Unified Diff format để sửa lỗi
    severity: str                # CRITICAL / HIGH / MEDIUM / LOW
    cwe_reference: str           # VD: "CWE-89: SQL Injection"
    confidence: str              # HIGH / MEDIUM / LOW
```

## Prompt Templates (Tiếng Việt)

```python
SYSTEM_INSTRUCTION = """
Bạn là Chuyên gia Bảo mật Ứng dụng cao cấp với hơn 10 năm kinh nghiệm.
Nhiệm vụ: Phân tích kết quả từ công cụ SAST và đề xuất cách khắc phục chi tiết.
Ngôn ngữ phản hồi: Tiếng Việt (bắt buộc cho tất cả các trường giải thích).
Quy tắc:
1. Giải thích lỗ hổng dựa trên logic mã nguồn được cung cấp, không phỏng đoán.
2. Đề xuất mã sửa lỗi dưới dạng Unified Diff — chỉ thay đổi những gì cần thiết.
3. Không bao giờ đề xuất xóa toàn bộ logic nghiệp vụ để "an toàn hơn".
4. Đánh giá confidence dựa trên lượng context code được cung cấp.
5. Không tiết lộ thông tin nhạy cảm hoặc API keys trong phản hồi.
"""

USER_PROMPT_TEMPLATE = """
### Thông tin lỗ hổng từ SAST
- Công cụ: {tool_name}
- Rule ID: {rule_id}
- Mô tả: {message}
- File: {file_path}, dòng {line_number}
- CWE: {cwe_id}

### Mã nguồn ngữ cảnh (30 dòng xung quanh)
```java
{code_context}
```

Hãy phân tích lỗ hổng trên và trả về kết quả theo JSON schema đã định nghĩa.
"""
```

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON Extraction | Regex/String searching | `response_schema` | `google-genai` ép buộc output JSON ở mức token decoding. |
| Rate Limiting | Custom counter/sleep | `slowapi` | Handles distributed state, headers, và FastAPI integration. |
| Retry Logic | Custom while loop | Exponential backoff pattern | Tránh thundering herd khi nhiều findings được phân tích cùng lúc. |

## Common Pitfalls

### Pitfall 1: Model Hallucination trong Remediation
**How to avoid:**
1. System Prompt yêu cầu Unified Diff thay vì rewrite toàn bộ function.
2. Thêm field `confidence` — LOW confidence báo hiệu cần human review kỹ hơn.
3. Không tự động apply code — bắt buộc human approval qua `/approve` command.

### Pitfall 2: Vietnamese Encoding trong JSON
**Prevention:** Pydantic tự xử lý UTF-8, dùng `model.model_dump_json()` thay vì `json.dumps()`.

### Pitfall 3: Quota Exhaustion
**What goes wrong:** Phân tích đồng thời nhiều findings → 429 errors.
**How to avoid:** `slowapi` + queue phân tích tuần tự, không song song.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `google-generativeai` SDK | `google-genai` SDK | 2024 (deprecated) | API thay đổi, hỗ trợ Pydantic trực tiếp. |
| TypedDict cho schema | Pydantic BaseModel | 2024 | Type safety tốt hơn, tích hợp trực tiếp với FastAPI. |
| `gemini-1.5-flash` | `gemini-2.5-flash` | 2025 | Nhanh hơn, chính xác hơn, chi phí tương đương. |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `gemini-2.5-flash` đủ chính xác cho phân tích Java security | Summary | Thấp — có thể switch sang `gemini-2.5-pro` qua env var. |
| A2 | 30 dòng context đủ để phân tích phần lớn lỗ hổng Java | Architecture | Trung bình — complex class hierarchies có thể cần thêm context. |
| A3 | `slowapi` đủ cho rate limiting single-instance | Standard Stack | Thấp — đủ cho scope đồ án. |

## Environment Variables

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
GEMINI_MAX_RETRIES=3
GEMINI_RATE_LIMIT=10/minute
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` + `pytest-asyncio` |
| Style | Code first, test after |
| Quick run | `pytest mcp/tests/services/llm/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | File |
|--------|----------|-----------|------|
| REQ-3.1 | Gemini API gọi thành công | Integration (mocked) | `test_client.py` |
| REQ-3.2 | Output bằng tiếng Việt | Unit | `test_service.py` |
| REQ-3.3 | Unified Diff hợp lệ | Unit | `test_remediation.py` |
| REQ-3.4 | Pydantic validation bắt lỗi schema | Unit | `test_validator.py` |
| REQ-3.5 | Rate limit hoạt động | Unit | `test_rate_limit.py` |

## Security Domain

### Known Threat Patterns for LLM

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt Injection | Tampering | System Instructions cố định + dấu phân cách `###` cho user content. |
| Insecure Output | Information Disclosure | Filter đầu ra qua Guardrails trước khi lưu DB. |
| RCE via Remediation | Tampering | Human-in-the-loop bắt buộc — KHÔNG auto-apply code. |

## Sources

### Primary (HIGH confidence)
- [google-genai Python SDK](https://github.com/googleapis/python-genai) - Official new SDK.
- [Gemini API Docs - Structured Output](https://ai.google.dev/gemini-api/docs/structured-output) - Pydantic response schema.
- [slowapi GitHub](https://github.com/laurentS/slowapi) - FastAPI rate limiting.

**Research date:** 2026-04-16
**Valid until:** 2026-07-16
