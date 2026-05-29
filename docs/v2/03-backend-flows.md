# 03 — Backend flows

5 luồng quan trọng nhất, đọc theo source code thực tế.

---

## 3.1 Ingest qua webhook (CI gọi sau khi run xong)

**Trigger**: GitHub Actions workflow step gửi `POST /webhook/pipeline-complete`.

**Source**: `api/artifacts.py:webhook_pipeline_complete` (line 527)

```
CI runner
    │ POST /webhook/pipeline-complete
    │ Authorization: Bearer <CI_WEBHOOK_TOKEN>
    │ body: WebhookRunPayload { run_id, run_number, repository, pipeline_status }
    ▼
┌──────────────────────────────────┐
│ Auth check                       │
│  - CI_WEBHOOK_TOKEN empty → bypass│
│  - else: bearer phải match       │
└────────────┬─────────────────────┘
             │
             ▼
┌──────────────────────────────────┐
│ Project routing                  │
│                                  │
│  if MULTI_TENANT_ENABLED         │
│     and body.repository:         │
│    → lookup Project by           │
│      github_url=https://github.com/{repo}│
│  else / not found:               │
│    → get_or_create from env      │
│      GITHUB_OWNER/REPO (legacy)  │
└────────────┬─────────────────────┘
             │
             │ Trả 202 ngay lập tức,
             │ background_task.add_task(processor.process_run)
             ▼
┌──────────────────────────────────────┐
│ SecurityProcessor.process_run        │  services/processor.py:64
│  (chạy trong asyncio task riêng,     │
│   không block HTTP response)         │
│                                      │
│ 1. Resolve project (by id, expunge   │
│    khỏi session để dùng cross-session)│
│ 2. Build GitHubClient:               │
│      - có github_token+owner+repo →   │
│        per-project client             │
│      - else → env-singleton           │
│ 3. Load artifact profile             │
│    (core/profiles.py)                │
│ 4. github.list_artifacts(run_id)     │
│ 5. Filter security artifacts:        │
│    profile.matches(name)             │
│    (vd. semgrep-report,              │
│     trivy-image-scan-123, ...)       │
│ 6. For each artifact:                │
│    ┌────────────────────────────┐    │
│    │ idempotency check:         │    │
│    │  - đã exist + processed →   │    │
│    │    skip                     │    │
│    │  - exist nhưng pending/failed→│ │
│    │    wipe findings cũ, retry  │    │
│    │  - không exist → create row │    │
│    └────────────┬───────────────┘    │
│                 ▼                    │
│         self._run() — § 3.2          │
│ 7. Update last_processed_run_id      │
│    (chỉ tiến forward)                │
└──────────────────────────────────────┘
```

**Idempotency**: SAST + DAST webhook cùng `run_id` có thể đến tách biệt, nhưng
`list_artifacts` trả cumulative set → check `status='processed'` trên Artifact
row trước khi re-process (`processor.py:126`). 1 file lỗi không kill cả batch (`processor.py:171` try/except per artifact).

---

## 3.2 Single-artifact pipeline (`SecurityProcessor._run`)

**Source**: `services/processor.py:203`

