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

---

## V3.5 — Per-project webhook token (Phase 3)

Trước V3.5, `CI_WEBHOOK_TOKEN` là 1 secret global cho cả instance — CI repo A có thể spoof `body.repository = owner/repo-of-B` để push findings vào project B nếu cùng biết global token. V3.5 đóng lỗ đó:

### Mới — cách auth + routing

1. **Mỗi project có 1 token riêng** lưu trong cột `projects.webhook_token` (Fernet-encrypted khi `FERNET_KEY` set).
2. Owner / admin sinh token qua **`POST /projects/{id}/webhook/rotate`** (response trả plaintext **1 lần duy nhất**).
3. CI dùng token đó trong `Authorization: Bearer ...`. Server match thẳng vào `Project.webhook_token` → biết project nào → bỏ qua `body.repository`.
4. Token cũ bị xoá ngay khi rotate.

### Backward compat

Nếu chưa có project nào rotate token, server vẫn fallback `settings.CI_WEBHOOK_TOKEN` (legacy) + route by `body.repository` như cũ. Deploy lên không cần migration ngay.

### UI flow

`GET /projects/{id}/integration` trả:
- `has_project_token: bool` — đã rotate chưa
- `token_visible: bool` — caller có quyền xem token plaintext không (owner/admin only)
- `webhook_token: str | null` — token thật (chỉ khi token_visible)
- YAML + curl snippet sẵn

Dashboard Settings có nút "Rotate webhook token" cho owner — bấm xong copy token vào GitHub repo secrets.

---

## V3.5 — RBAC audit (Phase 4)

Closes 4 gaps where read endpoints didn't honor per-project membership:

| Endpoint | Trước | Sau |
|---|---|---|
| `GET /stats/overview?project_id=X` | Trả KPI bất kể caller có quyền | 403 khi RBAC on + X ngoài memberships |
| `GET /stats/latest-scan?project_id=X` | Same | Same |
| `GET /monitor/uptime` + `/alerts` | Mở cho mọi caller (kể cả anonymous) | `require_read_access` + scope theo memberships |
| `GET /api/chat/report?project_id=X` | Chỉ check global role | + Membership trên X |
| `GET /findings/{id}` | Chỉ check kill-switch | + Finding→Artifact→Project chain check |

Test coverage: `tests/test_rbac_audit_v35.py` (8 case).
