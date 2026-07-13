#!/usr/bin/env python
"""Seed a self-contained DEMO project that exercises the whole V4.0/4.1/4.2
"Xử lý dữ liệu" (Processing) pipeline so it can be tried on the dashboard:

    Raw (nhiều tool)  →  Chuẩn hoá severity (V4.1)  →  Khử trùng lặp (V4.0)
                      →  AI: FP + grounding (V4.2)   →  Unique  →  Gate

It inserts realistic findings (multiple tools, some reporting the SAME vuln so
cross-tool dedup collapses them; a spread of label↔score severity signals so the
normaliser shows promotions/disagreements; and a few AI-analysed findings with
false-positive verdicts + a hallucinated/ungrounded fix), then runs the REAL
`SecurityProcessor._correlate_run_findings` so the `_correlation` provenance is
produced by production code, not hand-faked.

Idempotent: re-running wipes the demo project's findings/artifacts and reseeds.
Read the whole thing before running — it only touches the demo project.

Run from mcp/:
    .venv/Scripts/python.exe -m scripts.seed_demo_processing
"""
from __future__ import annotations

import asyncio
import hashlib
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402

from src.core.db import AsyncSessionLocal  # noqa: E402
from src.models.entities import (  # noqa: E402
    Artifact,
    CommandFeedback,
    Finding,
    FindingAction,
    Project,
)
from src.services.enricher import _SEVERITY_TO_CVSS  # noqa: E402
from src.services.normalizers.severity import resolve_severity  # noqa: E402
from src.services.processor import SecurityProcessor  # noqa: E402

PROJECT_NAME = "demo-xu-ly-du-lieu"
GITHUB_URL = "https://github.com/demo/xu-ly-du-lieu"
RUN_ID = 990101  # small, distinctive; endpoints scope by project_id anyway

# V4.3 — real source cached on a few findings so the chat "lỗi này có thật không?"
# investigation (/verify) can trace data flow OFFLINE (no GitHub fetch needed).
# The finding's `line` is set to the vulnerable line within these snippets.
SRC_SSRF = '''import requests
from flask import request, jsonify


def fetch_url():
    # Tải tài nguyên từ xa theo yêu cầu người dùng
    target = request.args.get("url")
    # KHÔNG có allowlist / kiểm tra URL người dùng nhập
    resp = requests.get(target, timeout=5)
    return jsonify({"status": resp.status_code, "body": resp.text[:2000]})
'''

SRC_TEST_FIXTURE = '''import pytest
from app.auth import login

# Thông tin đăng nhập CHỈ dùng cho bộ test — không phải secret thật.
TEST_USERNAME = "test_user"
TEST_PASSWORD = "password123"


def test_login_success(client):
    resp = client.post("/login", data={
        "username": TEST_USERNAME,
        "password": TEST_PASSWORD,
    })
    assert resp.status_code == 200


def test_login_wrong_password(client):
    resp = client.post("/login", data={
        "username": TEST_USERNAME,
        "password": "wrong",
    })
    assert resp.status_code == 401
'''


# --------------------------------------------------------------------------
# Severity provenance builder — mirrors normalizer(resolve_severity) + enricher
# (cvss_source) EXACTLY so the seeded `_severity` looks like a real ingest.
# --------------------------------------------------------------------------
def build_sev(
    *,
    raw_label: str | None = None,
    score: float | None = None,
    kind: str | None = None,
    dast_promote_to: str | None = None,
) -> tuple[str, float | None, dict]:
    res = resolve_severity(raw_label=raw_label, score=score, score_kind=kind)
    prov = res.provenance()
    normalized = res.severity

    if dast_promote_to:  # zap normalizer path: DAST raises the band
        normalized = dast_promote_to
        prov["normalized"] = normalized
        prov["source"] = "promoted-dast"
        prov["disagreement"] = False

    had_real_cvss = score is not None
    if had_real_cvss:
        cvss = score
        prov.setdefault("cvss_source", "tool")
    else:
        cvss = _SEVERITY_TO_CVSS.get(normalized.lower())
        if cvss is not None:
            prov["cvss_source"] = "derived-from-label"
            prov.setdefault("cvss", cvss)
        else:
            prov.setdefault("cvss_source", "none")
    return normalized, cvss, prov


def _hash(rule_id: str, file_path: str, message: str) -> str:
    return hashlib.sha256(f"{rule_id}:{file_path}:{message}".encode()).hexdigest()