```
artifact_id, github_artifact_id
       │
       ▼
┌────────────────────────────────────┐
│ github.fetch_artifact()            │
│  - ZIP download                    │
│  - size cap 50MB (Zip Bomb)        │
│  - reject paths có ../ (Zip Slip)  │
│  - chỉ extract .sarif/.xml/.json   │
│  - cap 10MB/file                   │
│  return [{filename, content}, ...] │
└────────────┬───────────────────────┘
             │
             ▼ for each file
┌────────────────────────────────────┐
│ scrubber.scrub_content()           │  core/guardrails.py:35
│                                    │
│  if _looks_like_json(content):     │
│    → return AS-IS (V2.7)            │
│    Lý do: detect-secrets thay      │
│    "[SECRET_SCRUBBED]" cho cả      │
│    dòng → break JSON. Regex email   │
│    ăn vào \n@app → invalid escape. │
│  else:                             │
│    → scrub_text():                 │
│      1. detect-secrets line scrub  │
│      2. EMAIL regex → token        │
│      3. IPv4 regex → token         │
└────────────┬───────────────────────┘
             │
             ▼
┌────────────────────────────────────┐
│ NormalizerFactory.get(filename, content)│
│                                    │
│ 6 normalizer families (normalizer.py):│
│  - SemgrepSARIF                    │
│  - CodeQLSARIF                     │
│  - SpotBugsXML (defusedxml)        │
│  - ESLintSARIF                     │
│  - TrivyJSON (vuln + secret)       │
│  - DependencyCheckJSON             │
│  - OWASPZapSARIF (DAST)            │
│                                    │
│ Factory tự detect via content head │
│ (lenient: parse dict bằng tay thay │
│ vì pydantic strict → 1 SARIF lỗi   │
│ không kill cả batch).              │
│                                    │
│ ValueError → skip file.            │
└────────────┬───────────────────────┘
             │
             ▼
┌────────────────────────────────────┐
│ normalizer.normalize() →            │
│   list[FindingCreate]              │
│                                    │
│ Severity mapping (xem normalizer.py):│
│  SARIF level error/warning/note    │
│   → high/medium/low                │
│  SpotBugs priority 1-5             │
│  ESLint severity 0/1/2             │
│  Trivy/DepCheck → _sca_severity()  │
│    ưu tiên CVSS score, fallback    │
│    label, default 'medium' (pending)│
│                                    │
│ Promotion: CWE injection class     │
│ (77, 78, 89, 94, 95, 502, 917) ×   │
│ DAST 'high' → promoted 'critical'  │
└────────────┬───────────────────────┘
             │
             ▼
┌────────────────────────────────────┐
│ deduplicate() — per-batch          │
│   batch_hashes set                 │
└────────────┬───────────────────────┘
             │
             ▼
┌────────────────────────────────────┐
│ enricher.enrich()                  │  services/enricher.py
│  - CWE description từ static dict  │
│  - CVSS score nếu raw_data có      │
│  - OWASP Top 10 2021 mapping       │
└────────────┬───────────────────────┘
             │
             ▼
┌────────────────────────────────────┐
│ scrubber.scrub_text(enriched.message)│
│  (V2.7 — per-field post-parse PII   │
│   scrub. Vì pre-parse skip JSON.)  │
└────────────┬───────────────────────┘
             │
             ▼
┌────────────────────────────────────┐
│ compute_dedup_hash(                │
│   rule_id, file_path, scrubbed_msg)│
│  → SHA-256 truncated 64 chars      │
└────────────┬───────────────────────┘
             │
             ▼
┌────────────────────────────────────┐
│ Auto-revoke check (V3.1 T1 + T2)   │
│                                    │
│ Tier 1: dedup_hash đã từng REVOKED │
│   trong cùng project → inherit     │
│   status=REVOKED, revoked_by=      │
│   'auto-suppress'                  │
│                                    │
│ Tier 2: pattern rule match         │
│   (rule_matches() check rule_id,   │
│   file_glob fnmatch, tool, severity│
│   ≤ severity_max) → REVOKED,       │
│   revoked_by='auto-suppress (rule #X)'│
│                                    │
│ Tier 1 wins khi cả 2 match.        │
└────────────┬───────────────────────┘
             │
             ▼
   session.add_all(findings)
   artifact.status = 'processed'
   await session.commit()
```

---

## 3.3 Poller (background task, every 5 min)

**Source**: `services/poller.py:GitHubPoller.start`

Khởi động từ `main.py:lifespan` khi `APP_ENV != testing`.

```
┌─────────────────────────────────────┐
│ start() loop                        │
│   await sleep(interval)             │
│   _poll() → route theo flag         │
└────────────┬────────────────────────┘
             │
             ├─── MULTI_TENANT_ENABLED=false ──→ _poll_single_tenant()
             │       │
             │       ├─ Find/create project từ env GITHUB_OWNER/REPO
             │       ├─ list_workflow_runs(workflow_name, branch)
             │       ├─ filter: id > last_processed_run_id
             │       │           AND conclusion == 'success'
             │       └─ for each new run sorted by id:
             │            → processor.process_run(project_id, run_id)
             │            → update last_processed_run_id
             │
             └─── MULTI_TENANT_ENABLED=true ──→ _poll_multi_tenant()
                     │
                     ├─ session.list_active() projects
                     ├─ asyncio.gather(_poll_one_project)
                     │    với semaphore=3 (rate-limit GitHub 5000/h PAT)
                     │    return_exceptions=True (1 lỗi không kill cycle)
                     └─ per project:
                          → GitHubClient.for_project(p)
                          → list_workflow_runs(p.polling_workflow_name,
                                               p.polling_branch)
                          → filter new + success
                          → processor.process_run(p.id, run_id)
                          → update p.last_processed_run_id
```

---

## 3.4 `/findings/{id}/explain` — AI analysis

**Source**: `api/analysis.py` + `services/llm/service.py`

