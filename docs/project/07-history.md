# 07 — Lịch sử V2 (chronological)

Tất cả commit ở branch `ft/imp-fe` sau khi `v0.1.0` đóng băng.

## V2.1.1 — Action library split

| Commit | Mô tả |
|---|---|
| `377555e` | Plan: PHASE-V2 — DevSecOps template roadmap |
| `5bfa971` | Refactor monolithic `action.yml` → 3 composite + reusable workflow + inheritor-guide |
| `89cd4aa` | Defer chat-system deploy đến V2.5, chốt deploy shape B1 (2 Web Service) |
| `da68d62` | Rename author "Le Ba Tien Thanh" → "cocheche" trong 7 file |

## V2.1.2 — Python sample

| Commit | Mô tả |
|---|---|
| `f985da4` | Tạo `examples/sample-python/` (Flask vulnerable, 5 lỗ hổng cố ý, Dockerfile, security.yml) |

## V2.1.3 — Test prep

| Commit | Mô tả |
|---|---|
| `3cc26b5` | Add `dev.bat lint` + `mcp/scripts/lint_workflows.py` + `docs/actions-testing.md` (Level 1/2/3 test guide) |

## V2.1.4 — Repo split (3-repo topology)

Chuyển từ monolithic chat-system → 3 repo độc lập.

