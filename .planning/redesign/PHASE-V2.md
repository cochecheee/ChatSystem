# PHASE V2 — DevSecOps Template (CI → CD → Runtime SAST → Monitor)

> Plan cụ thể cho mục tiêu V2: biến chat-system từ "1 dashboard SAST" thành **template DevSecOps end-to-end** mà project khác kế thừa được. Nhỏ-nhẹ cho đồ án nhưng đầy đủ flow.

**Mục tiêu**: 2 tuần, ~70-80h work.

**Inputs đã chốt** (qua AskUser):
- CD: Push Docker Hub + auto-deploy staging Render/Fly.io free tier
- Monitor: DAST + CVE daily + uptime/error tracking nhẹ + alert email
- Template: Reusable workflow + composite Action (build trên `action.yml` v0.1.0)

---

## Vision

```
[Inheritor repo]                          [chat-system platform]
       │                                          │
       │ uses: cochecheee/sast-chat-ci@v2         │
       │ uses: cochecheee/sast-chat-cd@v2         │
       │ uses: cochecheee/sast-chat-monitor@v2    │
       ▼                                          ▼
┌──────────────────┐                    ┌──────────────────┐
│  Push code       │                    │  Dashboard       │
│       ↓          │                    │  (existing)      │
│  CI (SAST)       │ ───webhook────►    │  + Runtime tab   │
│       ↓          │                    │  + Monitor tab   │
│  CD (Deploy)     │ ───deploy event─►  │  + Email alerts  │
│       ↓                                          ▲
│  Staging URL     │ ◄──DAST scan──────────────────│
│       ↓          │                               │
│  Daily CVE       │ ───alert───────────────────►  │
│  Daily uptime    │ ───alert───────────────────►  │
└──────────────────┘                    └──────────────────┘
```

**3 reusable artifact** mà inheritor repo dùng:

1. `cochecheee/sast-chat/.github/workflows/sast-ci.yml` — reusable workflow (CI + SAST + push notify)
2. `cochecheee/sast-chat/cd-action` — composite Action (build image + deploy Render)
3. `cochecheee/sast-chat/monitor-action` — composite Action (DAST + CVE re-scan + uptime ping + email)

---

## Sub-phase V2.1 — Reusable workflow + composite refactor

**Effort**: 2 ngày.

### Mục tiêu

Inheritor repo chỉ cần 1-2 file workflow ngắn để có toàn bộ SAST CI/CD + monitor.

### Nội dung

1. **Reusable workflow** `cochecheee/sast-chat/.github/workflows/sast-ci.yml@v2`
   - Inputs: `language` (java/python/node/go), `dashboard_url`, `dashboard_token` (secret)
   - Tự chọn SAST tool theo language:
     - Java → Semgrep + CodeQL + SpotBugs + Dep-Check + Trivy
     - Python → Semgrep + CodeQL + Bandit + Trivy + Safety
     - Node → Semgrep + CodeQL + ESLint security + npm audit + Trivy
     - Go → Semgrep + CodeQL + gosec + Trivy
   - Output: artifact + webhook về dashboard

2. **Refactor `action.yml`** thành 3 composite action tách biệt trong subdirs:
   - `actions/notify-dashboard/action.yml` — wraps webhook (rename của action.yml hiện tại)
   - `actions/sast-suite/action.yml` — chạy SAST tools theo language input
   - `actions/aggregate-sarif/action.yml` — gộp SARIF artifacts upload tới dashboard

3. **Sample inheritor repo** `cochecheee/sast-chat-sample-java`:
   ```yaml
   # .github/workflows/security.yml
   name: Security
   on: [push, pull_request]
   jobs:
     security:
       uses: cochecheee/sast-chat/.github/workflows/sast-ci.yml@v2
       with:
         language: java
         dashboard_url: ${{ secrets.MCP_GATEWAY_URL }}
         dashboard_token: ${{ secrets.MCP_WEBHOOK_TOKEN }}
   ```

### Deliverables

- [ ] `.github/workflows/sast-ci.yml` reusable workflow
- [ ] 3 composite actions split từ action.yml hiện tại
- [ ] `cochecheee/sast-chat-sample-java` repo (mới hoặc fork demo)
- [ ] `docs/inheritor-guide.md` — quickstart cho project mới (5 phút onboard)

---

## Sub-phase V2.2 — CD pipeline (deploy staging)

**Effort**: 3 ngày.

### Mục tiêu

