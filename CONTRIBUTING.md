# Contributing to chat-system

Cảm ơn đã dành thời gian. Tài liệu này mô tả workflow team — đọc 5 phút, làm được PR đầu tiên.

## 1. Setup môi trường

Project chia 2 nửa:

- **Backend** (`mcp/`) — FastAPI + SQLAlchemy + Alembic. Xem [`mcp/docs/setup.md`](mcp/docs/setup.md).
- **Frontend** (`dashboard/`) — React 19 + TypeScript + Vite. Xem [`dashboard/README.md`](dashboard/README.md).

Quy trình tóm tắt:

```bash
git clone <repo>
cd chat-system

# Backend
cd mcp
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env       # điền GITHUB_TOKEN, GEMINI_API_KEY, SECRET_KEY
uvicorn src.main:app --reload --port 8000

# Frontend (terminal khác)
cd dashboard
npm install
cp .env.local.example .env.local   # nếu file example chưa có, set VITE_API_URL=http://localhost:8000
npm run dev
```

Mở `http://localhost:5173`. Login user dev mặc định trong `mcp/docs/setup.md`.

## 2. Branch convention

Branch luôn tạo từ `master` (hoặc `main`):

| Prefix | Dùng khi | Ví dụ |
|---|---|---|
| `ft/` | Thêm tính năng | `ft/finding-bulk-revoke` |
| `fix/` | Sửa bug | `fix/project-context-reload-loop` |
| `refactor/` | Đổi code, không đổi behavior | `refactor/split-artifacts-router` |
| `docs/` | Chỉ doc | `docs/architecture-diagram` |
| `chore/` | Build / CI / dependency / tooling | `chore/bump-fastapi` |
| `test/` | Thêm/sửa test | `test/llm-service-retry` |

Đặt tên ngắn, kebab-case, mô tả kết quả chứ không mô tả task.

## 3. Commit message

Theo [Conventional Commits](https://www.conventionalcommits.org/). Format:

```
<type>(<scope>): <subject>

<body — optional, mô tả WHY>
```

`<type>` trùng với prefix branch (`feat`, `fix`, `refactor`, `docs`, `chore`, `test`).
`<scope>` là module hoặc area (vd `mcp`, `fe`, `auth`, `llm`, `v3.6`). Tuỳ chọn.

Ví dụ:

```
feat(fe): mark finding as not-a-bug + suppression shortcut

Wires V3.1 4-tier FP loop into Vulnerabilities detail pane.
Previously the only way to revoke was via ChatOps slash command.

fix(auth): require explicit project_id when RBAC_PER_PROJECT=true

chore(ci): bump python setup-python to v5
```

Một commit = một thay đổi logic. Đừng nhét sửa typo + refactor + feature vào 1 commit.

## 4. Code style

### Backend (Python)

- Lint qua **Ruff**: `cd mcp && ruff check .` (CI gate này — phải sạch).
- Format tuỳ chọn: `ruff format .` (chưa enforce trong CI; chạy nếu muốn cho gọn).
- Type-check qua **mypy** (chỉ strict cho `core/`, `repositories/`, `services/llm/`): `mypy src`
- Quy ước: `snake_case`, type hint trên function signature, `from __future__ import annotations` đầu file, async-first.
- Config trong `mcp/pyproject.toml` — không cần `.flake8`/`black.cfg`.

> **Baseline carve-out**: `pyproject.toml` tạm `ignore` ~21 rule (B904, SIM*, N806, E402, RUF003 unicode tiếng Việt...) vì code có sẵn vi phạm. CI chỉ gate code mới qua các rule còn bật. Khi sửa file nào, dọn vi phạm của file đó rồi gỡ dần entry trong `ignore`. Đừng thêm rule mới vào `ignore` cho code mình viết.

### Frontend (TypeScript)

- Format qua **Prettier**: `cd dashboard && npm run format` (sửa) hoặc `npm run format:check` (chỉ check).
- Lint qua **ESLint**: `npm run lint`.
- Type-check + build: `npm run build` (chạy `tsc -b` trước).
- Quy ước: file `PascalCase.tsx` cho component, `camelCase.ts` cho hook/util, single-quote, semicolon, 2-space indent.

CI sẽ chạy tất cả các check trên — nếu fail thì PR không merge được.

## 5. Test policy

Trước khi mở PR:

- **Sửa BE logic** → thêm/cập nhật `pytest` trong `mcp/tests/`. Chạy `pytest -q` trước khi push.
- **Sửa FE hook hoặc data flow** → cập nhật Playwright spec trong `dashboard/tests/e2e/` (Vitest unit test sẽ thêm sau).
- **Sửa schema** → thêm migration Alembic trong `mcp/migrations/versions/`, test `init_db()` chạy không lỗi.

Nếu bug không có test cover, viết test reproduce bug TRƯỚC khi fix.

## 6. PR workflow

1. Push branch lên remote: `git push -u origin <branch>`.
2. Mở PR trên GitHub, base = `master`. Template tự fill.
3. Điền checklist + cách verify cho reviewer.
4. CI phải xanh. Ít nhất 1 approval.
5. Squash & merge (giữ commit history main gọn) — trừ khi PR có nhiều commit logic độc lập.

## 7. Đừng làm

- **Đừng commit secret**: token, password, API key. `.env*` đã trong `.gitignore` — đừng `git add -f`.
- **Đừng force-push** lên `master`. Force-push lên branch riêng của mày OK.
- **Đừng skip CI hook** với `--no-verify` trừ khi đã hỏi maintainer.
- **Đừng xoá test cũ** chỉ vì nó fail — fix code hoặc thảo luận trong PR.
- **Đừng over-engineer**: cleanup hôm khác, đừng nhét vào PR feature.

## 8. Có thắc mắc?

- Lỗi setup → mở issue với template "Bug report".
- Idea mới → mở issue với template "Feature request" để bàn trước khi code.
- Tham khảo architecture: `mcp/docs/`, `README.md` section "Kiến trúc".