| Action | Đích |
|---|---|
| Tạo `D:\School\DoAnTotNghiep\sast-action\` | Move actions/, sast-ci.yml, action.yml |
| Tạo `D:\School\DoAnTotNghiep\sample-python\` | Move từ chat-system/examples/sample-python/ |
| Update 24 reference `cochecheee/sast-chat` → `cochecheee/sast-action` | 6 file ở chat-system |

| Commit | Repo | Mô tả |
|---|---|---|
| (initial) | sast-action | First commit của SAST library |
| (initial) | sample-python | First commit Flask vulnerable demo |
| `a679bf1` | chat-system | Delete 11 file đã move + update 24 ref + add render.yaml |

## V2.1.4 — Deploy + iterate fix

Push lên Render free tier rồi fix incrementally.

| Commit | Repo | Mô tả |
|---|---|---|
| `8377d30` | chat-system | Bỏ persistent disk khỏi render.yaml (free tier không hỗ trợ) |
| (push) | sast-action | First push lên `cochecheee/sast-action` master |
| `2e21f6c` | sast-action | Move `dashboard_url` từ inputs → secrets (GitHub cấm `${{ secrets.* }}` trong `with:` của reusable wf caller) |
| (push) | sample-python | First push lên `cochecheee/sample-python` main |
| `db31b9d` | sample-python | Fix: pass `dashboard_url` via secrets block (match contract) |
| `4fd2bb8` | sast-action | Fix 2 parse error: literal `${{ }}` trong description string + bind secret → env để `if:` step truy cập. Pin `safety<3`. |
| `3c290fe` | sample-python | Add `permissions:` block ở workflow level (caller phải explicitly grant) |
| `89b738a` | chat-system | Add prefix `sast-reports-` vào profile + add `CORS_ORIGINS` env cho production |

## V2.1.5 — End-to-end verify

Sau loạt fix trên:
- ✅ sast-action workflow parse OK
- ✅ sample-python CI chạy + notify-dashboard step success (HTTP 202)
- ✅ mcp ingest 1 run, parse 4 SARIF/JSON, lưu finding vào DB
- ✅ Dashboard local fetch được data Render

## V2.2 — CD pipeline (~2 giờ implement, 10 phút setup user)

**Goal**: CI pass → tự build container + push Docker Hub + redeploy Render staging.

| Commit | Repo | Mô tả |
|---|---|---|
| `dbfac87` | sast-action | Add composite `build-image/` (Docker login + buildx + Trivy image scan + push 2 tags) + composite `deploy-staging/` (POST Render Deploy Hook). Extend `sast-ci.yml` với job `cd:` chạy sau `sast:`, 4 input mới (`deploy`, `image_repo`, `dockerfile`, `build_context`), 3 secret mới (`docker_username`, `docker_password`, `render_deploy_hook`). |
| `86abe29` | sample-python | `security.yml` bật `deploy: true`, pass 3 secret Docker + Render. |
| (docs) | chat-system | Update `docs/project/04-deploy.md` thêm "Staging service cho inheritor" section. Update `05-reusable-workflow.md` thêm V2.2 inputs/secrets/example. |

### Manual setup cần làm (user)
1. Docker Hub Access Token
2. Render staging service từ `cochecheee/sample-python:latest` image
3. Copy Deploy Hook URL
4. Add 3 secret vào sample-python GitHub repo

### Defer
- `Deployment` entity ở mcp + `POST /webhook/deployment` route (chưa cần để CD work)
- Dashboard "Deployed" badge

Sẽ làm khi cần show deploy history qua UI. Hiện CD pass/fail xem ở GitHub Actions tab + Render dashboard.

## V2.2 — verification (2026-05-13/14)

Bootstrap manual + 2 lần Flask compat fix:
- `1eb0f66` (sample-python) Pin Flask 1.0 transitive deps
- `86fda08` (sample-python) Python 3.12 → 3.9 (Flask 1.0 needs `collections.MutableMapping`)
- `7e45470` (sample-python) Fix /health route (Flask 1.0 không auto-jsonify dict)

End-to-end verified ở https://sample-python-latest.onrender.com:
- ✅ Image build + push Docker Hub `tienbui482/sample-python:latest`
- ✅ Render auto-pull image + boot
- ✅ /health 200 + vuln endpoints fire correctly
- ✅ CI run #11 → mcp ingest 125 findings (102 trivy + 16 semgrep + 7 bandit)

## V2.3 — DAST + Runtime tab (2026-05-14)

| Commit | Repo | Mô tả |
|---|---|---|
| `e3215be` | sast-action | composite `run-dast/` (OWASP ZAP baseline + full scan + retry cold start) + `cd:` extends sast-ci.yml với 3 input mới (dast, staging_url, dast_scan_type) + DAST job depends on cd. Notify dashboard with pipeline_status=dast_complete. |
| `7845ad0` | sample-python | Enable `dast: true` + staging_url. |
| `1593f0f` | sample-python | Fix `permissions: issues: write` (ZAP action requires nó dù allow_issue_writing=false). |
| `92903a1` | chat-system | mcp `ZapJsonNormalizer` (parses ZAP site/alerts/instances JSON, riskcode → severity mapping) + `DAST_TOOLS` filter ở finding_repo. stats endpoint thêm `dast_open/dast_critical_high`. profile thêm prefix `dast-reports-`. dashboard Runtime tab (Pages/Runtime.tsx). |

End-to-end verified với run #13 (sha 1593f0f):
- ✅ Workflow chạy 3 job (sast + cd + dast)
- ✅ Reprocess pulled cả 3 artifact (sast-reports-13, trivy-image-scan-13, dast-reports-13)
- ✅ mcp ingest 184 findings: 23 SAST + 102 deps + **59 DAST (owasp-zap)**

## V2.4 — Monitor + alert (2026-05-14)

| Commit | Repo | Mô tả |
|---|---|---|
| `a73d460` | chat-system | mcp `UptimeCheck` + `Alert` entities, `monitor.py` background loop (httpx ping every interval, alert raise after threshold consecutive fails, recovered alert when 2xx returns), `smtp_service.py` (gracefully skip if SMTP_HOST empty), Sentry init guarded by SENTRY_DSN, `/monitor/*` API (summary/uptime/alerts/ack/ping). dashboard Monitor page. render.yaml: MONITOR_ENABLED=true + sample-python staging làm default target. |

Verified với manual ping:
- ✅ Background loop ping sample-python staging mỗi 5 phút
- ✅ 8 checks ghi nhận, uptime 75% (cold start 22s gây 2 timeout)
- ✅ /monitor/summary + /alerts endpoints respond đúng schema

Skipped verification (cần config):
- Email send (SMTP_HOST chưa set)
- Sentry capture (SENTRY_DSN chưa set)

## V2.5 — Dashboard Static Site (in progress)

| Commit | Repo | Mô tả |
|---|---|---|
| `8e98a7a` | chat-system | render.yaml thêm service `dashboard` (runtime: static, rootDir: dashboard, buildCommand: npm ci+vite build, staticPublishPath: ./dist, SPA fallback rewrite, security headers, VITE_API_URL pinned). |

Chờ user click **Sync** ở Render Blueprint UI để Render tạo service mới.

## Sub-phase đếm số

```
✅ V2.1.1  Split action → composite + reusable workflow
✅ V2.1.2  Python sample
✅ V2.1.3  Test infra (lint + docs)
✅ V2.1.4  Repo split + Render deploy
✅ V2.1.5  Fix ingest profile + CORS
✅ V2.2    CD: build + push Docker Hub + Render redeploy
✅ V2.3    DAST (OWASP ZAP) + Runtime tab + ZapNormalizer
✅ V2.4    Monitor uptime + alert + email + Sentry
🔄 V2.5    Dashboard Static Site (chờ Render Sync user action)
```

Tổng: 8 milestone done. Tag v0.2.0 chờ V2.5 verified.

## Reference: V1 history

V0.1.0 (defense-ready, 2026-05-08 → 2026-05-09): xem `.planning/redesign/PROGRESS.md` và `CHANGELOG.md` cho chi tiết Day 1-7.

## Commit identity

Local git config ở cả 3 repo:
```
user.name  = cochecheee
user.email = buitien747@gmail.com
```

(Trước 2026-05-13 dùng `tienblt@vng.com.vn` work account → đã switch.)