Sau khi CI pass + SAST không có critical, auto-deploy to staging. Chứng minh "Shift Left" thực sự — security gate trước deploy.

### Nội dung

1. **Build & push Docker image** (đã có infrastructure ở v0.1.0):
   - Trigger sau khi `sast-ci.yml` pass
   - Push `cochecheee/<inheritor-repo>:sha-<commit>` + `:latest`
   - Multi-arch nếu dễ (linux/amd64 đủ cho thesis)

2. **Auto-deploy staging** — chọn 1 platform free:
   - **Render** (default cho thesis) — Render Web Service free tier, deploy hook URL trigger.
     - Pros: 1 click setup, GitHub-native, có free tier rồ ràng.
     - Cons: cold start ~30s, build trong Render (chậm hơn pre-built image).
     - Workaround: Render dùng pre-built image từ Docker Hub thay vì build từ source.
   - **Alternative**: Fly.io paid tier ($5/mo), Koyeb free, Railway $5 credit. Document trong inheritor-guide.

3. **Approval gate** — GitHub Environment protection:
   - Environment "staging" — auto-approve
   - Environment "production" — require manual approval của security_lead role
   - Reuse JWT role concept từ chat-system

4. **Composite Action** `cochecheee/sast-chat/actions/deploy-staging`:
   ```yaml
   - uses: cochecheee/sast-chat/actions/deploy-staging@v2
     with:
       image: cochecheee/sast-chat-sample-java
       deploy_hook: ${{ secrets.RENDER_DEPLOY_HOOK }}
       wait_for_health: 60   # seconds
       health_url: https://my-app-staging.onrender.com/health
   ```

5. **Post-deploy webhook** vào chat-system:
   - Body: `{"event": "deployed", "service": "...", "url": "...", "sha": "..."}`
   - Backend lưu vào table mới `Deployment(project_id, url, sha, deployed_at, status)`
   - Dashboard có badge "Deployed" trên Pipelines tab

### Backend changes cần làm

```python
# mcp/src/models/entities.py — new table
class Deployment(Base):
    __tablename__ = "deployments"
    id: int (pk)
    project_id: FK
    sha: str
    staging_url: str
    deployed_at: datetime
    status: str  # deployed | failed | rolled_back

# mcp/src/api/artifacts.py — new endpoint
@router.post("/webhook/deployment")
async def webhook_deployment(...): ...
```

### Deliverables

- [ ] `actions/deploy-staging/action.yml` (Render variant)
- [ ] `Deployment` entity + migration
- [ ] `POST /webhook/deployment` endpoint
- [ ] Dashboard "Deployed" badge ở Pipelines tab
- [ ] `docs/cd-setup.md` — Render setup guide

---

## Sub-phase V2.3 — Runtime SAST (DAST + CVE monitoring)

**Effort**: 4 ngày.

### Mục tiêu

Sau khi staging deployed, chạy SAST động (DAST) trên URL thật + monitor CVE mới publish ảnh hưởng deps đã deploy.

### Nội dung

1. **OWASP ZAP DAST** — daily scheduled GitHub Action:
   ```yaml
   # cochecheee/sast-chat/.github/workflows/dast-scheduled.yml
   on:
     schedule: [cron: '0 2 * * *']   # 2 AM UTC daily
     workflow_dispatch:
   inputs:
     target_url: ...
     scan_type: baseline | full
   ```
   - Baseline scan ~5 phút (passive)
   - Full scan ~15 phút (active probing)
   - Output: ZAP JSON report
   - Composite action `actions/zap-scan` parse ZAP output → POST tới dashboard

2. **Dashboard "Runtime" tab** mới:
   - List DAST findings (1 page riêng vì format khác SAST)
   - Source: ZAP JSON normalize qua mới `services/normalizer.py:ZapNormalizer`
   - Reuse Finding entity với `tool=zap`, `category=dast` (mới — extend FindingRepository)

3. **Daily CVE re-scan** — workflow chạy lại Trivy fs scan trên latest commit + so sánh với last scan:
   - New CVE published → finding mới → email alert
   - CVE resolved (đã fix) → finding `status=auto_resolved`
   - Logic so sánh: dedup_hash diff theo run

4. **Composite action** `actions/runtime-monitor/action.yml`:
   ```yaml
   - uses: cochecheee/sast-chat/actions/runtime-monitor@v2
     with:
       staging_url: https://my-app-staging.onrender.com
       dashboard_url: ${{ secrets.MCP_GATEWAY_URL }}
       dashboard_token: ${{ secrets.MCP_WEBHOOK_TOKEN }}
       zap_scan_type: baseline
       enable_cve_recheck: true
   ```