```
POST /findings/{id}/explain
Authorization: Bearer <JWT>
       │
       ▼
┌──────────────────────────────────┐
│ get_current_user(JWT)            │
│  - decode HS256                  │
│  - read sub, role, memberships   │
└────────────┬─────────────────────┘
             │
             ▼
┌──────────────────────────────────┐
│ enforce_finding_project_access   │  core/auth.py:159
│   min_role='developer'           │
│  - Finding → Artifact → project_id│
│  - if RBAC_PER_PROJECT off → bypass│
│  - if user.role == 'admin' → bypass│
│  - else check membership ≥ developer│
│       → 403 nếu fail              │
└────────────┬─────────────────────┘
             │
             ▼
┌──────────────────────────────────┐
│ if status == 'ai_analyzed' AND   │
│    ai_analysis JSON exists:      │
│   → return cached AnalysisResult │
│      (no Gemini call!)           │
└────────────┬─────────────────────┘
             │
             ▼ cache miss
┌──────────────────────────────────┐
│ LLMAnalysisService.analyze_finding│
│                                  │
│ 1. _resolve_project(finding)     │
│    Finding → Artifact → Project  │
│ 2. Pick credentials:             │
│    - project.gemini_api_key ?    │
│      GeminiClient cache (api_key,│
│      model) → reuse              │
│    - else env GEMINI_*            │
│ 3. Pick GitHubClient cùng cách   │
│ 4. Fetch source_code:            │
│    - raw_data.source_code cached?│
│    - else github.fetch_file_content│
│      (cap 100KB, skip binary)    │
│    - scrub_content() on result   │
│    - persist back vào raw_data   │
│ 5. Extract ±15 lines context     │
│    around line_number            │
│ 6. InjectionGuardrail.check():   │
│    - reject patterns ("ignore    │
│      previous instructions", etc)│
│    - reject content > 2000 chars │
│    - else sanitize (strip ctrl)  │
│ 7. build_prompt(...)              │
│    → llm/prompts.py              │
│ 8. gemini.analyze(prompt)        │
│    → google-genai SDK            │
│    → response_schema=AnalysisOutput│
│       (Pydantic structured output)│
│    → retries 3× on 429/503       │
│ 9. AnalysisResult(...)           │
│ 10. finding.status='ai_analyzed' │
│     finding.ai_analysis=result   │
│     await session.commit()       │
└────────────┬─────────────────────┘
             │
             ▼
       HTTP 200 AnalysisResult
       (vulnerability_id, explanation_vi, impact_vi,
        remediation_diff, severity, cwe_reference,
        confidence)
```

Rate-limit: `slowapi.Limiter` đính router (`api/analysis.py:19`) — chỉ cho phép N req/min per IP (config qua slowapi default).

---

## 3.5 `/api/chat/command` dispatch (ChatOps)

**Source**: `api/chat.py:handle_command` + `services/command_service.py`

```
POST /api/chat/command
Authorization: Bearer <JWT>
body: CommandRequest { command: "/approve", finding_id, justification, ... }
       │
       ▼
┌──────────────────────────────────────┐
│ COMMAND_ROLES check                  │
│  cmd ∈ {explain, fix, report, scan,  │
│         rerun, approve, revoke,      │
│         status, results, help,       │
│         feedback}                    │
│  user.role phải ∈ allowed_roles[cmd]│
└────────────┬─────────────────────────┘
             │
             ▼
┌──────────────────────────────────────┐
│ CommandService.handle()              │
│  dispatch dict → _handle_<cmd>       │
└────────────┬─────────────────────────┘
             │
             ├─── explain/fix → _handle_explain()
             │      reuse LLMAnalysisService (§ 3.4)
             │
             ├─── scan → github.dispatch_workflow('ci.yml')
             │
             ├─── rerun → github.rerun_workflow(run_id)
             │
             ├─── approve → _handle_approve()
             │      ├ enforce_finding_project_access(min_role='security_lead')
             │      ├ reject nếu status==APPROVED (409)
             │      ├ reject nếu severity==INFO (400)
             │      ├ justification length ≥ 20 (422 otherwise)
             │      └ status=APPROVED, audit trail set, commit
             │
             ├─── revoke → tương tự, reject nếu đã REVOKED
             │
             ├─── report → report_service.generate_html() → data.html
             │
             ├─── status → list_workflow_runs → latest run summary
             │
             ├─── results → query findings của run_id (hoặc latest)
             │      + severity breakdown + top 5 critical/high
             │
             ├─── help → static list 11 lệnh + role yêu cầu
             │
             └─── feedback → CommandFeedback row, ≥5 ký tự
```

Free-form chat (`POST /api/chat/message`) khác — không phải command:
- Lấy context: finding hiện tại + 5 critical/high gần nhất
- Gọi `gemini.chat(text, context)` (model basic, không structured)
- Bên cạnh đó chạy regex `_suggested_command()` để map "phân tích finding 5" → `/explain 5`
- Trả `{reply, suggested_command}` → UI render suggested thành chip clickable

---

## 3.6 V3.3 read-side auth gate

Mọi endpoint list/read findings đều qua `require_read_access`:

```python
async def require_read_access(credentials):
    if settings.ANONYMOUS_READ_ENABLED:
        return None  # legacy bypass
    return await get_current_user(credentials)  # demand JWT
```

Khi RBAC bật + user không phải admin, route gọi `allowed_project_ids(user)`
để fold `project_ids=[1,5,9]` vào filter — repo trả `[]` ngay nếu list rỗng
(`finding_repo.py:67`). Không leak dữ liệu project user không thuộc.

`/findings/gate-count` exception duy nhất: chấp nhận `CI_WEBHOOK_TOKEN` làm
bearer thay JWT để CI gọi không phải issue token riêng.