# --------------------------------------------------------------------------
# AI analysis blocks (ai_analysis JSON = AnalysisResult shape)
# --------------------------------------------------------------------------
def ai_block(
    *,
    fid_placeholder: int,
    vuln_id: str,
    cwe: str,
    severity: str,
    fp: str,
    fp_reason: str,
    grounded: bool,
    grounded_note: str,
    confidence: str,
    explanation: str,
    impact: str,
    diff: str,
) -> dict:
    return {
        "finding_id": fid_placeholder,
        "vulnerability_id": vuln_id,
        "explanation_vi": explanation,
        "impact_vi": impact,
        "remediation_diff": diff,
        "severity": severity,
        "cwe_reference": cwe,
        "confidence": confidence,
        "false_positive_likelihood": fp,
        "false_positive_reason": fp_reason,
        "grounded": grounded,
        "grounded_note": grounded_note,
    }


# --------------------------------------------------------------------------
# Finding specs. Each dict → one Finding row. `sev=` is a build_sev() kwargs
# dict (the resolver decides the canonical band). Cluster members share
# (category-tool, file, cwe, close line) so _correlate_run_findings collapses
# them. `ai=` attaches an ai_analysis block; `status`/`revoked_by` for revokes.
# --------------------------------------------------------------------------
def finding_specs() -> list[dict]:
    S = []  # noqa: N806

    # ===== CLUSTER A — SQL Injection CWE-89 (SAST, 3 tools) =====
    S.append(dict(tool="codeql", rule_id="py/sql-injection", cwe="CWE-89",
                  file="pygoat/introduction/views.py", line=42,
                  msg="SQL query built from user-controlled `request.GET` without parameterisation.",
                  sev=dict(raw_label="error", score=9.1, kind="security-severity")))  # keeper, promoted+disagree
    S.append(dict(tool="semgrep", rule_id="python.django.security.injection.sql.sql-injection",
                  cwe="CWE-89", file="pygoat/introduction/views.py", line=42,
                  msg="Detected string concatenation into a raw SQL statement.",
                  sev=dict(raw_label="ERROR")))
    S.append(dict(tool="bandit", rule_id="B608", cwe="CWE-89",
                  file="pygoat/introduction/views.py", line=44,
                  msg="Possible SQL injection vector through string-based query construction.",
                  sev=dict(raw_label="MEDIUM")))

    # ===== CLUSTER B — Command Injection CWE-78 (SAST, 2 tools) =====
    S.append(dict(tool="codeql", rule_id="py/command-line-injection", cwe="CWE-78",
                  file="app/utils/exec.py", line=88,
                  msg="Uncontrolled command line built from user input passed to os.system.",
                  sev=dict(raw_label="error", score=8.8, kind="security-severity")))  # keeper
    S.append(dict(tool="semgrep", rule_id="python.lang.security.audit.dangerous-os-exec",
                  cwe="CWE-78", file="app/utils/exec.py", line=88,
                  msg="Found subprocess call with shell=True and tainted argument.",
                  sev=dict(raw_label="ERROR")))

    # ===== CLUSTER C — Hardcoded credentials CWE-798 (SAST, 2 tools) =====
    S.append(dict(tool="semgrep", rule_id="python.lang.security.hardcoded-password",
                  cwe="CWE-798", file="app/config/settings.py", line=15,
                  msg="Hardcoded secret assigned to SECRET_KEY.",
                  sev=dict(raw_label="WARNING")))  # keeper (tool priority > bandit)
    S.append(dict(tool="bandit", rule_id="B105", cwe="CWE-798",
                  file="app/config/settings.py", line=15,
                  msg="Possible hardcoded password: 'django-insecure-...'.",
                  sev=dict(raw_label="MEDIUM")))

    # ===== CLUSTER D — Vulnerable dependency CWE-1321 (DEPS, 3 tools) =====
    S.append(dict(tool="dependency-check", rule_id="CVE-2021-23337", cwe="CWE-1321",
                  file="package-lock.json", line=1240,
                  msg="lodash <4.17.21 prototype pollution (CVE-2021-23337).",
                  sev=dict(raw_label="HIGH", score=7.2, kind="v3")))  # keeper (deps, low id)
    S.append(dict(tool="owasp-dependency-check", rule_id="CVE-2021-23337", cwe="CWE-1321",
                  file="package-lock.json", line=1240,
                  msg="lodash prototype pollution via _.set (CVE-2021-23337).",
                  sev=dict(raw_label="HIGH", score=7.2, kind="v3")))
    S.append(dict(tool="trivy", rule_id="CVE-2021-23337", cwe="CWE-1321",
                  file="package-lock.json", line=1242,
                  msg="lodash: command injection / prototype pollution (CVE-2021-23337).",
                  sev=dict(raw_label="HIGH", score=7.2, kind="v3")))

    # ===== STANDALONE — severity story (promotions / disagreements / v2vsv3) =====
    S.append(dict(tool="codeql", rule_id="py/reflective-xss", cwe="CWE-79",
                  file="templates/profile.html", line=12,
                  msg="Reflected cross-site scripting from unescaped context variable.",
                  sev=dict(raw_label="error", score=6.2, kind="security-severity")))  # disagree, NOT promoted
    S.append(dict(tool="codeql", rule_id="py/unsafe-deserialization", cwe="CWE-502",
                  file="api/serializers.py", line=77,
                  msg="Deserialization of untrusted data with pickle.loads.",
                  sev=dict(raw_label="error", score=9.6, kind="security-severity")))  # promoted+disagree → critical
    S.append(dict(tool="semgrep", rule_id="python.requests.security.ssrf", cwe="CWE-918",
                  file="api/fetch.py", line=9, source=SRC_SSRF,
                  msg="Server-side request forgery: URL from request used in requests.get.",
                  sev=dict(raw_label="ERROR")))  # label-only + có source cho /verify (TRUE_POSITIVE)
    S.append(dict(tool="semgrep", rule_id="python.lang.security.path-traversal", cwe="CWE-22",
                  file="api/files.py", line=45,
                  msg="Path traversal: user input joined into filesystem path.",
                  sev=dict(raw_label="WARNING")))
    S.append(dict(tool="bandit", rule_id="B303", cwe="CWE-327",
                  file="utils/crypto.py", line=9,
                  msg="Use of insecure MD5 hash function.",
                  sev=dict(raw_label="MEDIUM")))
    S.append(dict(tool="eslint", rule_id="no-eval", cwe="CWE-95",
                  file="static/app.js", line=120,
                  msg="eval() can execute arbitrary code; avoid it.",
                  sev=dict(raw_label="ERROR")))  # label-only → high
    S.append(dict(tool="gosec", rule_id="G401", cwe="CWE-326",
                  file="server/main.go", line=40,
                  msg="Use of weak cryptographic primitive (DES).",
                  sev=dict(raw_label="HIGH")))

    S.append(dict(tool="trivy", rule_id="CVE-2023-41164", cwe="CWE-400",
                  file="requirements.txt", line=7,
                  msg="Django <3.2.21 DoS via django.utils.encoding.uri_to_iri (CVE-2023-41164).",
                  sev=dict(raw_label="MEDIUM", score=8.2, kind="v3")))  # ★ promoted MEDIUM→HIGH (score)
    S.append(dict(tool="safety", rule_id="CVE-2023-30861", cwe="CWE-524",
                  file="requirements.txt", line=11,
                  msg="Flask <2.2.5 cookie caching of sensitive response (CVE-2023-30861).",
                  sev=dict(raw_label="low", score=7.1, kind="v3")))  # ★ promoted LOW→HIGH (score)
    S.append(dict(tool="trivy", rule_id="CVE-2022-40899", cwe="CWE-502",
                  file="requirements.txt", line=15,
                  msg="future <0.18.3 deserialization issue (reported CVSS v2).",
                  sev=dict(raw_label="CRITICAL", score=9.4, kind="v2")))  # ★ v2: score→high, label keeps critical
    S.append(dict(tool="trivy", rule_id="CVE-2022-40900", cwe="CWE-502",
                  file="requirements.txt", line=40,
                  msg="pyyaml <5.4 arbitrary code execution (reported CVSS v3).",
                  sev=dict(raw_label="CRITICAL", score=9.4, kind="v3")))  # ★ v3: agree critical (far line → not merged w/ v2)
    S.append(dict(tool="trivy", rule_id="CVE-2021-33203", cwe=None,
                  file="requirements.txt", line=20,
                  msg="Dependency vulnerability with UNKNOWN vendor label but a CVSS score.",
                  sev=dict(raw_label="UNKNOWN", score=6.5, kind="v3")))  # ★ score-only
    S.append(dict(tool="dependency-check", rule_id="CVE-2020-1234", cwe="CWE-79",
                  file="package-lock.json", line=980,
                  msg="jquery <3.5.0 XSS in DOM manipulation.",
                  sev=dict(raw_label="MEDIUM", score=5.3, kind="v3")))  # agree medium

    # ===== STANDALONE — DAST (owasp-zap) =====
    S.append(dict(tool="owasp-zap", rule_id="40018", cwe="CWE-89",
                  file="https://staging.demo.app/search", line=None,
                  msg="SQL injection confirmed on the /search endpoint (active scan).",
                  sev=dict(raw_label="High", dast_promote_to="critical")))  # ★ DAST promotion
    S.append(dict(tool="owasp-zap", rule_id="10038", cwe="CWE-16",
                  file="https://staging.demo.app/", line=None,
                  msg="Content Security Policy header not set.",
                  sev=dict(raw_label="Low")))

    # ===== benign SAST fillers (raw-by-tool variety) =====
    S.append(dict(tool="semgrep", rule_id="python.lang.best-practice.logging", cwe="CWE-311",
                  file="api/config.py", line=5, msg="Sensitive data may be logged in cleartext.",
                  sev=dict(raw_label="WARNING")))
    S.append(dict(tool="bandit", rule_id="B110", cwe="CWE-703",
                  file="utils/parse.py", line=51, msg="try/except/pass detected.",
                  sev=dict(raw_label="LOW")))
    S.append(dict(tool="eslint", rule_id="no-document-cookie", cwe="CWE-1004",
                  file="static/cookie.js", line=8, msg="Cookie set without HttpOnly flag.",
                  sev=dict(raw_label="WARNING")))
    S.append(dict(tool="codeql", rule_id="py/csrf-protection-disabled", cwe="CWE-352",
                  file="api/views.py", line=300, msg="CSRF protection disabled on a state-changing view.",
                  sev=dict(raw_label="error", score=7.4, kind="security-severity")))  # agree high
    S.append(dict(tool="gosec", rule_id="G304", cwe="CWE-22",
                  file="server/files.go", line=60, msg="Potential file inclusion via variable.",
                  sev=dict(raw_label="MEDIUM")))
    S.append(dict(tool="trivy", rule_id="CVE-2023-0286", cwe="CWE-843",
                  file="requirements.txt", line=25, msg="cryptography X.400 type confusion (CVE-2023-0286).",
                  sev=dict(raw_label="HIGH", score=7.4, kind="v3")))

    # ===== AI-analysed findings (V4.2 story) =====
    S.append(dict(tool="bandit", rule_id="B105", cwe="CWE-798",
                  file="tests/test_auth.py", line=6, source=SRC_TEST_FIXTURE,
                  msg="Possible hardcoded password: 'password123'.",
                  sev=dict(raw_label="LOW"), status="ai_analyzed",
                  ai=dict(vuln_id="BANDIT-B105", cwe="CWE-798", severity="low",
                          fp="HIGH",
                          fp_reason="Chuỗi nằm trong fixture test (tests/), không phải secret production; không có luồng dữ liệu tới sink thật.",
                          grounded=True, grounded_note="Bản vá đối chiếu được với mã nguồn.",
                          confidence="LOW",
                          explanation="Bandit gắn cờ chuỗi 'password123' là mật khẩu cứng, nhưng nó là dữ liệu giả trong test đăng nhập.",
                          impact="Không có tác động thực tế: giá trị chỉ dùng khi chạy test, không xuất hiện ở runtime.",
                          diff="# tests/test_auth.py\n# (cân nhắc: có thể là false positive — chuỗi test)\n-    password = 'password123'\n+    password = os.environ.get('TEST_PASSWORD', 'password123')")))
    S.append(dict(tool="eslint", rule_id="no-eval", cwe="CWE-95",
                  file="static/vendor/chart.min.js", line=1,
                  msg="eval() usage detected in bundled script.",
                  sev=dict(raw_label="ERROR"), status="ai_analyzed",
                  ai=dict(vuln_id="ESLINT-no-eval", cwe="CWE-95", severity="high",
                          fp="HIGH",
                          fp_reason="File là thư viện bên thứ ba đã minify (static/vendor), không phải mã ứng dụng — sửa tại đây vô nghĩa; nên loại trừ khỏi scan.",
                          grounded=True, grounded_note="Đối chiếu được dòng eval trong bundle.",
                          confidence="LOW",
                          explanation="eval nằm trong chart.min.js của thư viện Chart.js đã đóng gói.",
                          impact="Không phải bề mặt tấn công của ứng dụng; là mã vendor.",
                          diff="// static/vendor/chart.min.js\n// (false positive: vendored/minified — thêm vào ignore của ESLint)")))
    S.append(dict(tool="semgrep", rule_id="python.lang.security.audit.raw-sql", cwe="CWE-89",
                  file="api/legacy.py", line=210,
                  msg="Raw SQL execution with a formatted string.",
                  sev=dict(raw_label="ERROR"), status="ai_analyzed",
                  ai=dict(vuln_id="SEMGREP-raw-sql", cwe="CWE-89", severity="high",
                          fp="LOW",
                          fp_reason="",
                          grounded=False,
                          grounded_note="Bản vá tham chiếu hàm `sanitize_query()` và biến `db_cursor` KHÔNG có trong mã nguồn thật — nghi mô hình bịa; đã hạ độ tin cậy xuống LOW.",
                          confidence="LOW",
                          explanation="Câu lệnh SQL ghép chuỗi f-string với tham số từ request.",
                          impact="Có thể dẫn tới SQL injection nếu tham số không được kiểm soát.",
                          diff="# api/legacy.py\n-    cursor.execute(f\"SELECT * FROM t WHERE id={id}\")\n+    cursor.execute(sanitize_query(db_cursor, id))  # <-- không neo được vào mã thật")))
    S.append(dict(tool="codeql", rule_id="py/stored-xss", cwe="CWE-79",
                  file="templates/comment.html", line=55,
                  msg="Stored XSS: comment body rendered without escaping.",
                  sev=dict(raw_label="error", score=7.7, kind="security-severity"),
                  status="ai_analyzed",
                  ai=dict(vuln_id="CODEQL-stored-xss", cwe="CWE-79", severity="high",
                          fp="LOW", fp_reason="",
                          grounded=True,
                          grounded_note="Bản vá đối chiếu khớp dòng render `{{ comment.body }}` trong template.",
                          confidence="HIGH",
                          explanation="Nội dung comment do người dùng nhập được render thẳng vào HTML mà không escape.",
                          impact="Kẻ tấn công lưu script chạy trên trình duyệt của mọi người xem trang.",
                          diff="{# templates/comment.html #}\n-  {{ comment.body }}\n+  {{ comment.body | e }}")))
    S.append(dict(tool="trivy", rule_id="CVE-2020-14343", cwe="CWE-502",
                  file="requirements.txt", line=30,
                  msg="pyyaml full_load arbitrary code execution (CVE-2020-14343).",
                  sev=dict(raw_label="HIGH", score=9.8, kind="v3"), status="ai_analyzed",
                  ai=dict(vuln_id="CVE-2020-14343", cwe="CWE-502", severity="critical",
                          fp="MEDIUM",
                          fp_reason="Dự án có thể không dùng yaml.load không an toàn; cần xác minh cách gọi trước khi kết luận.",
                          grounded=True, grounded_note="Bản vá nâng version trong manifest.",
                          confidence="MEDIUM",
                          explanation="Phiên bản PyYAML cũ cho phép thực thi mã khi load YAML không tin cậy.",
                          impact="RCE nếu ứng dụng load YAML từ nguồn không tin cậy.",
                          diff="# requirements.txt\n-pyyaml==5.3\n+pyyaml==5.4")))

    # AI auto-revoked (drives ai_revoked): status REVOKED + revoked_by ~ triage
    S.append(dict(tool="bandit", rule_id="B110", cwe="CWE-703",
                  file="utils/logging.py", line=88,
                  msg="try/except/pass swallows exceptions in the logging path.",
                  sev=dict(raw_label="LOW"), status="REVOKED",
                  revoked_by="ai-triage",
                  revoke_justification="AI triage (thấy code): false positive — except chỉ nuốt lỗi ghi log, không nằm trên đường dữ liệu bảo mật; tự thu hồi khỏi gate.",
                  ai=dict(vuln_id="BANDIT-B110", cwe="CWE-703", severity="low",
                          fp="HIGH",
                          fp_reason="except/pass trong nhánh ghi log phụ; không ảnh hưởng luồng bảo mật.",
                          grounded=True, grounded_note="Đối chiếu khối try/except trong mã.",
                          confidence="HIGH",
                          explanation="Mẫu try/except/pass ở đoạn ghi log, không che giấu lỗi bảo mật.",
                          impact="Không đáng kể — chỉ bỏ qua lỗi ghi log.",
                          diff="# utils/logging.py (được AI đánh giá là nhiễu, không cần sửa)")))

    return S