### Backend changes

- `Finding.category` field thêm value `"dast"` (hiện chỉ `sast` | `deps`)
- New normalizer `ZapNormalizer` parse ZAP JSON
- Stats endpoint thêm `dast_open`, `dast_critical_high`
- Alert table `Alert(type, finding_id, recipient, status, sent_at)` — Phase V2.4 dùng

### Deliverables

- [ ] `actions/zap-scan/action.yml` + ZAP normalizer
- [ ] `actions/cve-recheck/action.yml` (Trivy daily re-scan)
- [ ] Dashboard tab "Runtime" (DAST findings)
- [ ] `docs/dast-setup.md`

---

## Sub-phase V2.4 — Monitor + Email alert

**Effort**: 3 ngày.

### Mục tiêu

Monitor staging app uptime + error rate. Email alert khi: critical finding mới, deploy fail, app down, CVE mới ảnh hưởng deps đã deployed.

### Nội dung

1. **Uptime check** — composite action `actions/uptime-check`:
   - Cron mỗi 15 phút (GitHub Action) → ping `health_url`
   - Track 200/non-200 ratio trong 24h sliding window
   - POST tới dashboard `/webhook/uptime`
   - Alert email nếu downtime > 5 phút
   - Alternative: dùng UptimeRobot free + webhook integration (đỡ tốn GitHub Actions minutes)

2. **Error tracking nhẹ** — Sentry free tier (5k errors/month):
   - Backend (mcp) integrate `sentry-sdk[fastapi]` — ~30 LOC
   - Frontend (dashboard) integrate `@sentry/react` — ~30 LOC
   - Inheritor repo: docs/sentry-setup.md cho team tự setup
   - Dashboard tab "Monitor" hiển thị Sentry events count (qua Sentry API)

3. **Email alert engine**:
   - Backend: SMTP qua Gmail App Password (đơn giản, không tốn tiền)
   - Alert types: `critical_finding`, `deploy_failed`, `uptime_down`, `new_cve`
   - Throttle: max 1 email/severity/15min để tránh spam
   - Template HTML đơn giản (reuse `report_service` pattern)
   - Subscribers per project: `Project.alert_emails` (CSV string field)

4. **Dashboard tab "Monitor"**:
   - Uptime chart (24h)
   - Error rate (Sentry API call)
   - Recent alerts list (DB)
   - "Send test email" button

5. **Composite action** `actions/notify-monitor/action.yml`:
   ```yaml
   - uses: cochecheee/sast-chat/actions/notify-monitor@v2
     with:
       event: deployed | failed | down
       service_name: my-app
       dashboard_url: ${{ secrets.MCP_GATEWAY_URL }}
       dashboard_token: ${{ secrets.MCP_WEBHOOK_TOKEN }}
   ```

### Backend changes

```python
# mcp/src/models/entities.py
class Project(Base):
    # ... existing ...
    alert_emails: str = ""  # CSV
    sentry_dsn: str = ""

class Alert(Base):
    id, project_id (FK), type, severity, title, body
    sent_to, sent_at, status (pending|sent|failed)

class UptimeCheck(Base):
    id, project_id, checked_at, status_code, response_time_ms, healthy: bool

# mcp/src/services/alert_service.py — new
class AlertService:
    def send(self, type, project, finding=None) -> Alert: ...
    # SMTP via env: ALERT_SMTP_HOST, ALERT_SMTP_USER, ALERT_SMTP_PASS

# mcp/src/api/artifacts.py
@router.post("/webhook/uptime")
@router.post("/alert/test")    # for "Send test email" button
```

### Deliverables

- [ ] `Alert` + `UptimeCheck` entities + migration v3
- [ ] `services/alert_service.py` SMTP wrapper
- [ ] `actions/uptime-check/action.yml`
- [ ] `actions/notify-monitor/action.yml`
- [ ] Sentry SDK integration BE + FE
- [ ] Dashboard "Monitor" tab
- [ ] `docs/email-setup.md` (Gmail App Password howto)
- [ ] `docs/sentry-setup.md`

---

## Timeline tổng (2 tuần)

