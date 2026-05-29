# 07 — Chuyển sang MySQL

Hiện codebase support **SQLite (dev) + Postgres (Render prod)**. Đây là kế hoạch
chuyển sang **MySQL** làm DB chính (vd. MySQL 8.0 / MariaDB 10.6+).

## 7.1 Verdict: chuyển được, scope nhỏ

SQLAlchemy 2.0 đã abstract phần lớn khác biệt. Code app **không cần đổi**, chỉ
6 vị trí cụ thể trong infra/config/types cần điều chỉnh. Test suite 305/305
phải pass lại với MySQL fixture.

## 7.2 Tóm tắt các điểm cần đổi

| # | Vị trí | Thay đổi |
|---|--------|---------|
| 1 | `requirements.txt` | Thêm driver async `aiomysql` (hoặc `asyncmy`); có thể giữ `asyncpg`/`aiosqlite` cho dev parity |
| 2 | `core/config.py:_normalize_database_url` | Thêm nhánh rewrite `mysql://` → `mysql+aiomysql://` |
| 3 | `models/entities.py` | DT_TZ ⇒ MySQL không có TIMESTAMP WITH TIME ZONE → switch sang `TIMESTAMP` UTC convention + app-side tz handling; hoặc dùng `DATETIME(6)` |
| 4 | `core/db.py` migration helpers | Thay query `information_schema` Postgres-flavor bằng MySQL flavor (cú pháp tương tự, type name khác) |
| 5 | Index trên `String(1024)` | MySQL InnoDB key prefix limit (3072 bytes utf8mb4 = 768 chars) → cần short index hoặc rút length |
| 6 | Charset / collation | `CREATE TABLE … DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci` cho Unicode message + Vietnamese |

## 7.3 Driver lựa chọn

| Driver | Maintained | Note |
|--------|-----------|------|
| **`asyncmy`** (recommended) | ✅ active 2024+, Cython | Drop-in replacement, perf tốt hơn aiomysql |
| `aiomysql` | maintenance mode | Pure Python, ổn nhưng chậm hơn |

`requirements.txt` patch:
```diff
 # Database
 sqlalchemy>=2.0.0
 aiosqlite>=0.20.0
-asyncpg>=0.30.0
+asyncpg>=0.30.0          # giữ nếu cần parity với Render
+asyncmy>=0.2.9           # MySQL async driver
```

URL connection:
```
mysql+asyncmy://user:pass@host:3306/dbname?charset=utf8mb4
```

## 7.4 Patch `_normalize_database_url`

`core/config.py`:
```python
@field_validator("DATABASE_URL", mode="after")
@classmethod
def _normalize_database_url(cls, v: str) -> str:
    if not v:
        return v
    if v.startswith("postgres://"):
        return "postgresql+asyncpg://" + v[len("postgres://"):]
    if v.startswith("postgresql://") and "+asyncpg" not in v:
        return "postgresql+asyncpg://" + v[len("postgresql://"):]
    # MySQL
    if v.startswith("mysql://") and "+asyncmy" not in v and "+aiomysql" not in v:
        return "mysql+asyncmy://" + v[len("mysql://"):]
    return v
```

## 7.5 Cột timezone — quyết định quan trọng

MySQL **không có** kiểu `TIMESTAMP WITH TIME ZONE`. 2 cách:

### Option A — `TIMESTAMP` (recommended)
- MySQL `TIMESTAMP` lưu UTC, auto-convert theo `time_zone` session.
- Set `time_zone = '+00:00'` ở connection pool → giống Postgres TIMESTAMP WITH TIME ZONE.
- SQLAlchemy `DateTime(timezone=True)` map sang `TIMESTAMP` trên MySQL — **không cần đổi `DT_TZ` singleton**.
- Range: 1970-01-19 → 2038-01-19 (32-bit). **Đủ cho thesis scope**.

Cách set session tz trong driver:
```python
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
    connect_args={"init_command": "SET time_zone='+00:00'"},
)
```

### Option B — `DATETIME(6)` + app-side UTC
- Range rộng hơn (year 1000 → 9999), nhưng MySQL coi DATETIME là naive.
- Phải dùng `String` hoặc custom TypeDecorator để serialize UTC.
- Phức tạp hơn — chỉ chọn nếu cần lưu timestamp xa (audit log nhiều năm).

→ **Khuyến nghị Option A.**

## 7.6 BigInteger, JSON, Float — không thay đổi

