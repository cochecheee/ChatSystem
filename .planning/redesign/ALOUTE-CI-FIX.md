# ALOUTE CI allow-failure → unblock deploy

**Repo**: `cochecheee/SAST_CICD` (ALOUTE Spring Thymeleaf RCE)
**Date**: 2026-05-16
**Goal**: ALOUTE CI vẫn deploy (CD job chạy) dù 1 SAST tool fail. Không block defense demo.

## Strategy options

| # | Cách | Pros | Cons |
|---|---|---|---|
| A | Tìm step stuck → `continue-on-error: true` trong sast-suite | Root cause fix, vẫn báo về mcp | Phải đọc CI log |
| B | Pin gate threshold cực cao (`gate_fail_on_critical=999`) trong caller | 1-line patch | Mọi inheritor đều đi qua nếu vô tình copy |
| C | Caller workflow set `continue-on-error: true` toàn job | Đơn giản nhất | Mất signal hoàn toàn |

→ Đề xuất **A** với fallback **B** nếu hết thời gian.

## Steps

| # | Việc | Status |
|---|---|---|
| 1 | Đọc CI log ALOUTE gần nhất, identify step stuck | TODO |
| 2 | Patch `sast-action` composite hoặc `SAST_CICD/.github/workflows/security.yml` | TODO |
| 3 | Commit + push, trigger CI ALOUTE | TODO |
| 4 | Verify: CD job chạy, mcp ingest findings ALOUTE | TODO |

## Verify

```bash
gh run list --repo cochecheee/SAST_CICD --limit 1
gh run watch <run-id> --repo cochecheee/SAST_CICD
curl -s https://mcp-l958.onrender.com/findings | jq '[.[] | select(.artifact.run.project.name | contains("SAST_CICD"))] | length'
```
