# MCP Server — Anthropic Model Context Protocol

> V2.7 — báo cáo tiến độ docx ch.3.2. Code: `mcp/src/mcp_server.py`.

## Bản chất

Project có **2 protocol cùng truy cập 1 codebase + DB**:

| Protocol | Process | Client | Mục đích |
|---|---|---|---|
| REST HTTP (FastAPI) | `uvicorn src.main:app --port 8000` | React dashboard, curl, CI webhook | UI + integration |
| **MCP** (Anthropic) | `python -m src.mcp_server` | Claude Desktop, Cursor, Continue, MCP Inspector | AI agent natural-language access |

2 process khác nhau, cùng đọc/ghi `mcp.db` (SQLite) hoặc Render Postgres. Không có khoá độc quyền → có thể chạy song song.

## 8 Tool đã expose

| Tool | Mô tả | Mutate DB? |
|---|---|---|
| `list_findings` | Filter theo severity / category / status / tool / query | No |
| `get_finding` | Detail 1 finding kèm `ai_analysis` | No |
| `explain_finding` | Trigger Gemini phân tích VI + remediation diff | Yes (cache) |
| `approve_finding` | Mark APPROVED + audit trail mcp:security_lead | Yes |
| `revoke_finding` | Thu hồi approve + audit trail | Yes |
| `list_pipelines` | GitHub Actions workflow runs | No |
| `get_stats_overview` | KPI tổng (severity / status / tool / category breakdown) | No |
| `trigger_scan` | Dispatch GitHub workflow | No (gọi GitHub API) |

Audit trail: action mutate ghi `submitted_by=mcp:security_lead` hoặc `approved_by=mcp:security_lead` để phân biệt với UI/CI caller.

## Cách chạy

### Stdio (mặc định — Claude Desktop launch subprocess)

```bash
cd D:\School\DoAnTotNghiep\chat-system\mcp
.\.venv\Scripts\activate
python -m src.mcp_server
```

Process treo lắng nghe stdin/stdout. Không in gì khi healthy.

### HTTP + SSE (MCP Inspector / debug)

```bash
python -m src.mcp_server --transport http --port 8765
```

Server listen `http://localhost:8765/mcp`. Mở MCP Inspector `npx @modelcontextprotocol/inspector` rồi nhập URL.

## Claude Desktop config

Edit `claude_desktop_config.json` (Windows: `%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "sast-chat": {
      "command": "D:\\School\\DoAnTotNghiep\\chat-system\\mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "src.mcp_server"],
      "cwd": "D:\\School\\DoAnTotNghiep\\chat-system\\mcp",
      "env": {
        "DATABASE_URL": "sqlite+aiosqlite:///D:/School/DoAnTotNghiep/chat-system/mcp/mcp.db",
        "GITHUB_TOKEN": "<your PAT>",
        "GITHUB_OWNER": "cochecheee",
        "GITHUB_REPO": "sample-python",
        "GEMINI_API_KEY": "<your key>",
        "GEMINI_MODEL": "gemini-2.5-flash"
      }
    }
  }
}
```

Restart Claude Desktop → tool icon trên chat input hiện 8 tool. Hỏi:

> "Show me critical findings from the latest scan"

→ Claude tự gọi `get_stats_overview` rồi `list_findings(severity="critical")` rồi format kết quả.

> "Approve finding #5 — đây là false positive vì input đã được sanitize ở UserService.cleanInput()"

→ Claude tự gọi `approve_finding(finding_id=5, justification=...)`.

## Verify

```bash
# Unit test 13 case
.\.venv\Scripts\python.exe -m pytest tests/test_mcp_server.py -v

# Stdio smoke (kết thúc Ctrl+C — không có output là OK)
.\.venv\Scripts\python.exe -m src.mcp_server

# HTTP smoke
.\.venv\Scripts\python.exe -m src.mcp_server --transport http --port 8765 &
curl -N -H "Accept: text/event-stream" http://localhost:8765/mcp
```

## Bảo mật

- **No auth ở stdio** — Claude Desktop launch subprocess local, không qua network. OK cho dev.
- **HTTP transport KHÔNG có auth** — chỉ nên expose `localhost`. Khi cần expose qua tunnel/Render, thêm reverse-proxy với auth riêng. Roadmap v0.3 add OAuth ở MCP server.
- **Guardrails 4-layer (xem `docs/guardrails.md`)** apply cho `explain_finding` qua `LLMAnalysisService` — content scrub + injection check trước khi gửi Gemini.
- **Audit trail**: mọi mutate action ghi `mcp:<role>` → distinguishable từ human action.

## Limitations

- Mỗi tool tạo `AsyncSessionLocal` riêng → không transaction cross-tool. Acceptable vì tool granularity = 1 action.
- `list_findings` cap 200 row mỗi call → client phải pagination chia nhiều call nếu cần.
- Không stream LLM response trong MCP transport → `explain_finding` block đến khi Gemini xong (~5-10s).

## Defense talking points (báo cáo ch.3.2)

- **Why MCP**: REST API mỗi tool integration phải viết custom code; MCP chuẩn hoá → 1 server expose, N AI client connect (Claude Desktop, Cursor, Continue, agent tự built).
- **Demo flow**: Dashboard hiển thị findings; Claude Desktop kết nối cùng DB qua MCP → dev hỏi "explain finding 5", "approve nếu rule này có false positive history" → AI gọi đúng tool, MCP server xử lý qua existing service + guardrail layer.
- **3 khái niệm cốt lõi MCP** (resources / tools / prompts) — implementation hiện chỉ dùng **tools** (action + read). Roadmap v0.3 có thể thêm **resources** (expose findings list dạng URI: `finding://5`) và **prompts** (template "explain this finding for a junior dev").