| Type Python | MySQL DDL sau khi map |
|-------------|----------------------|
| `Integer` | `INT` |
| `BigInteger` | `BIGINT` ✅ (run_id 64-bit OK) |
| `String(N)` | `VARCHAR(N)` |
| `Text` | `TEXT` |
| `Float` | `FLOAT` |
| `JSON` | `JSON` ✅ (MySQL 5.7+ native, 8.0 tốt hơn) |
| `DateTime(timezone=True)` | `TIMESTAMP` (Option A) |

## 7.7 Index trên VARCHAR dài — gotcha lớn

`Finding.file_path` đang là `String(1024)`. InnoDB utf8mb4 cần 4 bytes/char,
prefix index limit 3072 bytes ≈ 768 chars cho row format DYNAMIC. Nếu bạn
thêm index trên `file_path`, phải prefix-index:

```python
file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
# Nếu cần index:
__table_args__ = (Index("ix_finding_file_path", file_path, mysql_length=255),)
```

Hiện tại không có index trên `file_path` → **không cần làm gì**. Các cột đang
indexed (`dedup_hash` 64 chars, `github_artifact_id` 255, `github_run_id` BIGINT) đều OK.

## 7.8 Charset & collation

Bắt buộc cho data tiếng Việt (Finding.message, AnalysisResult.explanation_vi):

```sql
CREATE DATABASE chat_system
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;
```

SQLAlchemy table args để force tất cả table:
```python
class Base(DeclarativeBase):
    __table_args__ = {
        "mysql_charset": "utf8mb4",
        "mysql_collate": "utf8mb4_0900_ai_ci",
    }
```

## 7.9 Migration helpers (`core/db.py`)

`_needs_tz_migration` + `_needs_bigint_migration` hiện check `data_type` Postgres
qua `information_schema`. MySQL có schema tương tự nhưng tên type khác:

```python
def _needs_tz_migration(sync_conn) -> bool:
    if sync_conn.dialect.name == "postgresql":
        # existing logic
        ...
    if sync_conn.dialect.name == "mysql":
        dtype = _mysql_column_type(sync_conn, "projects", "created_at")
        if dtype is None:
            return False
        # MySQL trả 'timestamp' hoặc 'datetime'. Nếu là 'datetime' → cần migrate
        return dtype.lower() != "timestamp"
    return False


def _mysql_column_type(sync_conn, table: str, column: str) -> str | None:
    from sqlalchemy import text
    row = sync_conn.execute(
        text(
            "SELECT DATA_TYPE FROM information_schema.columns "
            "WHERE TABLE_SCHEMA = DATABASE() "
            "AND TABLE_NAME = :t AND COLUMN_NAME = :c"
        ),
        {"t": table, "c": column},
    ).first()
    return row[0] if row else None
```

`_migrate_schema` (additive ALTER) đã neutral — dùng `TEXT`, `VARCHAR`, `DATETIME` — chạy được trên cả 3 DB.

## 7.10 Bool storage (active flag)

Comment trong `Project.active`:
> asyncpg không tự coerce bool → INTEGER → store INT 0/1

MySQL chấp nhận `BOOLEAN` alias → `TINYINT(1)`, không cần workaround. Nhưng
**giữ `Mapped[int]`** vì:
- Đảm bảo cross-DB compat (SQLite + Postgres + MySQL cùng row format)
- Không break test fixture hiện có

## 7.11 Docker compose patch

```yaml
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_DATABASE: chat_system
      MYSQL_ROOT_PASSWORD: rootpw
      MYSQL_USER: mcp
      MYSQL_PASSWORD: mcppw
    command: >
      --character-set-server=utf8mb4
      --collation-server=utf8mb4_0900_ai_ci
      --default-time-zone=+00:00
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql

  mcp:
    # ... existing config
    environment:
      DATABASE_URL: mysql+asyncmy://mcp:mcppw@mysql:3306/chat_system?charset=utf8mb4
    depends_on:
      - mysql

volumes:
  mysql_data:
  mcp_data:
```

## 7.12 Test suite

`tests/conftest.py` hiện dùng SQLite in-memory:
```python
DATABASE_URL = "sqlite+aiosqlite:///:memory:"
```

Để test trên MySQL CI, có 2 cách:
1. **Giữ SQLite cho unit test** (nhanh), chạy 1 lượt integration test trên MySQL container CI (`services: mysql:8.0` trong GitHub Actions).
2. Chuyển toàn bộ test sang MySQL: chậm hơn ~5×, nhưng catch sớm bug DB-specific.

→ **Option 1** đủ cho thesis scope.

## 7.13 Checklist migrate

