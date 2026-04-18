# Phase 4: CI/CD Pipeline & SAST Integration - Research

**Researched:** 2026-04-16 (Updated)
**Domain:** Security CI/CD, SAST, GitHub Actions, Java/Gradle
**Confidence:** HIGH

## Summary

Phase 4 thiết lập pipeline bảo mật cho **Java target repo** (repo riêng), không phải chat-system repo. Pipeline chạy trên Java repo khi có Push/PR, quét bằng 5 SAST tools, upload kết quả lên GitHub Artifacts. MCP Gateway **polling** GitHub API định kỳ để phát hiện workflow run mới và fetch artifacts về xử lý.

**Primary recommendation:** Workflow YAML đặt trong Java repo. SpotBugs dùng Gradle plugin built-in SARIF (4.7.0+). MCP Gateway dùng background AsyncIO poller thay vì webhook để tránh phụ thuộc public URL.

## Architecture

```
[Java Repo — target]                    [chat-system repo]
 .github/workflows/security-scans.yml       mcp/src/services/poller.py
  ├─ semgrep     (Java + JS/TS)              │  polls every 5 min
  ├─ codeql      (java, javascript)          │  GET /repos/.../actions/runs
  ├─ eslint      (Thymeleaf static JS/TS)    │
  ├─ spotbugs    (Java — Gradle plugin)      │
  └─ dep-check   (Java + JS deps)            │
       │ upload artifacts                    │
       └──────── GitHub Artifacts ───────────┘
                                            fetch → normalize → enrich → store
```

## Standard Stack

### Core
| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| GitHub Actions | N/A | Pipeline Orchestration | Chạy trong Java repo |
| Semgrep | v1 | Polyglot SAST | Covers Java + JS/TS |
| CodeQL | v3 | Semantic Analysis (Java) | Needs `./gradlew build -x test` |
| ESLint | 9.x | Security Linting (JS/TS) | Thymeleaf static assets |
| SpotBugs | 4.8.3 | SAST Java | Via `com.github.spotbugs` Gradle plugin v6 |
| OWASP Dependency-Check | v1.1.0 | SCA | Java (Gradle) + JS deps |

### Supporting
| Tool | Purpose |
|------|---------|
| `jq` 1.7+ | SARIF parsing trong security gate script |
| `gh` CLI 2.x | PR commenting |
| `@microsoft/eslint-formatter-sarif` 3.1.0 | ESLint → SARIF output |
| `eslint-plugin-security` 4.0.0 | Security rules cho JS/TS |

## Architecture Patterns

### Pattern 1: SpotBugs SARIF via Gradle Plugin (Built-in)
**What:** SpotBugs 4.7.0+ hỗ trợ SARIF output trực tiếp qua Gradle plugin — không cần converter ngoài.
**Configuration trong `build.gradle` của Java repo:**
```gradle
plugins {
    id 'com.github.spotbugs' version '6.0.0'
}

spotbugs {
    toolVersion = '4.8.3'
    ignoreFailures = true  // Report findings, không fail build
}

spotbugsMain {
    reports {
        sarif {
            required = true
            outputLocation = layout.buildDirectory.file('reports/spotbugs/main.sarif')
        }
        html { required = false }
        xml  { required = false }
    }
}
```

### Pattern 2: CodeQL cho Java 21 + Gradle
```yaml
- name: Initialize CodeQL
  uses: github/codeql-action/init@v3
  with:
    languages: java, javascript
    java-version: '21'

- name: Build with Gradle (no tests)
  run: ./gradlew build -x test

- name: Perform CodeQL Analysis
  uses: github/codeql-action/analyze@v3
```

### Pattern 3: ESLint cho Thymeleaf Static Assets
```yaml
- name: Install ESLint
  working-directory: src/main/resources/static
  run: |
    npm init -y
    npm install --save-dev eslint @microsoft/eslint-formatter-sarif eslint-plugin-security

- name: Run ESLint
  working-directory: src/main/resources/static
  run: npx eslint js/ --format @microsoft/eslint-formatter-sarif --output-file eslint-results.sarif
  continue-on-error: true
```

### Pattern 4: MCP Polling Service (AsyncIO Background Task)
**What:** MCP Gateway chạy background task polling GitHub API mỗi 5 phút.
**When:** Thay vì webhook (cần public URL), polling hoạt động tốt trong môi trường local/dev.
```python
# mcp/src/services/poller.py
async def poll_github_runs():
    while True:
        await asyncio.sleep(300)  # 5 minutes
        runs = await github_client.get_latest_runs(owner, repo)
        for run in runs:
            if run.id > last_processed_run_id and run.status == "completed":
                await processor.process_run(run)
                update_last_processed_run_id(run.id)
```

### Anti-Patterns to Avoid
- **Polling quá nhanh:** Dưới 1 phút sẽ vượt GitHub API rate limit (1000 req/hour for authenticated).
- **Hard-failing individual tools:** Dùng `continue-on-error: true` cho tất cả scan steps.
- **Ignoring lockfiles:** Dependency-Check cần `package-lock.json` / `build.gradle` để scan transitive deps.

## Common Pitfalls

### Pitfall 1: CodeQL cần build thành công
**What goes wrong:** CodeQL analyze thất bại nếu `./gradlew build` lỗi.
**How to avoid:** Dùng `-x test` để bỏ qua tests, đảm bảo build clean trước khi chạy pipeline.

### Pitfall 2: SpotBugs cần compiled classes
**What goes wrong:** SpotBugs scan `.class` files, không phải source — phải build trước.
**How to avoid:** Đảm bảo `./gradlew classes` chạy trước `./gradlew spotbugsMain`.

### Pitfall 3: GitHub API Rate Limit cho Polling
**What goes wrong:** Polling quá thường xuyên → 403/429 từ GitHub API.
**How to avoid:** Interval tối thiểu 5 phút. Dùng `ETag` / `If-Modified-Since` header để conditional polling.

### Pitfall 4: Permissions Blindness
**What goes wrong:** `upload-sarif` hoặc `gh pr comment` thất bại với 403.
**How to avoid:** Khai báo explicit permissions trong workflow:
```yaml
permissions:
  contents: read
  security-events: write
  pull-requests: write
  actions: read
```

## Environment Variables (MCP Gateway)
```env
# Polling config
GITHUB_TOKEN=ghp_xxx
GITHUB_OWNER=your-org
GITHUB_REPO=java-target-repo
POLLING_INTERVAL_SECONDS=300
POLLING_WORKFLOW_NAME=Security Scans
```

## Validation Architecture

### Phase Requirements → Test Map
| Req ID | Behavior | How to Verify |
|--------|----------|---------------|
| REQ-4.1 | Trigger on Push/PR | Push to Java repo, check Actions tab |
| REQ-4.2 | 5 SAST Tools run | Check all jobs complete in Actions run |
| REQ-4.3 | Artifacts uploaded | Check Artifacts section in Actions run summary |
| REQ-4.4 | Security Gate blocks High/Critical | Add vulnerable code, verify gate fails |
| REQ-4.5 | MCP Poller fetches new runs | Check MCP logs after workflow completes |

## Sources

### Primary (HIGH confidence)
- [SpotBugs Gradle Plugin](https://github.com/spotbugs/spotbugs-gradle-plugin) - SARIF output docs
- [GitHub CodeQL Action](https://github.com/github/codeql-action) - Java + Gradle config
- [OWASP Dependency-Check Action](https://github.com/dependency-check/Dependency-Check_Action)
- [ESLint Formatter SARIF](https://github.com/microsoft/eslint-formatter-sarif)

**Research date:** 2026-04-16
**Valid until:** 2026-07-16
