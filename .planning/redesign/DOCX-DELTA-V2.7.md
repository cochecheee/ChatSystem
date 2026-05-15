# Docx Delta — Phần thêm vào báo cáo tiến độ 2

> Tài liệu này chứa **văn bản cần paste vào Word docx** để khớp giữa
> báo cáo tiến độ và implementation V2.7. Mở `Nhom04_BaoCaoTienDo1_fixed_1.docx`,
> sao chép từng section dưới đây vào vị trí chỉ định, định dạng theo
> heading style hiện có.

---

## Insert sau section 4.5 — section 4.6 mới

### 4.6. Quyết định kiến trúc bổ sung — tách 3 repo (V2.1.3)

Trong quá trình hiện thực, hệ thống đã được tái cấu trúc từ **kho mã đơn nhất** (theo thiết kế ban đầu trong mục 4.1) sang **kiến trúc 3 kho mã độc lập** nhằm hỗ trợ mô hình template hoá:

| Kho | URL | Vai trò |
|---|---|---|
| `chat-system` | `github.com/cochecheee/ChatSystem` | Backend `mcp/` (FastAPI + MCP) + Dashboard `dashboard/` (React) + render.yaml |
| `sast-action` | `github.com/cochecheee/sast-action` | Thư viện GitHub Actions tái sử dụng (composite + reusable workflow) |
| `sample-python` | `github.com/cochecheee/sample-python` | Inheritor mẫu (Flask vulnerable demo) |

#### Lý do tách

1. **Tái sử dụng**: Một dashboard `chat-system` có thể phục vụ nhiều
   repository inheritor (Java, Python, Node, Go). Thư viện
   `sast-action` được tham chiếu qua `uses: cochecheee/sast-action@v0.2.0`
   trong workflow của inheritor — chỉ 10 dòng cấu hình.
2. **Versioning độc lập**: Thay đổi composite action không ảnh hưởng
   backend mcp; ngược lại nâng cấp mcp không yêu cầu inheritor sync.
3. **Bảo mật**: Inheritor không cần access source code mcp; chỉ giao
   tiếp qua webhook + secret token.

#### Liên hệ với mô hình kiến trúc gốc

Mặc dù tách kho, 6 thành phần kiến trúc trong mục 4.1 vẫn được giữ
nguyên về mặt logic. Cụ thể, "MCP Server" và "LLM Orchestrator" vẫn
nằm trong thư mục `mcp/` của kho `chat-system`; "CI/CD Pipeline" được
hiện thực bởi reusable workflow trong `sast-action`; "Web Dashboard"
là thư mục `dashboard/` của `chat-system`. Mô hình triển khai 3 kho
chỉ là phân vùng vật lý cho mã nguồn, không thay đổi luồng dữ liệu
end-to-end trong mục 4.5.

---

## Insert sau section 4.6 — section 4.7 mới

### 4.7. Mở rộng vượt phạm vi ban đầu

Phạm vi nghiên cứu ban đầu (mục 2.1.3) lựa chọn **kiểm thử bảo mật
tĩnh** (SAST) làm phương pháp trọng tâm. Tuy nhiên, trong quá trình
hiện thực, ba thành phần mở rộng đã được bổ sung để hệ thống tiệm
cận quy trình DevSecOps hoàn chỉnh.

#### 4.7.1. CD — Triển khai tự động sang môi trường staging (V2.2)

Sau khi SAST và Security Gate (mục 4.2.3) cho phép pipeline tiếp tục,
một job `cd` được thêm vào reusable workflow để:

1. Đăng nhập Docker Hub, build image qua `docker buildx`, đính kèm
   Trivy image scan;
2. Push image với hai tag `<commit-sha>` và `latest`;
3. Gửi POST tới Render Deploy Hook URL để kích hoạt redeploy staging.

Vai trò: chứng minh rằng artifact đã qua SAST và Security Gate có thể
được triển khai an toàn — đóng kín vòng "shift-left → automated
deploy" mà mô hình truyền thống không có.

#### 4.7.2. DAST — Kiểm thử bảo mật động bổ sung (V2.3)

Sau khi staging được triển khai, một job `dast` chạy OWASP ZAP
baseline scan trong khoảng 5 phút đối với URL staging. Kết quả ZAP
JSON được đẩy về MCP Gateway thông qua webhook và được hiển thị
trong tab "Runtime" của dashboard với danh mục `category=dast`.

Lý do bổ sung: dù phạm vi nghiên cứu tập trung SAST, việc thực nghiệm
cho thấy một số lỗ hổng (cấu hình HTTP header, SSRF, IDOR runtime)
chỉ phát hiện được khi ứng dụng đang chạy. DAST đóng vai trò bổ trợ
SAST (không thay thế) — đúng tinh thần Defense-in-Depth.

#### 4.7.3. Monitor — Uptime check + alert (V2.4)

