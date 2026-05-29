# chat-system — Tài liệu kiến trúc (v2)

> Mục đích: giúp người mới (hoặc chính bạn sau 3 tháng) đọc 30 phút là **nắm
> được kiến trúc, luồng dữ liệu, và biết file nào làm gì** trong repo này.
> Không phải user guide — đây là **engineering map**.

Repo này là một MCP Gateway (FastAPI) + Dashboard (React/Vite) cho pipeline
DevSecOps: SAST/SCA/DAST tools chạy trong GitHub Actions → MCP ingest +
normalize + AI analyze → Dashboard hiển thị + ChatOps để triage.

## Đọc theo thứ tự

| # | File | Bạn sẽ hiểu |
|---|------|-------------|
| 1 | [01-architecture.md](01-architecture.md) | Component map, deployment topology, các V-version đã chồng lên nhau |
| 2 | [02-data-model.md](02-data-model.md) | 8 bảng SQLAlchemy + lý do từng cột, các enum status |
| 3 | [03-backend-flows.md](03-backend-flows.md) | 5 luồng chính: webhook ingest, poller, /explain, /approve, /triage |
| 4 | [04-frontend-flows.md](04-frontend-flows.md) | Routing, state, auth challenge, polling, ProjectContext |
| 5 | [05-api-reference.md](05-api-reference.md) | Bảng endpoint full kèm auth, RBAC, side-effect |
| 6 | [06-runbook.md](06-runbook.md) | Chạy local, common bugs (port 8000 zombie, FERNET_KEY, v.v.) |
| 7 | [07-mysql-migration.md](07-mysql-migration.md) | Kế hoạch chuyển DB SQLite/Postgres → MySQL: driver, type mapping, charset, checklist |

## 30-giây mental model

```
                 GitHub Actions          ← SAST/SCA/DAST chạy ở đây
                       │
       artifacts (SARIF/XML/JSON)
                       │
        ┌──────────────┴──────────────┐
        │ webhook /pipeline-complete  │   ← CI gọi sau khi run xong
        │ HOẶC                        │
        │ poller (mỗi 5 phút)         │   ← MCP tự pull
        └──────────────┬──────────────┘
                       │
            ┌──────────▼──────────┐
            │   SecurityProcessor │   processor.py
            │   ─ fetch artifact  │
            │   ─ scrub PII       │  guardrails.py
            │   ─ normalize       │  normalizer.py (6 tool families)
            │   ─ enrich CWE/CVSS │  enricher.py
            │   ─ dedup hash      │
            │   ─ auto-revoke     │  V3.1 Tier 1+2 (cross-run, rule-based)
            │   ─ store           │
            └──────────┬──────────┘
                       │
                  ┌────▼────┐
                  │ SQLite  │   (Postgres trong prod, Render)
                  │ /Postgres│
                  └────┬────┘
                       │
        ┌──────────────┴───────────────┐
        │  FastAPI routers             │
        │  /findings  /projects        │
        │  /github/runs  /stats        │
        │  /api/chat/*  /monitor       │
        └──────────────┬───────────────┘
                       │ JWT (Bearer)
                       │ + CORS
                       │
                ┌──────▼──────┐
                │  Dashboard  │   React 19 / Vite, 9 tabs
                │   Sidebar   │   Overview · Pipelines · Vulns · SCA ·
                │             │   Runtime · Monitor · Chat · Reports · Settings
                └──────┬──────┘
                       │
                       ▼
                  Gemini API   (qua MCP, không gọi trực tiếp từ FE)
```

## Vocabulary nhanh

| Từ | Ý nghĩa |
|----|---------|
| **Finding** | 1 lỗ hổng do SAST/SCA/DAST tool báo, đã normalize. Đơn vị nguyên tử của hệ thống. |
| **Artifact** | File ZIP do GitHub Actions sinh ra cho 1 tool (vd. `semgrep-report.zip`). Chứa N findings. |
| **Run** | Một workflow run trên GitHub Actions. Mỗi run ⇒ nhiều artifacts ⇒ nhiều findings. |
| **Project** | Bản ghi cấu hình cho 1 GitHub repo (token, key Gemini, polling settings). Multi-tenant. |
| **Suppression** | Quy tắc auto-revoke (V3.1 Tier 2). Match theo rule_id/file_glob/tool/severity. |
| **dedup_hash** | SHA-256(rule_id + file_path + scrubbed_message). Dùng để gộp lặp + inherit auto-revoke. |
| **Gate** | Endpoint `/findings/gate-count` mà CI gọi sau scan để quyết định pass/fail. |
| **Triage** | AI batch classify FP/TP (V3.1 Tier 3). |
| **RBAC per-project** | Bật bằng `RBAC_PER_PROJECT=true`. JWT mang `memberships`={project_id: role}. |

## Khi nào nên đọc file nào

- **"Cần fix bug trong ingest pipeline"** → `03-backend-flows.md` § 3.1 + 3.2, rồi `processor.py`.
- **"Thêm endpoint mới"** → `05-api-reference.md` để xem pattern auth/RBAC, rồi `api/artifacts.py` làm template.
- **"Sửa UI"** → `04-frontend-flows.md`, sau đó `dashboard/src/pages/<TenPage>.tsx`.
- **"Hiểu schema DB"** → `02-data-model.md`, rồi `models/entities.py`.
- **"Setup local lần đầu"** → `06-runbook.md`.
