# 02 — Data model

8 bảng SQLAlchemy. Tất cả định nghĩa ở `mcp/src/models/entities.py`.

## 2.1 ERD

```
       Project (1) ─────────< (N) Artifact (1) ─────────< (N) Finding
          │                                                    │
          │                                                    │
          ├─< (N) ProjectMember                                │
          │                                                    │
          ├─< (N) SuppressionRule                              │
          │                                                    │
          ├─< (N) UptimeCheck                                  │
          │                                                    │
          ├─< (N) Alert (project_id nullable)                 │
          │                                                    │
                                       CommandFeedback >─── (0..1) ┘
                                       AppConfig (no FK — flat KV)
```

## 2.2 Tables

### `projects` — multi-tenant config

| Col | Type | Why |
|-----|------|-----|
| `id` | int PK | — |
| `name` | string(255) | UI label, free-form |
| `github_url` | string(512) **UNIQUE** | Key dùng để lookup từ webhook payload (`MULTI_TENANT_ENABLED`) |
| `created_at` | tz-aware datetime | — |
| `last_processed_run_id` | **BigInteger** nullable | GitHub workflow run IDs là 64-bit (~25B as of 2026). INT4 overflow trên Postgres → đã hit production bug. |
| `github_owner` / `github_repo` / `github_token` | string | Per-project credentials cho V2.8 multi-tenant. Plaintext (decision: thesis scope; xem `core/secrets.py` cho Fernet wrap chưa fully wired). |
| `gemini_api_key` / `gemini_model` | string | Per-project AI key — cho phép quota cô lập giữa các tenant. |
| `artifact_profile` | string(64) | Key vào `core/profiles.py` để biết artifact name nào là "security relevant". Default `github-actions-default`. |
| `polling_workflow_name` / `polling_branch` | string | Override env cho từng project. |
| `active` | **int 0/1** | Lý do `int` thay vì `bool`: asyncpg không tự coerce bool → INTEGER khi Postgres column là INT, raise `invalid input syntax`. |

Properties (Pydantic `from_attributes`): `has_github_token`, `has_gemini_api_key` — exposes config status mà không leak secret.

### `artifacts` — 1 ZIP do GitHub Actions sinh ra

| Col | Type | Why |
|-----|------|-----|
| `id` | int PK | — |
| `github_artifact_id` | string(255) | ID raw từ GitHub API (giữ string để tránh BigInt-mismatch giữa tools). |
| `project_id` | FK → `projects.id` | — |
| `github_run_id` | **BigInteger** indexed nullable | Cho phép group findings theo workflow run (Pipelines page); index để query `?run_id=` nhanh. |
| `status` | string ∈ {`pending`, `processed`, `failed`} | `ArtifactStatus` enum, store as string. |
| `created_at` / `updated_at` | tz-aware datetime | onupdate cập nhật `updated_at`. |

### `findings` — đơn vị nguyên tử của hệ thống

| Col | Type | Why |
|-----|------|-----|
| `id` | int PK | — |
| `artifact_id` | FK | Để truy ngược → project (`enforce_finding_project_access`). |
| `tool` | string(100) | `semgrep`, `codeql`, `eslint`, `spotbugs`, `trivy`, `dependency-check`, `owasp-zap`, ... |
| `rule_id` | string(255) | ID tool-specific (`python.lang.security.audit.dangerous-system-call`, `CWE-79`, ...). |
| `severity` | string(50) | Lowercase: `critical` / `high` / `medium` / `low` / `info`. Normalizer thống nhất. |
| `message` | text | Tool description, đã scrub PII (V2.7 per-field). |
| `file_path` | string(1024) | Path tương đối repo root, hoặc `unknown` nếu tool không cho biết. |
| `line_number` | int nullable | — |
| `raw_data` | JSON nullable | Original payload + cached `source_code` (do `LLMAnalysisService.analyze_finding` fetch về một lần). |
| `normalized_at` | tz-aware datetime | Timestamp khi normalizer xử lý. |
| `cwe_id` | string(50) nullable | Sau enrich. |
| `cvss_score` | float nullable | Cho SCA tools (Trivy/DepCheck). |
| `dedup_hash` | string(64) **indexed** | SHA-256(`rule_id + file_path + scrubbed_message`). Dùng cho dedup TRONG batch và auto-revoke CROSS-RUN (V3.1 Tier 1). |
| `status` | string(30) | State machine — xem § 2.3. |
| `ai_analysis` | JSON nullable | Cache kết quả Gemini (`AnalysisResult` serialized). |
| `justification` / `approved_by` / `approved_at` | audit trail approve | Min length 20 ký tự enforce ở service layer. |
| `revoke_justification` / `revoked_by` / `revoked_at` | audit trail revoke | — |

Property `project_id` (computed): traverse `Artifact → Project`. **Try/except**
vì lazy-load trong async raise `MissingGreenlet` nếu artifact chưa được
eager-load. Pydantic `FindingOut` đọc field này — repo phải dùng `selectinload(Finding.artifact)` (xem `finding_repo.py:32`).

### `app_config` — runtime KV cho dashboard

Free-form JSON value cho 3 keys hiện hữu: `sast_tools`, `gates`, `ai`. Schema
defaults trong `services/config_service.py`. Chỉ admin update qua `PUT /config/{key}`.

### `uptime_checks` — V2.4 monitor

1 row mỗi cycle `monitor_loop`. Pruned >7 ngày bởi `prune_loop` (free Postgres
256MB sẽ đầy trong vài tháng nếu không prune). `is_up` lưu int 0/1 vì SQLite.

