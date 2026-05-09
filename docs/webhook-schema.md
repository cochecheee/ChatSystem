# Webhook Schema — `POST /webhook/pipeline-complete`

> Contract giữa CI pipeline và chat-system MCP Gateway. Mọi project muốn tích hợp với chat-system phải POST đúng schema này.

---

## Overview

Sau khi CI workflow của project hoàn tất, một bước cuối gọi POST đến chat-system để báo "run này xong". Chat-system sẽ:

1. Verify webhook token (header `Authorization: Bearer …`).
2. Resolve `Project` từ DB (theo `GITHUB_OWNER/GITHUB_REPO` hiện tại).
3. Schedule `SecurityProcessor.process_run(project_id, run_id)` chạy nền.
4. Trả `202 Accepted` ngay (không block CI).

Sau đó processor:
- Pull artifacts từ GitHub API.
- Filter theo `artifact_profile` của project (mặc định: 6 SAST + Trivy image scan).
- Normalize → enrich CWE/CVSS/OWASP → store findings.

**Note**: Webhook chỉ là trigger nhanh. Poller (mỗi 5 phút) cũng tự pull các run đã `completed/success` mà chưa được process, nên webhook fail không mất data — chỉ trễ.

---

## Endpoint

```
POST {MCP_GATEWAY_URL}/webhook/pipeline-complete
```

`MCP_GATEWAY_URL` ví dụ: `https://chat-system.example.com` hoặc public tunnel `https://abc123.trycloudflare.com`.

---

## Headers

| Header | Required | Mô tả |
|---|---|---|
| `Content-Type` | ✅ | `application/json` |
| `Authorization` | ⚠️ Conditional | `Bearer {MCP_WEBHOOK_TOKEN}`. Required khi `CI_WEBHOOK_TOKEN` đã set ở chat-system `.env`. Khi `.env` để trống → auth disabled (dev mode). |

---

## Request body

```json
{
  "run_id": 23856782093,
  "run_number": "109",
  "repository": "cochecheee/SAST_CICD",
  "ref": "refs/heads/main",
  "sha": "856928e2adac24423314c98541e253cd2da990af",
  "actor": "cocheche",
  "event": "push",
  "pipeline_status": "passed",
  "timestamp": "2026-05-08T21:30:00Z"
}
```

| Field | Type | Required | Mô tả |
|---|---|---|---|
| `run_id` | integer | ✅ | GitHub Actions run ID. Phải khớp với run đã có artifact upload xong. |
| `pipeline_status` | string | optional | `passed` / `failed` / `gate_failed` / `unknown`. Hiện không filter theo status — chỉ log. |
| Các field khác (`run_number`, `repository`, `sha`, `actor`, `event`, `ref`, `timestamp`) | string | optional | Ignored bởi server. Workflow vẫn nên gửi để debug + future use. |

Pydantic schema dùng `extra="ignore"` → field thừa không gây 422.

---

## Responses

### `202 Accepted` — Success
```json
{
  "status": "accepted",
  "run_id": 23856782093,
  "project_id": 1
}
```

Server đã queue task. Processor chạy nền, không block CI. Verify status sau ở dashboard tab Pipelines.

### `403 Forbidden` — Bad token
```json
{ "detail": "Invalid or missing webhook token" }
```

CI gửi sai `Authorization` header hoặc thiếu nó khi server đã set `CI_WEBHOOK_TOKEN`.

### `422 Unprocessable Entity` — Bad body
```json
{ "detail": [{"loc": ["body", "run_id"], "msg": "field required", "type": "value_error.missing"}] }
```

Body thiếu `run_id` (field bắt buộc duy nhất).

### Network errors

CI nên `continue-on-error: true` cho step gọi webhook — nếu chat-system down, poller vẫn pull được artifact. Webhook chỉ là fast-path.

---

## CI snippet — GitHub Actions

```yaml
- name: Notify chat-system
  if: always()
  env:
    MCP_GATEWAY_URL:   ${{ secrets.MCP_GATEWAY_URL }}
    MCP_WEBHOOK_TOKEN: ${{ secrets.MCP_WEBHOOK_TOKEN }}
  run: |
    if [ -z "${MCP_GATEWAY_URL}" ]; then
      echo "MCP_GATEWAY_URL not set — skipping."
      exit 0
    fi
    cat > run-metadata.json <<EOF
    {
      "run_id": ${{ github.run_id }},
      "run_number": "${{ github.run_number }}",
      "repository": "${{ github.repository }}",
      "ref": "${{ github.ref }}",
      "sha": "${{ github.sha }}",
      "actor": "${{ github.actor }}",
      "event": "${{ github.event_name }}",
      "pipeline_status": "passed",
      "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    }
    EOF
    curl -f -s -X POST "${MCP_GATEWAY_URL}/webhook/pipeline-complete" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${MCP_WEBHOOK_TOKEN}" \
      --max-time 20 \
      -d @run-metadata.json
  continue-on-error: true   # never block CI on dashboard notification failure
```

Sample đầy đủ ở repo demo: `ALOUTE_Spring_Thymeleaf_RCE/.github/workflows/ci.yml` job `notify`.

---

## Manual test

Verify webhook URL/token nhanh từ máy mày:

```bash
curl -i -X POST "${MCP_GATEWAY_URL}/webhook/pipeline-complete" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${MCP_WEBHOOK_TOKEN}" \
  -d '{"run_id": 1, "pipeline_status": "test"}'
```

Mong đợi: `202` + JSON `{"status":"accepted",...}`. Sai token → `403`.

Endpoint `GET /projects/{id}/integration` trả sẵn snippet đã điền URL, secret names, và curl command — copy-paste vào workflow của project mới.

---

## Multi-project (future)

Hiện tại 1 instance chat-system phục vụ 1 project (lấy `GITHUB_OWNER/REPO` từ `.env`). Day 6+ sẽ:

- Webhook accept thêm field `project_id` (hoặc lookup theo `repository` field trong body).
- `Project` đã có sẵn cột credentials per-row (Day 2 scaffolding) — chỉ cần kích hoạt loop ở poller + route webhook đúng project.
