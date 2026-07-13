"""Snapshot tests for the prompt registry.

Why snapshots: prompts are part of the product contract. An accidental
edit that changes Gemini behavior (drop a "MUST", reword a directive)
shouldn't sneak in via a normal PR. These tests render each prompt with
a fixed fixture and compare against a committed snapshot file. If a real
prompt edit is intentional, run `pytest --update-snapshots` (or set the
env var) to overwrite the snapshot in the same commit as the edit.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.services.llm.prompt_loader import get_registry

SNAPSHOT_DIR = Path(__file__).parent / "snapshots" / "prompts"
UPDATE = os.environ.get("UPDATE_PROMPT_SNAPSHOTS") == "1"


def _assert_snapshot(name: str, content: str) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{name}.txt"
    if UPDATE or not path.exists():
        path.write_text(content, encoding="utf-8")
        return
    expected = path.read_text(encoding="utf-8")
    assert content == expected, (
        f"Prompt {name!r} drifted from snapshot.\n"
        f"To accept the change: UPDATE_PROMPT_SNAPSHOTS=1 pytest tests/test_prompt_loader.py\n"
        f"Snapshot: {path}"
    )


# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------

def test_registry_lists_all_known_prompts():
    r = get_registry()
    assert set(r.list_ids()) == {"analyze", "cve", "chat", "summary", "triage", "investigate"}


def test_registry_unknown_prompt_raises():
    r = get_registry()
    with pytest.raises(KeyError):
        r.system_for("does-not-exist")


def test_frontmatter_parses_meta():
    """analyze.system.md ships with a YAML frontmatter — meta must merge
    into the returned dict (model + id from file overrides registry)."""
    rendered = get_registry().render(
        "analyze",
        tool_name="semgrep", rule_id="r1", message="m", file_path="f.py",
        line_number=None, cwe_id=None, cvss_score=None, code_context="",
    )
    assert rendered.meta.get("id") == "analyze.system"
    assert rendered.meta.get("model") == "gemini-2.5-flash"
    assert "response_schema" in rendered.meta  # from registry


# ---------------------------------------------------------------------------
# System prompts — snapshot the raw text
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("prompt_id", ["analyze", "chat", "summary", "triage", "investigate"])
def test_system_prompt_snapshot(prompt_id: str):
    text = get_registry().system_for(prompt_id)
    _assert_snapshot(f"{prompt_id}.system", text)


# ---------------------------------------------------------------------------
# User templates — snapshot the rendered text against a fixed fixture
# ---------------------------------------------------------------------------

def test_analyze_user_snapshot():
    rendered = get_registry().render(
        "analyze",
        tool_name="semgrep",
        rule_id="java/path-injection",
        message="Path traversal via user input",
        file_path="src/main/java/Foo.java",
        line_number=42,
        cwe_id="CWE-22",
        cvss_score=7.5,
        code_context="42 | File f = new File(req.getParameter(\"x\"));",
    )
    assert rendered.user is not None
    _assert_snapshot("analyze.user", rendered.user)


def test_investigate_user_snapshot():
    rendered = get_registry().render(
        "investigate",
        tool_name="codeql",
        rule_id="py/sql-injection",
        message="SQL query built from user input",
        file_path="app/views.py",
        line_number=42,
        cwe_id="CWE-89",
        cvss_score=9.1,
        code_context="  40 | def search(request):\n  42 | cursor.execute(f\"...{request.GET['q']}\")",
    )
    assert rendered.user is not None
    _assert_snapshot("investigate.user", rendered.user)


def test_triage_user_snapshot():
    items = [
        {"id": 1, "tool": "semgrep", "rule_id": "r1", "severity": "high",
         "file_path": "a.py", "line_number": 10, "message": "msg a",
         "code": "10 | os.system(x)"},
        {"id": 2, "tool": "codeql", "rule_id": "r2", "severity": "critical",
         "file_path": "b.java", "line_number": None, "message": "msg b", "code": ""},
    ]
    rendered = get_registry().render("triage", items=items)
    assert rendered.user is not None
    _assert_snapshot("triage.user", rendered.user)


def test_summary_user_snapshot():
    rendered = get_registry().render(
        "summary",
        project_name="ALOUTE",
        stats={
            "active": 184, "revoked": 12, "total": 196,
            "critical": 8, "high": 23, "medium": 50, "ai_analyzed": 100,
        },
        top_findings=[
            {"id": 1, "severity": "critical", "rule_id": "CVE-2022-1471",
             "file_path": "snakeyaml", "message": "Yaml deserialization RCE"},
            {"id": 2, "severity": "high", "rule_id": "java/ssrf",
             "file_path": "Foo.java", "message": "SSRF via user URL"},
        ],
    )
    assert rendered.user is not None
    _assert_snapshot("summary.user", rendered.user)


# ---------------------------------------------------------------------------
# Sanity: chat has no user template (caller builds its own prompt body)
# ---------------------------------------------------------------------------

def test_chat_has_no_user_template():
    rendered = get_registry().render("chat")
    assert rendered.user is None
    assert "Shiftwall" in rendered.system
