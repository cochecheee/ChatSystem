# sast-chat-sample-python

> **⚠️ Vulnerable on purpose.** Intentionally insecure Flask app dùng để demo chat-system / sast-chat reusable workflow. Đừng deploy ra public.

App nhỏ (~80 LOC) cố ý chứa 5 lỗ hổng phổ biến để Bandit, Semgrep, Trivy phát hiện được.

---

## Lỗi cố ý (đừng "fix")

| # | Type | Location | Tool sẽ bắt |
|---|---|---|---|
| 1 | SQL Injection (raw f-string query) | `app.py:user_lookup` | Semgrep, Bandit B608 |
| 2 | Reflected XSS (Markup unsafe) | `app.py:greet` | Semgrep |
| 3 | Command Injection (os.system) | `app.py:ping` | Bandit B605/B607 |
| 4 | Hardcoded Secret | `app.py:SECRET_KEY` | Bandit B105 |
| 5 | SSRF (urlopen user URL) | `app.py:fetch_url` | Semgrep, Bandit B310 |
| 6 | Outdated dependency CVE | `requirements.txt:Flask==1.0` | Trivy, Safety |

---

## Run local

```bash
pip install -r requirements.txt
python app.py
# http://localhost:5000
```

Endpoints để test:
```bash
# SQL injection
curl "http://localhost:5000/user?id=1' OR '1'='1"

# XSS
curl "http://localhost:5000/greet?name=<script>alert(1)</script>"

# Command injection
curl "http://localhost:5000/ping?host=8.8.8.8;ls"

# SSRF
curl "http://localhost:5000/fetch?url=http://169.254.169.254/latest/meta-data/"
```

---

## Wire vào chat-system

`.github/workflows/security.yml` đã có sẵn — dùng reusable workflow của `cochecheee/sast-chat`.

Cần 2 GitHub Secrets ở repo này:
- `MCP_GATEWAY_URL` — chat-system instance public URL (ví dụ ngrok / Render)
- `MCP_WEBHOOK_TOKEN` — match `CI_WEBHOOK_TOKEN` chat-system .env

Push code → CI chạy → findings xuất hiện trong dashboard chat-system.

Xem `docs/inheritor-guide.md` của chat-system repo để biết chi tiết.

---

## License

MIT — sample code, không guarantee. Reuse cho thesis demo / education.