### `command_feedback` — `/feedback` ChatOps

User submit free-text feedback về chất lượng AI analysis. `finding_id` optional
(general feedback OK). Persist để tune prompt sau.

### `project_members` — V3.0 RBAC

| Col | Type | Why |
|-----|------|-----|
| `(project_id, username)` | composite PK | Index lookup + đảm bảo unique. |
| `role` | string(20) | `viewer` / `developer` / `security_lead` / `owner`. Lattice strict. |
| `created_at` | tz-aware datetime | — |

Username (không user_id) vì hệ thống không có bảng `users` — identity đến từ
JWT `sub` claim, issue qua `/api/chat/auth/token`. Quyết định additive: không
phải migrate user gì cả khi bật V3.0.

### `suppression_rules` — V3.1 Tier 2

Pattern-based auto-revoke. Khi ingest sinh Finding match rule → `status=REVOKED` luôn.

| Col | Why |
|-----|-----|
| `rule_id` nullable | NULL = match all rule. |
| `file_glob` nullable | `fnmatch` style. NULL = mọi file. |
| `tool` nullable | NULL = mọi tool. |
| `severity_max` nullable | Vd. `medium` → chỉ áp rule cho finding ≤ medium. NULL = mọi severity. |
| `reason` text NOT NULL | Audit. |
| `created_by` string NOT NULL | — |
| `expires_at` tz-aware datetime nullable | Default 90 ngày (temp-by-design). Filter `list_active_for_project` bỏ expired. |

Logic match: xem `repositories/suppression_repo.py:rule_matches()`.

### `alerts` — V2.4 operational events

Khác Finding — đây là **runtime event** (URL down, CVE mới, deploy failed). Không phải lỗi source code.

| Col | Notes |
|-----|-------|
| `kind` ∈ {`down`, `recovered`, `cve_new`, `deploy_failed`} | — |
| `severity` ∈ {`low`, `medium`, `high`} | — |
| `extra` JSON | Vd. `{target_url, last_status, fail_count}` |
| `notified_at` | Set khi SMTP gửi mail OK |
| `acknowledged_at` | UI ack qua `POST /monitor/alerts/{id}/ack` |

## 2.3 Finding state machine

```
                   normalize + dedup
                          │
                          ▼
                  ┌───────────────┐
                  │ pending_review│  ←──┐
                  └───┬───────┬───┘     │
                      │       │         │
        /explain      │       │  auto-revoke (V3.1 T1+T2)
            │         │       │         │
            ▼         │       ▼         │
     ┌───────────┐   │  ┌─────────┐   │
     │ai_analyzed│   │  │ REVOKED │   │
     └─────┬─────┘   │  └────┬────┘   │
           │         │       │        │
   /approve│ /approve│       │/revoke │
           ▼         ▼       │        │
        ┌──────────────┐    │        │
        │   APPROVED   │ ───┘────────┘   /revoke
        └──────────────┘
```

- `pending_review` — default sau khi normalize.
- `ai_analyzed` — sau `/explain` thành công (Gemini đã sinh `AnalysisResult`).
  Re-call `/explain` sẽ trả cached `ai_analysis` thay vì gọi Gemini lại.
- `APPROVED` — security_lead+ phê duyệt bypass. Justification ≥ 20 ký tự. Finding `info` bị reject (không cần approve).
- `REVOKED` — đã xác định FP hoặc accepted risk. Loại khỏi gate-count.

**Rule sống**: không re-approve cái đã APPROVED, không re-revoke cái đã REVOKED (HTTP 409).

## 2.4 Dedup hash semantic

```python
dedup_hash = SHA-256(rule_id + file_path + scrubbed_message)
```

`scrubbed_message` là message **sau** khi `ScrubbingService.scrub_text` chạy
(email/IP/secret đã thay token). 3 use case:

1. **Per-batch dedup**: trong `_build_findings`, `batch_hashes` set tránh duplicate trong cùng 1 artifact.
2. **Cross-artifact dedup**: hash unique theo (rule, file, message) → 2 artifact khác nhau cùng phát hiện 1 lỗi → chỉ 1 row.
3. **Cross-run auto-revoke (V3.1 Tier 1)**: nếu hash từng được REVOKED ở 1 run trước, finding mới đến cùng hash auto-REVOKED với justification `"inherited revoke from ..."`.

## 2.5 Index strategy

| Table | Index | Lý do |
|-------|-------|------|
| `artifacts.github_run_id` | btree | Pipelines page query findings by run. |
| `findings.dedup_hash` | btree | Cross-run auto-revoke lookup. |
| `uptime_checks.checked_at` | btree | Monitor list query window N hours. |
| `alerts.raised_at` | btree | Monitor alerts ordered by recency. |
| `suppression_rules.project_id` | btree | List active rules per project. |

(SQLAlchemy default index từ `index=True` trên `mapped_column`.)

## 2.6 Migration philosophy

Hiện **không có Alembic** đã run (task #20 marked completed nhưng folder rỗng — TODO future). `init_db()` ở `core/db.py` chỉ chạy `Base.metadata.create_all()`. Trade-off:

- Dev/local: oneshot init, drop & re-create dễ.
- Prod: thêm cột mới = manual `ALTER TABLE` qua psql, hoặc `DROP+CREATE` trên test DB.

Đây là một **gap** cần đóng nếu scale lên. Xem task #19 + #20 trong todo list.
