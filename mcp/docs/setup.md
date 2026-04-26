# Hướng dẫn Setup Môi Trường — MCP Gateway

> Tài liệu này hướng dẫn từng bước setup hoàn chỉnh từ máy tính trắng đến server đang chạy và nhận webhook từ CI pipeline.

## Mục lục
1. [Cài đặt Python](#1-cài-đặt-python)
2. [Clone repo & tạo Python env](#2-clone-repo--tạo-python-env)
3. [Cấu hình biến môi trường (.env)](#3-cấu-hình-biến-môi-trường-env)
4. [Lấy GitHub Personal Access Token](#4-lấy-github-personal-access-token)
5. [Lấy Gemini API Key](#5-lấy-gemini-api-key)
6. [Lấy URL public cho MCP Gateway (MCP_GATEWAY_URL)](#6-lấy-url-public-cho-mcp-gateway-mcp_gateway_url)
7. [Cấu hình CI_WEBHOOK_TOKEN](#7-cấu-hình-ci_webhook_token)
8. [Chạy server](#8-chạy-server)
9. [Chạy tests](#9-chạy-tests)
10. [Checklist xác nhận end-to-end](#10-checklist-xác-nhận-end-to-end)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Cài đặt Python

> Bỏ qua nếu đã có Python 3.11+. Kiểm tra bằng: `python --version`

### Windows

**Cách 1 — Microsoft Store (đơn giản nhất):**
1. Mở Microsoft Store → tìm **Python 3.13** → Install

**Cách 2 — winget:**
```bash
winget install Python.Python.3.13
```

**Cách 3 — Tải trực tiếp:**
1. Vào [python.org/downloads](https://www.python.org/downloads/)
2. Tải bản **3.13.x** (Windows installer 64-bit)
3. Chạy installer — **TICK vào "Add Python to PATH"** trước khi nhấn Install

**Xác nhận sau khi cài:**
```bash
# Mở terminal mới (Git Bash hoặc PowerShell)
python --version
# Output: Python 3.13.x

pip --version
# Output: pip 24.x from ...
```

> **Lưu ý Windows:** Nếu `python` không nhận, thử `python3` hoặc `py`. Nếu vẫn không được, kiểm tra PATH trong System Environment Variables.

---

## 2. Clone repo & tạo Python env

### Bước 1 — Clone repo

```bash
git clone https://github.com/cochecheee/chat-system.git
cd chat-system/mcp
```

Nếu đã có repo, chỉ cần vào đúng thư mục:
```bash
cd /d/School/DoAnTotNghiep/chat-system/mcp
```

### Bước 2 — Tạo virtual environment

Virtual environment giúp cô lập dependencies, không ảnh hưởng Python system.

```bash
# Đứng trong thư mục mcp/
python -m venv .venv
```

Kiểm tra tạo thành công:
```bash
ls .venv/Scripts/    # Windows — phải thấy activate, python.exe, pip.exe
ls .venv/bin/        # macOS/Linux
```

### Bước 3 — Kích hoạt venv

```bash
# Git Bash (Windows):
source .venv/Scripts/activate

# PowerShell (Windows):
.venv\Scripts\Activate.ps1

# macOS / Linux:
source .venv/bin/activate
```

Sau khi activate, terminal sẽ hiện prefix `(.venv)`:
```
(.venv) user@machine /d/School/.../mcp $
```

> **Quan trọng:** Mỗi lần mở terminal mới phải activate lại. Nếu thấy `ModuleNotFoundError`, 99% là chưa activate.

### Bước 4 — Cài dependencies

```bash
pip install -r requirements.txt
```

Quá trình này mất 1-3 phút lần đầu. Output cuối cùng phải là:
```
Successfully installed fastapi-... uvicorn-... sqlalchemy-... ...
```

### Bước 5 — Xác nhận cài đặt

```bash
python -c "
import fastapi, sqlalchemy, httpx
from google import genai
from sarif_pydantic import Sarif
import cwe2, defusedxml
print('Tất cả dependencies OK')
"
```

---

## 3. Cấu hình biến môi trường (.env)

### Bước 1 — Tạo file .env

```bash
# Đứng trong mcp/
cp .env.example .env
```

### Bước 2 — Mở và điền .env

Mở file `.env` bằng bất kỳ text editor nào. Dưới đây là giải thích từng biến:

```env
# =============================================================================
# DATABASE
# =============================================================================

# SQLite — tự tạo tại mcp/mcp.db khi server start lần đầu.
# Không cần thay đổi trừ khi muốn đặt DB ở chỗ khác.
DATABASE_URL=sqlite+aiosqlite:///./mcp.db


# =============================================================================
# GITHUB (BẮT BUỘC — cần để fetch CI artifacts)
# =============================================================================

# Personal Access Token — xem Mục 4 để biết cách lấy
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Username GitHub của bạn (owner của repo SAST_CICD)
GITHUB_OWNER=cochecheee

# Tên repo Java target có CI pipeline
# LƯU Ý: Đây là SAST_CICD, KHÔNG phải chat-system
GITHUB_REPO=SAST_CICD


# =============================================================================
# POLLING — MCP tự động poll GitHub để tìm CI run mới
# =============================================================================

# Thời gian giữa 2 lần poll (giây). Default 300 = 5 phút.
# Giảm xuống 60 để test nhanh hơn, tăng lên nếu lo ngại rate limit.
POLLING_INTERVAL_SECONDS=300

# Phải khớp CHÍNH XÁC với field `name:` ở đầu file ci.yml trong SAST_CICD.
# Sai 1 ký tự cũng không tìm được run.
# Kiểm tra: xem Mục 11 (Troubleshooting) nếu poller không tìm được run.
POLLING_WORKFLOW_NAME=CI Workflow

# Branch cần poll. Thường là main hoặc master.
POLLING_BRANCH=main


# =============================================================================
# GEMINI AI (BẮT BUỘC cho Phase 3 — AI Analysis)
# Để trống nếu chưa implement Phase 3, server vẫn chạy bình thường.
# =============================================================================

# API Key từ Google AI Studio — xem Mục 5
GEMINI_API_KEY=AIzaSy_xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Model. gemini-2.5-flash: nhanh + rẻ. gemini-2.5-pro: chậm hơn nhưng chính xác hơn.
GEMINI_MODEL=gemini-2.5-flash

# Số lần retry khi gặp lỗi 429 (quota) hoặc 503 (server error)
GEMINI_MAX_RETRIES=3


# =============================================================================
# AUTH — Bảo mật các endpoints
# =============================================================================

# JWT secret key dùng để ký tokens cho Dashboard.
# PHẢI thay đổi — không dùng giá trị mặc định trong production.
# Generate ngẫu nhiên: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=change-me-to-a-random-string-of-at-least-32-chars

# Thời gian JWT token tồn tại (phút). 480 = 8 giờ.
ACCESS_TOKEN_EXPIRE_MINUTES=480

# API Key cho CI/CD pipeline khi gọi POST /artifacts/process.
# Để TRỐNG khi dev local (tắt auth).
# Nếu set, request phải có header: X-API-Key: <giá trị này>
CI_API_KEY=

# Token xác thực webhook từ CI pipeline.
# Phải khớp với GitHub Secret MCP_WEBHOOK_TOKEN trong repo SAST_CICD.
# Để TRỐNG khi dev local (tắt auth webhook).
# Xem Mục 7 để tạo và cấu hình đầy đủ.
CI_WEBHOOK_TOKEN=


# =============================================================================
# APP
# =============================================================================

# Môi trường chạy:
#   development — SQLAlchemy in SQL ra console, CORS allow *
#   production  — CORS strict, không echo SQL
#   testing     — poller tắt (dùng tự động bởi pytest, không cần set tay)
APP_ENV=development
```

### Bước 3 — Generate SECRET_KEY

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Output ví dụ: a3f8c2e1d4b7e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4
```

Copy output → paste vào `SECRET_KEY=` trong .env.

---

## 4. Lấy GitHub Personal Access Token

MCP Gateway dùng PAT để download artifacts từ GitHub Actions.

### Bước 1 — Tạo PAT

1. Đăng nhập [github.com](https://github.com)
2. Click **avatar** góc trên phải → **Settings**
3. Kéo xuống cuối sidebar trái → **Developer settings**
4. Chọn **Personal access tokens** → **Tokens (classic)**
5. Click **Generate new token** → **Generate new token (classic)**
6. Điền form:
   - **Note:** `MCP Gateway - SAST_CICD`
   - **Expiration:** `90 days` (hoặc `No expiration` cho dev)
   - **Scopes — chọn các mục sau:**
     - ✅ `repo` → Full control of private repositories
       *(nếu SAST_CICD là public repo, chỉ cần `public_repo`)*
     - ✅ `workflow` → Update GitHub Action workflows
     - ✅ `read:org` → Read org and team membership *(nếu repo thuộc org)*
7. Kéo xuống → Click **Generate token**
8. **Copy token ngay** — GitHub chỉ hiện 1 lần, sau đó không xem lại được

Token có dạng: `ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### Bước 2 — Điền vào .env

```env
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GITHUB_OWNER=cochecheee
GITHUB_REPO=SAST_CICD
```

### Bước 3 — Xác nhận token hoạt động

```bash
# Thay ghp_xxx bằng token thật
curl -s -H "Authorization: Bearer ghp_xxx" \
  https://api.github.com/repos/cochecheee/SAST_CICD/actions/artifacts?per_page=1 \
  | python -m json.tool | head -5
```

Kết quả kỳ vọng — phải thấy `"total_count"`:
```json
{
    "total_count": 47,
    "artifacts": [...]
}
```

Nếu thấy `"message": "Bad credentials"` → token sai. Nếu thấy `"message": "Not Found"` → GITHUB_OWNER hoặc GITHUB_REPO sai.

---

## 5. Lấy Gemini API Key

> Chỉ cần cho Phase 3 (AI Analysis). Server chạy bình thường không có key này.

### Bước 1 — Tạo API Key

1. Truy cập [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Đăng nhập Google Account
3. Click **Create API key**
4. Chọn project Google Cloud (hoặc click **Create API key in new project**)
5. Copy key

Key có dạng: `AIzaSy_xxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### Bước 2 — Điền vào .env

```env
GEMINI_API_KEY=AIzaSy_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
GEMINI_MODEL=gemini-2.5-flash
GEMINI_MAX_RETRIES=3
```

### Bước 3 — Xác nhận key hoạt động

```bash
# Thay AIzaSy_xxx bằng key thật
python -c "
from google import genai
client = genai.Client(api_key='AIzaSy_xxx')
response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Say hello in one word'
)
print('Gemini OK:', response.text.strip())
"
```

Kết quả kỳ vọng: `Gemini OK: Hello`

---

## 6. Lấy URL public cho MCP Gateway (MCP_GATEWAY_URL)

CI pipeline (SAST_CICD) gọi về MCP Gateway qua internet sau mỗi lần chạy. MCP cần có URL public ổn định để nhận webhook.

Có 2 lựa chọn miễn phí:

---

### Lựa chọn A — ngrok Static Domain *(khuyến nghị khi dev)*

ngrok cho **1 static domain miễn phí** per account. URL không thay đổi dù restart ngrok nhiều lần.

#### A1 — Tạo tài khoản ngrok

1. Vào [ngrok.com](https://ngrok.com) → **Sign up** (miễn phí)
2. Có thể đăng nhập bằng Google/GitHub

#### A2 — Cài ngrok trên Windows

**Cách 1 — Scoop** *(tự quản lý PATH, khuyến nghị):*
```bash
# Cài Scoop nếu chưa có (chạy trong PowerShell, không phải Git Bash)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
irm get.scoop.sh | iex

# Sau đó cài ngrok (có thể dùng Git Bash)
scoop install ngrok
```

**Cách 2 — Download thủ công** *(đơn giản, không cần thêm tool):*

1. Vào [ngrok.com/download](https://ngrok.com/download) → chọn **Windows (AMD64)**
2. Giải nén → được file `ngrok.exe`
3. Tạo thư mục và đặt ngrok vào:
   ```bash
   mkdir -p /c/tools/ngrok
   cp /c/Users/<username>/Downloads/ngrok.exe /c/tools/ngrok/
   ```
4. Thêm vào PATH vĩnh viễn:
   ```bash
   echo 'export PATH=$PATH:/c/tools/ngrok' >> ~/.bashrc
   source ~/.bashrc
   ```
5. Hoặc thêm qua Windows GUI:
   - Windows Search → **"Edit the system environment variables"**
   - Click **Environment Variables...**
   - Trong **User variables** → chọn `Path` → **Edit** → **New**
   - Nhập: `C:\tools\ngrok`
   - OK → OK → OK
   - Mở terminal **mới**

**Cách 3 — winget** *(nếu winget available):*
```bash
winget install ngrok
# Sau đó mở terminal mới — winget cập nhật PATH nhưng cần terminal mới
```

**Xác nhận cài thành công:**
```bash
ngrok version
# Output: ngrok version 3.x.x
```

#### A3 — Đăng nhập ngrok với authtoken

1. Vào [dashboard.ngrok.com](https://dashboard.ngrok.com) → **Your Authtoken** (sidebar trái)
2. Copy authtoken (dạng: `2abc...xyz_...`)
3. Chạy:
   ```bash
   ngrok config add-authtoken 2abc...xyz_...
   ```
   Output: `Authtoken saved to configuration file: /c/Users/<user>/.config/ngrok/ngrok.yml`

#### A4 — Lấy Static Domain miễn phí

1. Vào [dashboard.ngrok.com/domains](https://dashboard.ngrok.com/domains)
2. Click **+ New Domain**
3. ngrok tạo cho bạn 1 domain ngẫu nhiên dạng: `funny-word-12345.ngrok-free.app`
4. Copy domain này — đây là URL cố định của bạn

#### A5 — Chạy ngrok

Mỗi lần dev, mở **2 terminal**:

**Terminal 1 — MCP Gateway:**
```bash
cd /d/School/DoAnTotNghiep/chat-system/mcp
source .venv/Scripts/activate
uvicorn src.main:app --reload
```

**Terminal 2 — ngrok:**
```bash
ngrok http --domain=funny-word-12345.ngrok-free.app 8000
```

Output của ngrok khi chạy thành công:
```
Session Status    online
Account           cochecheee (Plan: Free)
Version           3.x.x
Region            Asia Pacific (ap)
Forwarding        https://funny-word-12345.ngrok-free.app -> http://localhost:8000
```

**URL public của bạn:** `https://funny-word-12345.ngrok-free.app`

#### A6 — Xác nhận ngrok hoạt động

```bash
curl https://funny-word-12345.ngrok-free.app/health
# Expected: {"status":"healthy"}
```

> **Hạn chế:** MCP chỉ nhận được webhook khi máy tính đang bật, venv đang active, uvicorn đang chạy, và ngrok đang chạy. Phù hợp cho dev/test, không phù hợp để demo liên tục.

---

### Lựa chọn B — Deploy lên Render *(khuyến nghị khi demo đồ án)*

Render là platform mà CI của bạn đã deploy Java app. Deploy MCP Gateway lên đây cho URL luôn online, không cần máy tính bật.

#### B1 — Tạo Dockerfile

Tạo file `mcp/Dockerfile`:

```dockerfile
FROM python:3.13-slim

WORKDIR /app

# Cài dependencies trước (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### B2 — Đảm bảo .dockerignore

Tạo `mcp/.dockerignore` để không copy file thừa vào image:

```
.venv/
.env
__pycache__/
*.pyc
*.db
.pytest_cache/
```

#### B3 — Commit và push

```bash
cd /d/School/DoAnTotNghiep/chat-system
git add mcp/Dockerfile mcp/.dockerignore
git commit -m "Add Dockerfile for Render deployment"
git push
```

#### B4 — Tạo Web Service trên Render

1. Vào [render.com](https://render.com) → Đăng nhập
2. Click **New +** → **Web Service**
3. Chọn **Build and deploy from a Git repository** → Connect GitHub
4. Tìm repo `chat-system` → Connect
5. Cấu hình service:
   - **Name:** `mcp-gateway`
   - **Region:** Singapore (gần nhất với VN)
   - **Branch:** `master` hoặc `main`
   - **Root Directory:** `mcp`
   - **Runtime:** `Docker`
   - **Instance Type:** `Free`
6. Click **Create Web Service**

Render sẽ tự build Docker image và deploy. Đợi 3-5 phút.

URL public sau khi deploy: `https://mcp-gateway-xxxx.onrender.com`

#### B5 — Thêm Environment Variables trên Render

Vào service dashboard → tab **Environment** → **Add Environment Variable** cho từng biến:

| Key | Value | Ghi chú |
|---|---|---|
| `APP_ENV` | `production` | Bắt buộc |
| `DATABASE_URL` | `sqlite+aiosqlite:///./mcp.db` | Bắt buộc |
| `GITHUB_TOKEN` | `ghp_xxx` | Bắt buộc |
| `GITHUB_OWNER` | `cochecheee` | Bắt buộc |
| `GITHUB_REPO` | `SAST_CICD` | Bắt buộc |
| `SECRET_KEY` | `<random 32 chars>` | Bắt buộc |
| `CI_WEBHOOK_TOKEN` | `<giá trị từ Mục 7>` | Bắt buộc |
| `POLLING_WORKFLOW_NAME` | `CI Workflow` | Bắt buộc |
| `GEMINI_API_KEY` | `AIzaSy_xxx` | Khi implement Phase 3 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Khi implement Phase 3 |

Sau khi thêm biến → Render tự redeploy.

#### B6 — Xác nhận Render deploy thành công

```bash
curl https://mcp-gateway-xxxx.onrender.com/health
# Expected: {"status":"healthy"}
```

> **Lưu ý free tier:** Service sleep sau 15 phút không có traffic. Lần đầu wake up mất ~30-50 giây. Webhook từ CI sẽ tự wake up. Nếu cần luôn online → nâng **Starter plan ($7/tháng)**.

---

### So sánh 2 lựa chọn

| Tiêu chí | ngrok Static | Render Free |
|---|---|---|
| Thời gian setup | ~10 phút | ~25 phút |
| Luôn online | Không (cần máy bật) | Gần như có (sleep 15 phút) |
| Chi phí | Miễn phí | Miễn phí |
| URL ổn định | Có (static domain) | Có |
| Phù hợp cho | Phát triển hàng ngày | Demo / báo cáo đồ án |
| Dữ liệu DB | Tồn tại lâu dài | Reset khi redeploy |

**Khuyến nghị thực tế:**
- Dùng **ngrok** khi code và test hàng ngày
- Switch sang **Render** 1-2 ngày trước khi demo đồ án

---

## 7. Cấu hình CI_WEBHOOK_TOKEN

Đây là bước kết nối CI pipeline với MCP Gateway. Sau mỗi CI run thành công, pipeline tự động POST về MCP để xử lý artifacts ngay — thay vì chờ poller poll sau 5 phút.

### Luồng hoạt động

```
GitHub Actions (SAST_CICD repo)
  └─ job: notify
       └─ step: Dispatch to MCP Gateway
            POST /webhook/pipeline-complete
            Header: Authorization: Bearer <MCP_WEBHOOK_TOKEN>
            Body: run-metadata.json
                  {
                    "run_id": 12345678,
                    "pipeline_status": "success",
                    "repository": "cochecheee/SAST_CICD",
                    ...
                  }
                         │
                         ▼
MCP Gateway
  └─ POST /webhook/pipeline-complete
       1. Verify token
       2. Tìm/tạo Project trong DB
       3. Background: fetch 6 security artifacts
       4. Parse → scrub → normalize → enrich → lưu DB
       5. Findings sẵn sàng để xem qua GET /findings
```

### Bước 1 — Tạo shared secret token

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Ví dụ output: xK9mN2pQ7rL4wE8tY1vA5uB3cD6jF0hG_abc123
```

Lưu token này — cần dùng ở cả 2 nơi bên dưới.

### Bước 2 — Điền token vào mcp/.env

```env
CI_WEBHOOK_TOKEN=xK9mN2pQ7rL4wE8tY1vA5uB3cD6jF0hG_abc123
```

### Bước 3 — Thêm 2 secrets vào GitHub Actions (repo SAST_CICD)

Vào **github.com/cochecheee/SAST_CICD** → **Settings** → **Secrets and variables** → **Actions**

**Secret 1:**
- Click **New repository secret**
- Name: `MCP_WEBHOOK_TOKEN`
- Value: `xK9mN2pQ7rL4wE8tY1vA5uB3cD6jF0hG_abc123` *(cùng giá trị với .env)*
- Click **Add secret**

**Secret 2:**
- Click **New repository secret**
- Name: `MCP_GATEWAY_URL`
- Value: URL từ **Mục 6**
  - ngrok: `https://funny-word-12345.ngrok-free.app`
  - Render: `https://mcp-gateway-xxxx.onrender.com`
- Click **Add secret**

### Bước 4 — Xác nhận ci.yml đã có bước dispatch

Mở file `.github/workflows/ci.yml` trong repo **SAST_CICD**. Tìm job `notify`, xác nhận có bước:

```yaml
- name: Dispatch to MCP Gateway
  env:
    MCP_GATEWAY_URL:   ${{ secrets.MCP_GATEWAY_URL }}
    MCP_WEBHOOK_TOKEN: ${{ secrets.MCP_WEBHOOK_TOKEN }}
  run: |
    curl -f -s -X POST "${MCP_GATEWAY_URL}/webhook/pipeline-complete" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${MCP_WEBHOOK_TOKEN}" \
      --max-time 20 \
      -d @run-metadata.json
```

> Endpoint phải là `/webhook/pipeline-complete` với `Authorization: Bearer`, không phải `X-Webhook-Token`.

### Bước 5 — Test webhook thủ công

```bash
# Không có token (CI_WEBHOOK_TOKEN trống trong .env — dev mode)
curl -s -X POST http://localhost:8000/webhook/pipeline-complete \
  -H "Content-Type: application/json" \
  -d '{"run_id": 12345, "pipeline_status": "success"}' \
  | python -m json.tool
```

Kết quả kỳ vọng:
```json
{
    "status": "accepted",
    "run_id": 12345,
    "project_id": 1
}
```

```bash
# Có token (giống như CI gửi thật)
curl -s -X POST http://localhost:8000/webhook/pipeline-complete \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer xK9mN2pQ7rL4wE8tY1vA5uB3cD6jF0hG_abc123" \
  -d '{"run_id": 12345, "pipeline_status": "success"}' \
  | python -m json.tool
```

### Bước 6 — Test qua ngrok (end-to-end)

Sau khi ngrok đang chạy:

```bash
curl -s -X POST https://funny-word-12345.ngrok-free.app/webhook/pipeline-complete \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer xK9mN2pQ7rL4wE8tY1vA5uB3cD6jF0hG_abc123" \
  -d '{"run_id": 12345, "pipeline_status": "success"}'
```

Nếu thấy `"status": "accepted"` trong terminal 1 (uvicorn) sẽ có log:
```
INFO: Run 12345: N/6 artifacts are security-relevant
INFO: Stored X findings for artifact ...
```

---

## 8. Chạy server

### Cách thường dùng (development)

```bash
# Bước 1: đi vào đúng thư mục
cd /d/School/DoAnTotNghiep/chat-system/mcp

# Bước 2: activate venv
source .venv/Scripts/activate   # Git Bash
# hoặc
.venv\Scripts\Activate.ps1       # PowerShell

# Bước 3: chạy server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Flag `--reload`: tự restart khi code thay đổi (chỉ dùng khi dev).
Flag `--host 0.0.0.0`: cho phép truy cập từ ngrok / các máy khác trong mạng.

### Logs khi start thành công

```
INFO:     Will watch for changes in these directories: ['/d/.../mcp']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [12345]
INFO:     Started server process [12346]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Poller started — interval=300s workflow='CI Workflow' branch='main'
```

### Các URL sau khi server chạy

| URL | Mô tả |
|---|---|
| http://localhost:8000/health | Health check |
| http://localhost:8000/docs | Swagger UI (test API tương tác) |
| http://localhost:8000/redoc | ReDoc (đọc tài liệu API) |
| http://localhost:8000/projects | Danh sách projects |
| http://localhost:8000/findings | Danh sách findings |
| http://localhost:8000/github/runs | Workflow runs từ GitHub |

---

## 9. Chạy tests

Tests hoàn toàn độc lập — không cần `.env` điền đầy đủ, không call GitHub/Gemini thật, không ảnh hưởng `mcp.db`.

### Chạy tất cả

```bash
cd /d/School/DoAnTotNghiep/chat-system/mcp
source .venv/Scripts/activate

.venv/Scripts/pytest tests/ -v
```

### Chạy nhanh

```bash
.venv/Scripts/pytest tests/ -q
# Expected: 128 passed in ~3s
```

### Chạy từng module

```bash
.venv/Scripts/pytest tests/test_db.py -v                  # DB models, CRUD
.venv/Scripts/pytest tests/test_github_client.py -v       # Artifact download, Zip safety
.venv/Scripts/pytest tests/test_guardrails_scrubbing.py -v # PII scrubbing
.venv/Scripts/pytest tests/test_guardrails_injection.py -v # Injection prevention
.venv/Scripts/pytest tests/test_normalizer.py -v          # SARIF/XML/JSON parsing
.venv/Scripts/pytest tests/test_enricher.py -v            # CWE/OWASP/CVSS enrichment
.venv/Scripts/pytest tests/test_processor.py -v           # End-to-end pipeline
.venv/Scripts/pytest tests/test_poller.py -v              # GitHub polling
.venv/Scripts/pytest tests/test_api_integration.py -v     # REST endpoints + webhook
.venv/Scripts/pytest tests/test_e2e.py -v                 # Full flow
```

### Coverage report

```bash
.venv/Scripts/pytest tests/ --cov=src --cov-report=term-missing
```

---

## 10. Checklist xác nhận end-to-end

Chạy từng bước theo thứ tự. Mỗi bước phải pass trước khi sang bước tiếp.

```bash
# ── Bước 1: Python & dependencies ──────────────────────────────────────
python --version
# Expected: Python 3.11.x hoặc cao hơn

python -c "import fastapi, sqlalchemy, httpx, sarif_pydantic, cwe2; print('deps OK')"
# Expected: deps OK

# ── Bước 2: Tests pass ─────────────────────────────────────────────────
cd /d/School/DoAnTotNghiep/chat-system/mcp
source .venv/Scripts/activate
.venv/Scripts/pytest tests/ -q
# Expected: 128 passed

# ── Bước 3: Server khởi động ───────────────────────────────────────────
# Chạy server trong background để test tiếp
uvicorn src.main:app &
sleep 2

curl -s http://localhost:8000/health
# Expected: {"status":"healthy"}

curl -s http://localhost:8000/ | python -m json.tool
# Expected: {"message":"MCP Gateway","version":"0.2.0","status":"running"}

# ── Bước 4: GitHub token hoạt động ────────────────────────────────────
GITHUB_TOKEN=$(grep '^GITHUB_TOKEN=' .env | cut -d= -f2)
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/cochecheee/SAST_CICD/actions/artifacts?per_page=1 \
  | python -m json.tool | grep total_count
# Expected: "total_count": <số > 0>

# ── Bước 5: Tạo project & xem GitHub runs ─────────────────────────────
curl -s -X POST http://localhost:8000/projects \
  -H "Content-Type: application/json" \
  -d '{"name":"SAST_CICD","github_url":"https://github.com/cochecheee/SAST_CICD"}' \
  | python -m json.tool
# Expected: {"id":1,"name":"SAST_CICD",...}

curl -s "http://localhost:8000/github/runs" | python -m json.tool | head -20
# Expected: list của runs, mỗi run có id, name, conclusion

# ── Bước 6: Webhook nhận được ──────────────────────────────────────────
curl -s -X POST http://localhost:8000/webhook/pipeline-complete \
  -H "Content-Type: application/json" \
  -d '{"run_id": 99999, "pipeline_status": "success"}' \
  | python -m json.tool
# Expected: {"status":"accepted","run_id":99999,"project_id":1}

# ── Bước 7: Findings endpoint hoạt động ───────────────────────────────
curl -s http://localhost:8000/findings | python -m json.tool | head -5
# Expected: [] hoặc list findings

# Tắt server background
kill %1
```

---

## 11. Troubleshooting

### `command not found: python` hoặc `command not found: python3`
Python chưa được thêm vào PATH. Trên Windows, cài lại Python và tick **"Add Python to PATH"** trong installer. Hoặc thêm thủ công: tìm `python.exe` trong `C:\Users\<user>\AppData\Local\Programs\Python\Python313\` và thêm vào PATH.

### `command not found: ngrok`
Ngrok chưa được thêm vào PATH:
```bash
# Tìm ngrok.exe
find "$LOCALAPPDATA" -name "ngrok.exe" 2>/dev/null
find /c/tools -name "ngrok.exe" 2>/dev/null

# Sau khi tìm ra đường dẫn, thêm vào PATH
echo 'export PATH=$PATH:/c/tools/ngrok' >> ~/.bashrc
source ~/.bashrc
```

### `ModuleNotFoundError: No module named 'src'`
Chưa activate venv hoặc chạy sai thư mục:
```bash
# Xác nhận đang ở trong mcp/
pwd  # phải kết thúc bằng .../mcp

# Activate venv
source .venv/Scripts/activate  # Git Bash
# Phải thấy (.venv) ở đầu prompt
```

### `No such table: projects` hoặc `table X has no column Y`
File `mcp.db` cũ từ schema cũ:
```bash
rm mcp.db   # hoặc rm -f mcp.db
# Server sẽ tạo lại DB với schema mới khi khởi động
```

### `HTTPStatusError: 401 Unauthorized` khi fetch GitHub
GitHub token hết hạn hoặc sai scope. Tạo lại PAT theo Mục 4, đảm bảo tick scope `repo` và `workflow`.

### `HTTPStatusError: 403 Forbidden` khi gọi `/artifacts/process`
`CI_API_KEY` đã được set trong `.env`. Thêm header vào request:
```bash
curl -H "X-API-Key: <giá trị CI_API_KEY trong .env>" ...
```
Hoặc đặt `CI_API_KEY=` (trống) khi dev local.

### `403 Invalid or missing webhook token` khi gọi `/webhook/pipeline-complete`
`CI_WEBHOOK_TOKEN` trong `.env` khác với token gửi lên. Kiểm tra:
- Giá trị `CI_WEBHOOK_TOKEN` trong `.env`
- Header đang gửi là `Authorization: Bearer <token>` (không phải `X-Webhook-Token`)
- Giá trị `MCP_WEBHOOK_TOKEN` secret trong GitHub Actions

### Poller khởi động nhưng không tìm thấy run nào
`POLLING_WORKFLOW_NAME` sai — không khớp với tên workflow trong ci.yml:
```bash
# Lấy tên workflow thật từ GitHub API
GITHUB_TOKEN=$(grep '^GITHUB_TOKEN=' .env | cut -d= -f2)
curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
  "https://api.github.com/repos/cochecheee/SAST_CICD/actions/runs?per_page=1" \
  | python -m json.tool | grep '"name"'
```
Copy chính xác giá trị `name` vào `POLLING_WORKFLOW_NAME` trong `.env`.

### `[scan] ERROR No plugins to scan with!`
Cảnh báo từ `detect-secrets` khi content quá ngắn. **Không ảnh hưởng pipeline** — artifact vẫn được xử lý bình thường.

### ngrok hiện `ERR_NGROK_8012` hoặc tunnel đã tồn tại
Một session ngrok khác đang dùng domain này. Đóng terminal ngrok cũ hoặc vào [dashboard.ngrok.com/tunnels](https://dashboard.ngrok.com/tunnels) để kill session cũ.

### Render deploy fail — `exec /bin/sh: exec format error`
Dockerfile có vấn đề line ending (Windows CRLF). Fix:
```bash
# Trong thư mục mcp/
sed -i 's/\r//' Dockerfile
```

### Render service sleep, webhook từ CI timeout
Free tier Render sleep sau 15 phút. Khi CI gọi webhook lần đầu sau idle, Render cần 30-50s để wake up. CI dùng `--max-time 20` có thể timeout trước. Giải pháp:
- Tăng `--max-time 60` trong ci.yml
- Hoặc thêm retry: `curl --retry 3 --retry-delay 10`
- Hoặc nâng lên Starter plan
