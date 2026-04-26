# Hướng dẫn Test MCP Gateway — Phase 2

## Mục lục
1. [Automated Tests (pytest)](#1-automated-tests-pytest)
2. [Live End-to-End Test — Webhook + Dữ liệu thật](#2-live-end-to-end-test--webhook--dữ-liệu-thật)
3. [Manual API Testing](#3-manual-api-testing)
4. [Lấy Run ID & Artifact ID từ GitHub](#4-lấy-run-id--artifact-id-từ-github)
5. [Lưu ý](#5-lưu-ý)

---

## 1. Automated Tests (pytest)

Toàn bộ logic được cover bằng **128 tests** với dữ liệu mock — không cần server chạy, không cần network.

```bash
cd mcp

# Chạy tất cả
.venv/Scripts/python.exe -m pytest tests/ -v

# Chạy nhanh (không verbose)
.venv/Scripts/python.exe -m pytest tests/ -q

# Chạy từng module
.venv/Scripts/python.exe -m pytest tests/test_db.py -v
.venv/Scripts/python.exe -m pytest tests/test_github_client.py -v
.venv/Scripts/python.exe -m pytest tests/test_guardrails_scrubbing.py -v
.venv/Scripts/python.exe -m pytest tests/test_guardrails_injection.py -v
.venv/Scripts/python.exe -m pytest tests/test_normalizer.py -v
.venv/Scripts/python.exe -m pytest tests/test_enricher.py -v
.venv/Scripts/python.exe -m pytest tests/test_processor.py -v
.venv/Scripts/python.exe -m pytest tests/test_poller.py -v
.venv/Scripts/python.exe -m pytest tests/test_schemas.py -v
.venv/Scripts/python.exe -m pytest tests/test_api_integration.py -v
.venv/Scripts/python.exe -m pytest tests/test_e2e.py -v
.venv/Scripts/python.exe -m pytest tests/test_main.py -v
```

### Kết quả kỳ vọng

```
128 passed in ~3s
```

### Phạm vi coverage

| Test file | Tests | Covers |
|-----------|------:|--------|
| `test_normalizer.py` | 40 | SARIF / SpotBugs XML / ESLint JSON / DepCheck JSON / Trivy JSON — parsing, severity mapping, deduplication, smart factory routing |
| `test_guardrails_injection.py` | 17 | 10 injection patterns, length limit, control char strip |
| `test_enricher.py` | 17 | CWE name lookup, OWASP 2021 mapping, CVSS score enrichment |
| `test_api_integration.py` | 14 | REST endpoints (projects, artifacts, findings, webhook, github browser), HTTP status codes, auth |
| `test_github_client.py` | 8 | Artifact download, ZIP extraction, Zip Slip / Zip Bomb protection |
| `test_guardrails_scrubbing.py` | 7 | PII scrubbing (email, IP), secret detection |
| `test_poller.py` | 6 | GitHub polling loop, skip processed runs, error resilience |
| `test_schemas.py` | 5 | Pydantic schema validation, dedup hash |
| `test_processor.py` | 5 | End-to-end pipeline, artifact status transitions |
| `test_e2e.py` | 4 | Full flow: fetch → scrub → normalize → enrich → DB |
| `test_main.py` | 2 | `/health`, `/` root endpoints |
| `test_db.py` | 3 | SQLAlchemy models, CRUD, DB initialization |

---

## 2. Live End-to-End Test — Webhook + Dữ liệu thật

Test toàn bộ pipeline với artifacts thật từ repo `cochecheee/SAST_CICD`.

**Run có sẵn để test:** `run_id = 23856782093` (thành công ngày 2026-04-01, có đủ 5 security artifacts)

### Bước 1: Start server

```bash
cd mcp
.venv/Scripts/uvicorn.exe src.main:app --reload
```

Server chạy tại `http://localhost:8000`.

### Bước 2: (Tùy chọn) Start ngrok để CI webhook gọi được

```bash
"D:/School/DoAnTotNghiep/ngrok-v3-stable-windows-amd64/ngrok.exe" http \
  --domain=nonpoisonous-vicki-undivisively.ngrok-free.dev 8000
```

> Chỉ cần nếu muốn test luồng CI → webhook tự động. Bỏ qua nếu test thủ công qua localhost.

### Bước 3: Gọi webhook với run_id thật

```bash
curl -s -X POST http://localhost:8000/webhook/pipeline-complete \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer VQfwyOv2GPiSVfY4Rgh2KaMUjKLf7o7qkxj7uegEyA4" \
  -d '{"run_id": 23856782093, "pipeline_status": "success"}' | python -m json.tool
```

Kết quả kỳ vọng:
```json
{
  "status": "accepted",
  "run_id": 23856782093,
  "project_id": 1
}
```

Server sẽ tự động:
1. Tạo project `cochecheee/SAST_CICD` nếu chưa có
2. Fetch danh sách artifacts từ GitHub
3. Lọc chỉ lấy 5 security artifacts: `semgrep-report`, `codeql-report`, `dep-check-report`, `trivy-report`, `eslint-report`
4. Download và unzip từng artifact
5. Normalize → enrich → lưu findings vào DB

### Bước 4: Kiểm tra findings

```bash
# Vài giây sau khi gọi webhook
curl -s http://localhost:8000/findings?limit=20 | python -m json.tool

# Lọc theo severity
curl -s "http://localhost:8000/findings?severity=high&limit=10" | python -m json.tool

# Lọc theo project
curl -s "http://localhost:8000/findings?project_id=1&limit=20" | python -m json.tool
```

### Bước 5: Check logs server

Xem terminal chạy uvicorn để theo dõi quá trình xử lý background:

```
INFO:     artifact 1 → processing semgrep-report.sarif
INFO:     artifact 1 → 23 findings saved
...
```

---

## 3. Manual API Testing

### 3.1 Health check

```bash
curl http://localhost:8000/health
```
```json
{"status": "healthy"}
```

---

### 3.2 Projects

```bash
# Tạo project
curl -s -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "Java SAST App", "github_url": "https://github.com/cochecheee/SAST_CICD"}' \
  | python -m json.tool

# Liệt kê projects
curl -s http://localhost:8000/projects | python -m json.tool
```

---

### 3.3 Browse GitHub runs & artifacts

Không cần gọi GitHub API trực tiếp — dùng endpoint của MCP:

```bash
# Liệt kê runs gần đây
curl -s "http://localhost:8000/github/runs" | python -m json.tool

# Liệt kê artifacts của một run
curl -s "http://localhost:8000/github/runs/23856782093/artifacts" | python -m json.tool
```

Artifacts của run `23856782093`:

| ID | Name | Size |
|----|------|------|
| 6223928866 | semgrep-report | 189 KB |
| 6224061293 | codeql-report | 77 KB |
| 6223926183 | dep-check-report | 120 KB |
| 6223914282 | trivy-report | 448 B |
| 6223913132 | eslint-report | 235 B |

---

### 3.4 Trigger xử lý artifact thủ công

```bash
# Trigger process cho 1 artifact cụ thể (dùng artifact ID từ bước 3.3)
curl -s -X POST http://localhost:8000/artifacts/process \
  -H "Content-Type: application/json" \
  -d '{"github_artifact_id": 6223928866, "project_id": 1}' \
  | python -m json.tool
```

Kết quả kỳ vọng (202 Accepted):
```json
{"message": "Processing started", "db_artifact_id": 1, "status": "pending"}
```

---

### 3.5 Findings

```bash
# Tất cả findings
curl -s http://localhost:8000/findings | python -m json.tool

# Lọc theo project + severity
curl -s "http://localhost:8000/findings?project_id=1&severity=high&limit=20" | python -m json.tool

# Chi tiết 1 finding
curl -s http://localhost:8000/findings/1 | python -m json.tool
```

Ví dụ finding từ semgrep:
```json
{
  "id": 1,
  "artifact_id": 1,
  "tool": "semgrep",
  "rule_id": "java.lang.security.audit.sqli.jdbc-sqli",
  "severity": "high",
  "message": "Potential SQL injection via string concatenation",
  "file_path": "src/main/java/com/example/UserDAO.java",
  "line_number": 42,
  "cwe_id": "CWE-89",
  "cvss_score": null,
  "dedup_hash": "a3f9c2...",
  "status": "pending_review",
  "normalized_at": "2026-04-26T10:00:00",
  "raw_data": {
    "owasp_category": "A03:2021 - Injection",
    "cwe_name": "Improper Neutralization of Special Elements used in an SQL Command"
  }
}
```

---

### 3.6 Test Webhook auth

```bash
# Không có token → 403
curl -s -X POST http://localhost:8000/webhook/pipeline-complete \
  -H "Content-Type: application/json" \
  -d '{"run_id": 99999, "pipeline_status": "success"}'

# Token sai → 403
curl -s -X POST http://localhost:8000/webhook/pipeline-complete \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer wrong-token" \
  -d '{"run_id": 99999, "pipeline_status": "success"}'

# Token đúng → 202
curl -s -X POST http://localhost:8000/webhook/pipeline-complete \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer VQfwyOv2GPiSVfY4Rgh2KaMUjKLf7o7qkxj7uegEyA4" \
  -d '{"run_id": 99999, "pipeline_status": "success"}' | python -m json.tool
```

---

### 3.7 Test CI_API_KEY cho `/artifacts/process`

Thêm `CI_API_KEY=my-secret-key` vào `.env`, restart server, sau đó:

```bash
# Không có key → 403
curl -s -X POST http://localhost:8000/artifacts/process \
  -H "Content-Type: application/json" \
  -d '{"github_artifact_id": 123, "project_id": 1}'

# Có key → 202
curl -s -X POST http://localhost:8000/artifacts/process \
  -H "Content-Type: application/json" \
  -H "X-API-Key: my-secret-key" \
  -d '{"github_artifact_id": 123, "project_id": 1}'
```

---

## 4. Lấy Run ID & Artifact ID từ GitHub

### Dùng MCP endpoint (dễ hơn)

```bash
# Server phải đang chạy
curl -s "http://localhost:8000/github/runs?branch=main&status=completed" | python -m json.tool
```

### Dùng GitHub API trực tiếp

```bash
GITHUB_TOKEN="<token>"

# Liệt kê runs
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/cochecheee/SAST_CICD/actions/runs?status=completed&per_page=5" \
  | python -m json.tool

# Liệt kê artifacts của run
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/cochecheee/SAST_CICD/actions/runs/23856782093/artifacts" \
  | python -m json.tool
```

---

## 5. Lưu ý

- **128 tests** chạy hoàn toàn với mock — không cần `.env`, không cần network, không tốn GitHub quota.
- **`mcp.db`** được tạo tự động khi server khởi động lần đầu. **`test.db`** được tạo khi chạy pytest. Cả hai đã được `.gitignore`.
- **Webhook auth** dùng `Authorization: Bearer <token>` — phải khớp với `CI_WEBHOOK_TOKEN` trong `.env` và secret `MCP_WEBHOOK_TOKEN` trong GitHub Actions.
- **Artifact filter**: server chỉ xử lý artifacts có tên đúng một trong 6 tên: `spotbugs-report`, `semgrep-report`, `codeql-report`, `dep-check-report`, `trivy-report`, `eslint-report`. Các artifacts khác (như `build-classes`, `gitleaks-results.sarif`) bị bỏ qua.
- **Background poller** chỉ chạy khi `APP_ENV != testing`. Ở `development`, poller tự động poll GitHub mỗi `POLLING_INTERVAL_SECONDS` giây (mặc định 300s) song song với webhook.
- **Swagger UI** đầy đủ tại `http://localhost:8000/docs` — có thể test tất cả endpoints mà không cần curl.
