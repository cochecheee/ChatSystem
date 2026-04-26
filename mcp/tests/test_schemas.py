from src.models.schemas import FindingCreate, compute_dedup_hash


def test_finding_create_valid():
    finding = FindingCreate(
        artifact_id=1,
        tool="semgrep",
        rule_id="python.lang.security.audit.exec-use",
        severity="high",
        message="Use of exec() detected",
        file_path="src/app.py",
        line_number=42,
    )
    assert finding.artifact_id == 1
    assert finding.tool == "semgrep"
    assert finding.line_number == 42


def test_finding_create_optional_fields():
    finding = FindingCreate(
        artifact_id=1,
        tool="codeql",
        rule_id="py/sql-injection",
        severity="critical",
        message="SQL injection vulnerability",
        file_path="src/db.py",
    )
    assert finding.line_number is None
    assert finding.cwe_id is None
    assert finding.cvss_score is None


def test_compute_dedup_hash_consistency():
    h1 = compute_dedup_hash("rule-123", "src/app.py", "Use of exec()")
    h2 = compute_dedup_hash("rule-123", "src/app.py", "Use of exec()")
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex digest


def test_compute_dedup_hash_uniqueness():
    h1 = compute_dedup_hash("rule-123", "src/app.py", "Use of exec()")
    h2 = compute_dedup_hash("rule-456", "src/app.py", "Use of exec()")
    assert h1 != h2


def test_compute_dedup_hash_different_files():
    h1 = compute_dedup_hash("rule-123", "src/app.py", "msg")
    h2 = compute_dedup_hash("rule-123", "src/other.py", "msg")
    assert h1 != h2
