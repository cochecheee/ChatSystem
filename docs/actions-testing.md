# Testing GitHub Actions — composite + reusable workflow

> Cách verify `actions/*` + `.github/workflows/sast-ci.yml` work end-to-end trước khi pin tag `@v0.2.0`.

3 levels từ cheap → real.

---

## Level 1 — Structural lint (10 giây, local)

```powershell
dev.bat lint
```

(Hoặc trực tiếp: `cd mcp; .venv\Scripts\python -m scripts.lint_workflows`)

Bắt:
- YAML parse error
- Composite action thiếu `runs.using` / `steps[].shell`
- Local action reference `./actions/foo` mà không có `action.yml`
- Workflow thiếu `on:` / `jobs:`

KHÔNG bắt: shell expression bug, input type mismatch (cần `actionlint`).

### Cấp deeper — actionlint (optional, recommend)

Download Windows binary: https://github.com/rhysd/actionlint/releases

```powershell
# Sau khi extract actionlint.exe vào PATH:
cd D:\School\DoAnTotNghiep\chat-system
actionlint
```

Bắt thêm: `${{ }}` syntax errors, shell expression issues, input typing, untrusted ref usage.

---

## Level 2 — Local execution với `act`

[`act`](https://github.com/nektos/act) chạy GitHub Actions local qua Docker.

```powershell
# Cài
choco install act-cli       # hoặc tải release từ GitHub

# Pre-condition: Docker Desktop đang chạy

# Chạy reusable workflow của sample-python local
cd examples\sample-python

# Tạo file secret tạm
@"
MCP_GATEWAY_URL=http://host.docker.internal:8000
MCP_WEBHOOK_TOKEN=test-token
"@ | Set-Content .secrets

act push --workflows .github\workflows\security.yml `
  --secret-file .secrets `
  -P ubuntu-latest=catthehacker/ubuntu:act-latest
```

**Limitation `act`**:
- Không pull reusable workflow từ remote `cocheche/sast-chat/.github/workflows/sast-ci.yml@main` — phải clone chat-system về local + override `uses:` dùng path local `./.github/workflows/sast-ci.yml` (act hỗ trợ relative reference).
- 1 số GitHub-only feature (cache, artifact upload server) sẽ no-op hoặc fail.
- Image `catthehacker/ubuntu:act-latest` nặng (~2 GB) — pull lần đầu chậm.

→ `act` tốt cho debug nhanh khi đang viết action. Real verify dùng Level 3.

---

## Level 3 — Real run trên GitHub Actions (5-10 phút, ground truth)

### Step 1: Push branch chat-system lên GitHub

```powershell
cd D:\School\DoAnTotNghiep\chat-system
git push origin ft/imp-fe
```

(Mày đã có remote `cocheche/sast-chat` chưa? Nếu chưa: `gh repo create cocheche/sast-chat --public --source=. --push --remote=origin`)

### Step 2: Tạo repo sample-python độc lập trên GitHub

```powershell
# Copy examples/sample-python/ ra folder tạm
$dst = "D:\tmp\sast-chat-sample-python"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Recurse -Force examples\sample-python\* $dst

cd $dst
git init
git add .
git commit -m "init: vulnerable Flask sample"

# Tạm chỉnh workflow để point sang branch test thay vì @v0.2.0
$wf = ".github\workflows\security.yml"
(Get-Content $wf) -replace '@main', '@ft/imp-fe' | Set-Content $wf
git add $wf
git commit --amend --no-edit

# Push lên GitHub
gh repo create cocheche/sast-chat-sample-python --public --source=. --push --remote=origin
```

### Step 3: Set GitHub Secrets

Khi chat-system chưa deploy public, dùng giá trị giả để workflow chạy nhưng `notify-dashboard` step sẽ skip với warning (URL trống = OK):

```powershell
gh secret set MCP_GATEWAY_URL    -R cocheche/sast-chat-sample-python --body ""
gh secret set MCP_WEBHOOK_TOKEN  -R cocheche/sast-chat-sample-python --body ""
```

Hoặc nếu mày có ngrok URL public:
```powershell
gh secret set MCP_GATEWAY_URL    -R cocheche/sast-chat-sample-python --body "https://abc.ngrok-free.app"
gh secret set MCP_WEBHOOK_TOKEN  -R cocheche/sast-chat-sample-python --body "<token same as chat-system .env>"
```

### Step 4: Trigger workflow + watch

Workflow tự trigger khi push commit. Hoặc manual:

```powershell
cd $dst
gh workflow run security.yml
gh run watch
```

### Step 5: Verify expected

Mong đợi:
- `actions/sast-suite` step chạy 4 tools (Semgrep + Trivy + Bandit + Safety) cho language=python
- Mỗi tool xuất file vào `reports/`
- Artifact `sast-reports-<run_number>` upload lên GitHub
- `actions/notify-dashboard` step:
  - URL trống → log warning "skipping notify"
  - URL có giá trị → POST 202 (nếu chat-system up) hoặc warning HTTP code khác
- Job overall: ✅ green

Nếu fail, check log của step nào:
```powershell
gh run view --log-failed
```

### Step 6: Cleanup khi xong test

```powershell
# Repo sample-python: giữ làm demo lâu dài hoặc xoá
gh repo delete cocheche/sast-chat-sample-python --yes

# Branch test trong sample-python: revert @ft/imp-fe → @v0.2.0 sau khi tag
```

---

## Tag `@v0.2.0` chính thức (sau khi Level 3 pass)

```powershell
cd D:\School\DoAnTotNghiep\chat-system
git tag -a v0.2.0 -m "v0.2.0 — DevSecOps template (CI + CD + DAST + Monitor)"
git push origin v0.2.0
```

Tag push trigger `.github/workflows/release.yml` → build + push Docker images lên Docker Hub.

Sau đó update sample-python (và bất kỳ inheritor nào) dùng `@v0.2.0`.

---

## Common bug khi viết composite

### `run:` thiếu `shell:`

```yaml
- run: echo hi   # ❌ composite: missing shell
```

Fix:
```yaml
- run: echo hi
  shell: bash
```

`dev.bat lint` bắt được.

### Local action path sai

```yaml
- uses: ./actions/sast-sweet   # ❌ typo, lookup ./actions/sast-sweet/action.yml
```

`dev.bat lint` bắt được.

### Reusable workflow `uses:` ở step thay vì job

```yaml
jobs:
  bad:
    runs-on: ubuntu-latest
    steps:
      - uses: cocheche/sast-chat/.github/workflows/sast-ci.yml@v0.2.0   # ❌ reusable phải ở job-level
```

Đúng:
```yaml
jobs:
  good:
    uses: cocheche/sast-chat/.github/workflows/sast-ci.yml@v0.2.0
    with: ...
```

### Secret name mismatch

GitHub action input vs secret:
```yaml
# inheritor workflow
secrets:
  dashboard_token: ${{ secrets.MCP_WEBHOOK_TOKEN }}
```

`dashboard_token` = key declared trong reusable workflow.
`MCP_WEBHOOK_TOKEN` = tên secret repo.

Sai key dashboard_token vs reusable expectation → workflow fail "secret X is not defined".

---

## Cheat sheet

| Need | Command |
|---|---|
| Quick syntax check | `dev.bat lint` |
| Deep check (need install) | `actionlint` |
| Local run via Docker | `act push --secret-file .secrets` |
| Real run on GitHub | push branch → watch Actions tab |
| Tag release | `git tag v0.2.0 && git push origin v0.2.0` |