```
Tuần 1 — V2.1 + V2.2
  Day 1: V2.1 — refactor action.yml thành 3 composite + reusable workflow
  Day 2: V2.1 — sample inheritor repo Java + inheritor-guide.md
  Day 3: V2.2 — Render setup + deploy-staging composite action
  Day 4: V2.2 — Deployment entity + webhook + dashboard badge
  Day 5: V2.2 — Test end-to-end CI → CD → staging URL live

Tuần 2 — V2.3 + V2.4
  Day 6: V2.3 — ZAP scan composite + ZapNormalizer
  Day 7: V2.3 — Dashboard Runtime tab + DAST display
  Day 8: V2.3 — CVE re-check daily workflow
  Day 9: V2.4 — Alert + UptimeCheck entities + SMTP service
  Day 10: V2.4 — Sentry integration BE + FE
  Day 11: V2.4 — Dashboard Monitor tab + email test
  Day 12: V2.4 — Composite action notify-monitor + email throttling
  Day 13: Buffer fix bugs + integration test
  Day 14: Tag v0.2.0, update CHANGELOG, screencast V2 demo
```

Total **~70-80h** nếu làm nhẹ, ~100h nếu polish kỹ.

---

## Lý do chọn các tool

| Choice | Lý do |
|---|---|
| Render (CD) | Free tier ổn, GitHub-native deploy hook, không cần credit card |
| OWASP ZAP (DAST) | Industry standard, OSS, GitHub Action có sẵn, demo dễ |
| SMTP Gmail App Password (alert) | Free, không cần SendGrid/Mailgun account, 500 email/day đủ thesis |
| Sentry free (error) | 5k events/month đủ thesis, SDK Python+JS mature |
| GitHub Actions cron (uptime) | Reuse hạ tầng đã có, không cần UptimeRobot account riêng |
| Cron daily CVE re-check | Không real-time nhưng đủ cho compliance + alert fatigue |

---

## Anti-pattern tránh ở V2

1. **Đừng auto-deploy production** — V2 chỉ staging. Production deploy = manual approval. Lý do: thesis demo chỉ chứng minh shift-left, production deploy là responsibility lớn.

2. **Đừng làm DAST full scan trên CI** — chậm 15+ phút, block CI. Schedule daily là đủ.

3. **Đừng spam alert** — throttle 1 email/severity/15min. Email fatigue làm user disable alert hoàn toàn.

4. **Đừng wire Sentry production-grade ngay** — chỉ basic init + capture, không session replay/tracing performance (overkill).

5. **Đừng support nhiều cloud platform CD** — Render là enough cho thesis. Document Fly.io/Koyeb để team khác chọn, không build adapter.

6. **Đừng mix DAST findings vào Vulnerabilities tab** — `category=dast` riêng, page Runtime riêng. Khác nature (runtime vs static).

---

## Risk register

| Risk | Mitigation |
|---|---|
| Render cold start lúc demo | Pre-warm bằng cron ping mỗi 10 phút trước demo |
| ZAP scan timeout (>15 phút full) | Default `baseline` mode (5 phút), full opt-in |
| Gmail SMTP rate limit | Throttle 500/day là đủ; nếu vượt fallback sang SendGrid free |
| Sentry quota 5k/month exceed | Sample rate 0.1 cho production; thesis demo không cần full |
| Composite action breaking change | Pin version `@v2.0.1`, semver discipline |
| GitHub Actions minutes free tier (2000/month) | Daily cron = ~30 runs/month × ~5 phút = 150 phút. Có dư |

---

## Quyết định pending — cần mày confirm

1. **Domain custom** cho dashboard demo? (Hiện ngrok URL, V2 cần URL ổn định cho Render webhook). Options:
   - Cloudflare Tunnel + domain mày sẵn có
   - Render có domain `*.onrender.com` cho dashboard luôn
   - Mua domain $10/năm

2. **Inheritor repo Java sample** — fork ALOUTE hay tạo mới?
   - Fork ALOUTE: nhanh, có data thật
   - Repo mới: clean, không legacy CI

3. **DAST scan target** — staging URL ALOUTE deploy ở đâu?
   - Đã chốt Render → URL `https://aloute-staging.onrender.com`
   - Cần build Dockerfile cho ALOUTE (Spring Boot có sẵn)

---

## Roadmap kế tiếp sau V2

V3 sẽ là Phase A + C của NEXT-PHASES.md (multi-tenant runtime + AI improvements). V2 lock down "DevSecOps platform" dimension; V3 lock down "AI moat" dimension.

V2 ship xong → portfolio rất pro. Đóng dấu thesis defense lần 2 (nếu mày cần) hoặc commercial conversation đầu tiên với team VN nhỏ.