Một background loop ping staging URL mỗi 5 phút, lưu kết quả vào
bảng `uptime_checks`, và phát Alert nếu service down ≥ 2 lần liên
tiếp. Email alert được gửi qua SMTP (Mailtrap sandbox cho dev,
Gmail App Password cho production). Sentry hook ghi nhận exception
tự động khi `SENTRY_DSN` được cấu hình.

Lý do bổ sung: defense-in-depth không chỉ là kiểm thử trước triển
khai, mà còn cần observability sau triển khai để phát hiện regression
runtime.

#### 4.7.4. MCP Server thật (V2.7)

Trong khi mục 3.2 mô tả giao thức Anthropic Model Context Protocol,
phiên bản ban đầu của hệ thống chỉ hiện thực REST API gateway. Trong
phase V2.7, hệ thống bổ sung **MCP server thật** qua `fastmcp` SDK
(`mcp/src/mcp_server.py`), expose 8 tool wrap repositories + services
hiện có:

`list_findings`, `get_finding`, `explain_finding`, `approve_finding`,
`revoke_finding`, `list_pipelines`, `get_stats_overview`, `trigger_scan`.

Hai protocol cùng truy cập một cơ sở dữ liệu:

| Protocol | Entry point | Client | Mục đích |
|---|---|---|---|
| REST (FastAPI) | `uvicorn src.main:app` | Dashboard, CI webhook | UI + integration |
| MCP (Anthropic) | `python -m src.mcp_server` | Claude Desktop, Cursor | AI agent natural-language |

Cấu hình kết nối Claude Desktop được mô tả trong `docs/mcp-server.md`.

---

## Update bảng ChatOps (4.3.1) — bổ sung 1 dòng

Bảng "Chi tiết ChatOps Commands" trong section 4.3.1 hiện liệt kê 10
lệnh: `/status`, `/scan`, `/results`, `/explain`, `/fix`, `/rerun`,
`/approve`, `/report`, `/help`, `/feedback`. Implementation hiện
thực có thêm **/revoke**:

```
/revoke      | Action     | Thu hồi phê duyệt trước đó cho 1 finding khi có bằng chứng mới |
             |            | finding_id, justification (≥20 ký tự)                          |
             |            | /revoke FINDING-001 "Bằng chứng mới — bypass qua header X"     |
             |            | Security team lead role                                        |
```

Lý do thêm: chu trình audit yêu cầu cơ chế đảo ngược quyết định
`/approve` khi tình huống thay đổi (CVE mới được công bố, exploit
PoC xuất hiện trong tự nhiên).

---

## Update bảng SAST Tools (4.2.2) — chú thích CodeQL multi-language

Bảng "Phân tích chi tiết các SAST Tools được tích hợp" liệt kê CodeQL
với ngôn ngữ "JavaScript, TypeScript, Python, Java, C#, C++, Go, Ruby".
Implementation V2.7 wire CodeQL cho 4 ngôn ngữ chính của project:
`java`, `python`, `javascript` (mapped từ input `node`), `go`. C#,
C++, Ruby không thuộc scope inheritor hiện tại — có thể thêm tương
lai bằng cách extend `actions/sast-suite/action.yml`.

---

## Update mục 4.4.2 — chú thích layer 4-pipeline rõ ràng

Văn bản hiện tại: "Guardrail system hoạt động theo mô hình pipeline,
trong đó mỗi request đi qua bốn lớp bảo vệ tuần tự."

Bổ sung implementation reference cho từng layer:

| Layer | Tên | Module hiện thực |
|---|---|---|
| L1 | Authentication | `core/auth.py` (JWT HS256) + `main.py:_enforce_production_safety` |
| L2 | Schema validation | Pydantic models tại mọi POST + `COMMAND_ROLES` whitelist (`api/chat.py`) |
| L3 | Content sanitization | `core/guardrails.py:ScrubbingService` — detect-secrets + PII regex |
| L4 | Prompt security | `core/guardrails.py:InjectionGuardrail` — 9 pattern + truncate + sanitize |

24 test case trong `tests/test_guardrails_*.py` verify L3 + L4.
Auth + schema bypass tests nằm trong `tests/test_chat_api.py` (10+
case kiểm tra 401/403/422).

---

## Cập nhật mục 4.5 — Polling interval

Mục 4.5.1 step 14 hiện ghi "real-time polling (15s interval)". Đã
khớp với cấu hình `POLL_INTERVAL_MS = 15_000` ở
`dashboard/src/lib/constants.ts`. Backend GitHub workflow poller
(`POLLING_INTERVAL_SECONDS=300` trong render.yaml) là cơ chế khác —
fallback polling khi webhook fail — không nằm trong scope "real-time
dashboard polling".

Khuyến nghị bổ sung 1 câu chú thích vào mục 4.5 cho rõ:

> Lưu ý: 15 giây là chu kỳ polling của dashboard tới MCP REST API.
> Cơ chế polling GitHub Workflow API ở phía backend (làm việc với
> webhook làm primary, polling 300s là fallback) là tầng khác, không
> ảnh hưởng tới giao diện người dùng.
