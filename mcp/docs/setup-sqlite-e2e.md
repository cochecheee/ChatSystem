# Chạy end-to-end với SQLite rỗng: import project → thêm pipeline → chạy → đổ artifact

Playbook chạy toàn bộ luồng trên **1 database SQLite trống**, không đụng tới MySQL (XAMPP)
trong `.env` hiện tại. Mọi lệnh dùng **PowerShell** (Windows), chạy từ thư mục `mcp/`.

```
cd D:\School\DoAnTotNghiep\chat-system\mcp
```

Luồng:

```
DB rỗng  →  chạy server (tạo schema + seed user)  →  login lấy JWT
        →  import project (POST /projects → nhận webhook_token + workflow YAML)
        →  thêm pipeline (commit workflow vào repo đích + set secrets)
        →  chạy pipeline  →  webhook đổ artifact  →  findings vào DB  →  verify
```

> **Muốn xem ngay không cần GitHub/CI?** Nhảy xuống [§7 — Đổ dữ liệu offline](#7--đổ-dữ-liệu-offline-không-cần-github).
> Còn muốn đúng luồng thật (artifact do CI sinh ra) thì đi tuần tự §0 → §6.

---

## 0. Trỏ vào SQLite rỗng (không sửa `.env`)

`.env` đang trỏ MySQL. Thay vì sửa file, **override bằng biến môi trường của session** —
pydantic-settings ưu tiên env var hơn `.env`, nên MySQL config giữ nguyên.

```powershell
$env:DATABASE_URL = "sqlite+aiosqlite:///./mcp_empty.db"
$env:SKIP_ALEMBIC = "1"   # DB mới: init_db() create_all() đã dựng đủ schema; bỏ qua Alembic
$env:APP_ENV      = "development"
```

- `mcp_empty.db` được tạo tự động ở `mcp/mcp_empty.db` khi server khởi động lần đầu.
- `SKIP_ALEMBIC=1`: bảng migration Alembic viết cho MySQL/Postgres có thể vấp trên SQLite mới;
  `Base.metadata.create_all()` trong `init_db()` đã tạo đủ bảng nên bỏ qua là an toàn.
- Muốn **làm lại từ đầu**: `Remove-Item .\mcp_empty.db` rồi chạy lại server.

> Cách khác (nếu thích sửa `.env`): comment dòng `DATABASE_URL=mysql+asyncmy://...`
> và thêm `DATABASE_URL=sqlite+aiosqlite:///./mcp_empty.db`.

---

## 1. Cài đặt & chạy server

`.venv` đã có sẵn (`aiosqlite` nằm trong `requirements.txt`). Nếu chưa cài:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Chạy server (giữ nguyên các `$env:` đã set ở §0 trong **cùng** cửa sổ PowerShell này):

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.main:app --reload --port 8000
```

Khi khởi động, server sẽ:
- `init_db()` → tạo toàn bộ bảng trong `mcp_empty.db`.
- Seed user mặc định: tạo tài khoản **`cochecheee`** (role `admin`) với mật khẩu
  `DEFAULT_USER_PASSWORD` (mặc định `changeme123`). Idempotent — không ghi đè nếu đã có.

Kiểm tra sống:
```powershell
curl.exe http://localhost:8000/health
# {"status":"healthy"}
```
Swagger UI để bấm thử mọi endpoint: **http://localhost:8000/docs**

> Mở **cửa sổ PowerShell thứ 2** cho các bước gọi API bên dưới (server giữ chạy ở cửa sổ 1).

---

## 2. Login lấy JWT

RBAC đang bật (`RBAC_PER_PROJECT=true`, `ANONYMOUS_READ_ENABLED=false`) nên mọi API đọc/ghi
cần JWT. Tài khoản `cochecheee` là `admin` → bỏ qua mọi kiểm tra per-project.

```powershell
$base  = "http://localhost:8000"
$login = Invoke-RestMethod -Method Post -Uri "$base/api/chat/auth/token" `
  -ContentType "application/json" `
  -Body (@{ username = "cochecheee"; password = "changeme123" } | ConvertTo-Json)

$token = $login.access_token
$H = @{ Authorization = "Bearer $token" }
$token
```

> Nếu bạn set `DEFAULT_USER_PASSWORD` khác trong `.env`/env var thì dùng đúng mật khẩu đó.
> Login sai → `401 Sai tên đăng nhập hoặc mật khẩu`.

---

## 3. Import project (`POST /projects`)

Tạo project **kèm `github_owner` + `github_repo` thật** — bước "chạy" (§5) cần chúng để
`process_run` fetch artifact từ đúng repo. Response trả về **gói tích hợp one-time**:
`webhook_token` (plaintext, chỉ hiện 1 lần) + `workflow_yaml` để dán vào repo đích.

```powershell
$body = @{
  name         = "demo-sqlite"
  github_url   = "https://github.com/cochecheee/sample-python"
  github_owner = "cochecheee"
  github_repo  = "sample-python"
  language     = "python"          # java|python|node|go — chỉ để render snippet
} | ConvertTo-Json

$proj = Invoke-RestMethod -Method Post -Uri "$base/projects" -Headers $H `
  -ContentType "application/json" -Body $body

$projectId    = $proj.id
$webhookToken = $proj.integration.webhook_token
"project_id   = $projectId"
"webhook_token= $webhookToken"      # LƯU LẠI — sau bước này API không trả token nữa

# Xem file workflow đã điền sẵn project_id để dán vào repo đích:
$proj.integration.workflow_yaml
```

Người tạo (`cochecheee`) tự động thành **owner** của project. Nếu lỡ mất `webhook_token`:
`POST /projects/$projectId/webhook/rotate` (owner/admin) để sinh token mới.

Xác nhận project đã vào DB:
```powershell
Invoke-RestMethod -Uri "$base/projects" -Headers $H | Format-Table id, name, github_owner, github_repo
```

---

## 4. Thêm pipeline vào repo đích

Lấy nội dung `workflow_yaml` ở §3, commit vào repo đích tại
`.github/workflows/security.yml`. Nó gọi reusable workflow SAST và bắn webhook về chat-system:

```powershell
$proj.integration.workflow_yaml | Out-File -Encoding utf8 .\security.yml
# → copy .\security.yml vào <repo-đích>/.github/workflows/security.yml rồi commit/push
```

Trong **repo đích** (GitHub → Settings → Secrets and variables → Actions), thêm 2 secret
(giá trị lấy từ `$proj.integration.secrets_to_set`):

| Secret | Giá trị |
|---|---|
| `MCP_GATEWAY_URL` | URL công khai của chat-system (vd ngrok/Render). **Local `localhost:8000` GitHub không gọi tới được** — xem ghi chú dưới. |
| `MCP_WEBHOOK_TOKEN` | `webhook_token` ở §3 |

> **Local dev:** GitHub Actions không truy cập được `localhost`. Muốn CI thật bắn webhook về máy,
> expose server qua tunnel: `ngrok http 8000` rồi set `MCP_GATEWAY_URL = https://<subdomain>.ngrok.app`.
> Nếu không muốn dựng tunnel, dùng **§5B** (tự bắn webhook) hoặc **§7** (đổ offline).

---

## 5. Chạy pipeline & đổ artifact

Pipeline phải sinh artifact tên khớp profile `github-actions-default` (vd `sast-reports-*`)
thì `process_run` mới nhặt. Có 3 cách kích hoạt ingest:

### 5A. Luồng CI thật (tự động)
Push code / `workflow_dispatch` ở repo đích → GitHub Actions chạy SAST → upload artifact →
step "Notify chat-system" gọi `POST /webhook/pipeline-complete`. Server nhận webhook →
`process_run(project_id, run_id)` → fetch artifact từ GitHub → chuẩn hoá → **đổ findings vào DB**.
(Cần `MCP_GATEWAY_URL` tới được server — xem ghi chú §4.)

### 5B. Tự bắn webhook cho 1 run có sẵn (không cần tunnel)
Nếu repo đã có **run hoàn tất kèm artifact bảo mật**, lấy `run_id` rồi tự POST webhook.
Auth bằng `webhook_token` per-project (§3):

```powershell
# Tìm run gần đây của project (proxy live sang GitHub — cần GITHUB_TOKEN trong .env):
Invoke-RestMethod -Uri "$base/github/runs?project_id=$projectId" -Headers $H |
  Select-Object -First 5 id, name, status, conclusion, head_branch

$runId = 1234567890   # ← điền id từ danh sách trên

Invoke-RestMethod -Method Post -Uri "$base/webhook/pipeline-complete" `
  -Headers @{ Authorization = "Bearer $webhookToken" } `
  -ContentType "application/json" `
  -Body (@{ run_id = $runId; pipeline_status = "passed" } | ConvertTo-Json)
# → {"status":"accepted","project_id":...,"auth_mode":"bearer_per_project",...}
```

Việc ingest chạy nền (BackgroundTask). Đợi vài giây rồi verify ở §6.

### 5C. Nạp thẳng 1 artifact theo id
`CI_API_KEY` để trống ở dev nên endpoint mở. Cần `github_artifact_id` thật:

```powershell
Invoke-RestMethod -Uri "$base/github/runs/$runId/artifacts" -Headers $H |
  Format-Table id, name, size_in_bytes
$artifactId = 111111111   # ← id artifact bảo mật (vd sast-reports-...)

Invoke-RestMethod -Method Post -Uri "$base/artifacts/process" `
  -ContentType "application/json" `
  -Body (@{ github_artifact_id = $artifactId; project_id = $projectId } | ConvertTo-Json)
# → {"message":"Processing started","db_artifact_id":...,"status":"pending"}
```

> **5B/5C đều cần GitHub thật** (`GITHUB_TOKEN` trong `.env` + repo có artifact). Muốn hoàn
> toàn không phụ thuộc GitHub thì dùng §7.

---

## 6. Verify — findings đã đổ vào DB chưa

```powershell
# Đếm + liệt kê findings của project
$r = Invoke-WebRequest -Uri "$base/findings?project_id=$projectId&limit=100" -Headers $H
"Tổng findings (X-Total-Count) = " + $r.Headers['X-Total-Count']
($r.Content | ConvertFrom-Json) | Select-Object -First 10 tool, severity, rule_id, file_path, status

# KPI tổng quan của project
Invoke-RestMethod -Uri "$base/stats/overview?project_id=$projectId" -Headers $H

# Kết quả cổng chặn (gate) theo severity
Invoke-RestMethod -Uri "$base/findings/gate-count?project_id=$projectId" -Headers $H
```

Có findings trả về = artifact đã được **fetch → chuẩn hoá → dedup → lưu** thành công.

---

## 7. Đổ dữ liệu offline (không cần GitHub)

Muốn thấy toàn bộ pipeline **Chuẩn hoá → Dedup → AI FP** trên DB SQLite rỗng mà **không**
dựng CI hay gọi GitHub: chạy script seed. Nó tạo project `demo-xu-ly-du-lieu`, chèn ~40 finding
đa-tool (có nhóm trùng để dedup), rồi chạy **`SecurityProcessor._correlate_run_findings` thật**.

```powershell
# vẫn giữ $env:DATABASE_URL trỏ mcp_empty.db (§0)
.\.venv\Scripts\python.exe -m scripts.seed_demo_processing
```

Sau đó login (§2), tìm project `demo-xu-ly-du-lieu` trong `GET /projects`, và verify như §6.
Script **idempotent** — chạy lại sẽ wipe findings cũ của đúng project demo rồi seed lại.

---

## 8. Reset về trạng thái sạch

```powershell
# Wipe findings + artifacts, GIỮ lại projects (dry-run trước, --apply để xoá thật)
.\.venv\Scripts\python.exe -m scripts.reset_db
.\.venv\Scripts\python.exe -m scripts.reset_db --apply

# Hoặc xoá sạch hoàn toàn: dừng server, xoá file DB rồi chạy lại
Remove-Item .\mcp_empty.db
```

---

## Tham chiếu endpoint

| Bước | Method & path | Auth |
|---|---|---|
| Login | `POST /api/chat/auth/token` | — (trả JWT) |
| Import project | `POST /projects` | Bearer JWT |
| List projects | `GET /projects` | Bearer JWT |
| Rotate webhook token | `POST /projects/{id}/webhook/rotate` | JWT (owner/admin) |
| Webhook CI | `POST /webhook/pipeline-complete` | Bearer `webhook_token` (per-project) |
| Nạp 1 artifact | `POST /artifacts/process` | `X-API-Key` nếu `CI_API_KEY` set (dev để trống) |
| List GitHub runs | `GET /github/runs?project_id=` | Bearer JWT |
| List artifacts của run | `GET /github/runs/{run_id}/artifacts` | Bearer JWT |
| List findings | `GET /findings?project_id=` | Bearer JWT |
| KPI overview | `GET /stats/overview?project_id=` | Bearer JWT |
| Gate count | `GET /findings/gate-count?project_id=` | Bearer JWT |
| Swagger UI | `GET /docs` | — |

## Biến môi trường quan trọng

| Biến | Giá trị demo | Ý nghĩa |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./mcp_empty.db` | DB SQLite rỗng, tự tạo |
| `SKIP_ALEMBIC` | `1` | Bỏ Alembic trên DB mới (create_all đã đủ) |
| `DEFAULT_USER_PASSWORD` | `changeme123` (mặc định) | Mật khẩu seed cho `cochecheee` |
| `GITHUB_TOKEN` | (trong `.env`) | Cần cho §5A/5B/5C fetch artifact từ GitHub |
| `CI_API_KEY` | (trống) | Trống = `/artifacts/process` mở, không cần key |
| `RBAC_PER_PROJECT` | `true` | Bật → cần JWT; `cochecheee` admin bypass |