```
[ ] Tạo MySQL 8.0 instance (Docker hoặc managed)
[ ] CREATE DATABASE với utf8mb4 + collation
[ ] CREATE USER + GRANT
[ ] Pip install asyncmy
[ ] requirements.txt thêm asyncmy
[ ] core/config.py: thêm nhánh mysql:// trong _normalize_database_url
[ ] core/db.py: engine connect_args set time_zone=+00:00
[ ] core/db.py: extend _needs_tz_migration cho MySQL
[ ] models/entities.py: thêm __table_args__ Base với mysql_charset utf8mb4
[ ] .env: DATABASE_URL=mysql+asyncmy://...
[ ] uvicorn start → kiểm CREATE TABLE thành công
[ ] pytest tests/ -q (SQLite vẫn pass)
[ ] Integration test 1 luồng webhook → ingest → query (verify TZ correct)
[ ] Backup data cũ (nếu có) → mysqldump
[ ] Update render.yaml nếu đẩy MySQL lên prod
```

## 7.14 Cân nhắc: có nên chuyển không?

| Lý do chuyển | Lý do giữ Postgres |
|--------------|--------------------|
| MySQL phổ biến hơn (host VN nhiều hơn) | Postgres JSON ops mạnh hơn (jsonb path query) |
| Quen thuộc hơn cho thầy/sinh viên VN | Render free Postgres đã có sẵn |
| Driver `asyncmy` ổn định | `asyncpg` đã wire xong, không có lý do break |
| MySQL tooling (phpMyAdmin, Workbench) dễ | — |

**Nếu chỉ vì preference cá nhân/môi trường host**: chuyển dễ, ~1 buổi việc + test.  
**Nếu muốn giữ Render free**: stick với Postgres.

## 7.15 Patch tối thiểu để test thử

Nếu muốn validate trước khi commit migration đầy đủ, đây là patch nhỏ nhất
để run MySQL local:

```diff
# requirements.txt
+asyncmy>=0.2.9

# core/config.py — _normalize_database_url
+    if v.startswith("mysql://") and "+asyncmy" not in v and "+aiomysql" not in v:
+        return "mysql+asyncmy://" + v[len("mysql://"):]

# core/db.py — create_async_engine
 engine = create_async_engine(
     settings.DATABASE_URL,
     echo=settings.APP_ENV == "development",
+    connect_args=(
+        {"init_command": "SET time_zone='+00:00'"}
+        if settings.DATABASE_URL.startswith(("mysql+", "mysql:"))
+        else {}
+    ),
 )

# .env
-DATABASE_URL=sqlite+aiosqlite:///./mcp.db
+DATABASE_URL=mysql+asyncmy://mcp:mcppw@localhost:3306/chat_system?charset=utf8mb4
```

Chạy:
```powershell
docker run -d --name mysql8 -p 3306:3306 -e MYSQL_ROOT_PASSWORD=rootpw -e MYSQL_DATABASE=chat_system -e MYSQL_USER=mcp -e MYSQL_PASSWORD=mcppw mysql:8.0 --default-time-zone=+00:00
uvicorn src.main:app --reload --port 8000
```

Verify schema:
```sql
USE chat_system;
SHOW TABLES;
DESC projects;
DESC findings;
```

Nếu thấy 9 bảng + `created_at TIMESTAMP NULL` + `last_processed_run_id BIGINT` → migration thành công.

## 7.16 Gotcha XAMPP: port confusion

**Port của Apache (URL phpMyAdmin) ≠ port của MySQL.**

- `http://localhost:8888/phpmyadmin/` → port 8888 là **Apache (httpd)**.
- mysqld vẫn listen ở port 3306 (default) hoặc bất kỳ port nào set trong `xampp/mysql/bin/my.ini` `[mysqld] port=...`.

Cách kiểm tra port MySQL thực:
```powershell
Get-NetTCPConnection -State Listen | ForEach-Object {
  $p = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue
  if ($p.ProcessName -match 'mysql|maria') { "$($_.LocalPort) $($p.ProcessName)" }
}
```

→ Connection string phải dùng port của mysqld, không phải port phpMyAdmin URL.

## 7.17 Kết quả thực tế (verified)

Patch áp dụng đã chạy được:
- DB engine: `MariaDB 10.4.32` (XAMPP bundled)
- 9 bảng auto-create: `alerts`, `app_config`, `artifacts`, `command_feedback`, `findings`, `projects`, `project_members`, `suppression_rules`, `uptime_checks`
- Tất cả `utf8mb4_unicode_ci` (qua `Base.__table_args__`)
- Session `@@time_zone = '+00:00'` (qua `_engine_connect_args` SET init_command)
- `init_db()` chạy `Base.metadata.create_all` + `_migrate_schema` không lỗi