async def main() -> None:
    async with AsyncSessionLocal() as s:
        # 1) project (idempotent)
        proj = (await s.execute(
            select(Project).where(Project.name == PROJECT_NAME)
        )).scalar_one_or_none()
        if proj is None:
            proj = Project(
                name=PROJECT_NAME, github_url=GITHUB_URL,
                github_owner="demo", github_repo="xu-ly-du-lieu",
                gate_critical_threshold=0, gate_high_threshold=5,
                active=1,
            )
            s.add(proj)
            await s.flush()
            print(f"Created project #{proj.id} {PROJECT_NAME}")
        else:
            # wipe old findings/artifacts for a clean reseed
            fids = [r[0] for r in (await s.execute(
                select(Finding.id).where(Finding.project_id == proj.id))).all()]
            if fids:
                await s.execute(delete(FindingAction).where(FindingAction.finding_id.in_(fids)))
                await s.execute(delete(CommandFeedback).where(CommandFeedback.finding_id.in_(fids)))
            await s.execute(delete(Finding).where(Finding.project_id == proj.id))
            await s.execute(delete(Artifact).where(Artifact.project_id == proj.id))
            proj.archived_at = None
            proj.active = 1
            print(f"Reusing project #{proj.id} {PROJECT_NAME} (wiped old findings)")
        await s.flush()

        # 2) one artifact = one run
        art = Artifact(
            github_artifact_id="demo-artifact-1", project_id=proj.id,
            github_run_id=RUN_ID, status="processed",
            created_at=datetime.now(UTC),
        )
        s.add(art)
        await s.flush()

        # 3) findings
        now = datetime.now(UTC)
        specs = finding_specs()
        for spec in specs:
            normalized, cvss, prov = build_sev(**spec["sev"])
            raw_data = {"_severity": prov, "demo_seed": True}
            if spec.get("source"):
                raw_data["source_code"] = spec["source"]
            f = Finding(
                artifact_id=art.id, project_id=proj.id,
                tool=spec["tool"], rule_id=spec["rule_id"],
                severity=normalized, message=spec["msg"],
                file_path=spec["file"], line_number=spec.get("line"),
                cwe_id=spec.get("cwe"), cvss_score=cvss,
                raw_data=raw_data,
                dedup_hash=_hash(spec["rule_id"], spec["file"], spec["msg"]),
                status=spec.get("status", "pending_review"),
                normalized_at=now,
                revoked_by=spec.get("revoked_by"),
                revoke_justification=spec.get("revoke_justification"),
                revoked_at=now if spec.get("revoked_by") else None,
            )
            if "ai" in spec:
                f.ai_analysis = ai_block(fid_placeholder=0, **spec["ai"])
            s.add(f)
        await s.flush()
        await s.commit()
        total_raw = len(specs)
        print(f"Inserted {total_raw} raw findings under run {RUN_ID}")

    # 4) run the REAL cross-tool correlation (writes _correlation, deletes dups)
    proc = SecurityProcessor()
    deleted = await proc._correlate_run_findings(proj.id, RUN_ID)
    print(f"Cross-tool dedup collapsed {deleted} duplicate findings")

    # 5) fix ai_analysis.finding_id placeholders (cosmetic — panel reads by id)
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(Finding).where(Finding.project_id == proj.id,
                                  Finding.ai_analysis.is_not(None)))).scalars().all()
        for f in rows:
            ai = dict(f.ai_analysis or {})
            if ai.get("finding_id") != f.id:
                ai["finding_id"] = f.id
                f.ai_analysis = ai
        await s.commit()
        remaining = (await s.execute(
            select(Finding).where(Finding.project_id == proj.id))).scalars().all()
        print(f"Unique findings after dedup: {len(remaining)}")
        print(f"\nDONE. Open the dashboard, chọn project '{PROJECT_NAME}' (#{proj.id}), "
              f"vào trang 'Xử lý dữ liệu'.")


if __name__ == "__main__":
    asyncio.run(main())
