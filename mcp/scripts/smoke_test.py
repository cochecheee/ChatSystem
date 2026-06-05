"""End-to-end smoke test — kiểm tra toàn bộ stack trước demo.

Chạy:  python -m scripts.smoke_test
Hoặc:  python -m scripts.smoke_test --base http://localhost:8000

Pass = mọi check trả OK. Fail = in stack trace + exit code 1.

Không cần Gemini quota; mock các Gemini-bound endpoint khi không có key.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any


class Check:
    def __init__(self, name: str, fn) -> None:
        self.name = name
        self.fn = fn
        self.result: str | None = None
        self.detail: str | None = None

    def run(self, base: str) -> bool:
        try:
            data = self.fn(base)
            self.result = "OK"
            self.detail = data if isinstance(data, str) else json.dumps(data, indent=2)[:200]
            return True
        except Exception as exc:
            self.result = "FAIL"
            self.detail = f"{type(exc).__name__}: {exc}"
            return False


def _get(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as resp:
        body = resp.read().decode()
        if "application/json" in (resp.headers.get("Content-Type") or ""):
            return json.loads(body)
        return body[:300]


def _post(url: str, body: dict, headers: dict | None = None) -> Any:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_health(base: str) -> Any:
    return _get(f"{base}/health")


def check_projects_listed(base: str) -> Any:
    data = _get(f"{base}/projects")
    if not isinstance(data, list) or not data:
        raise AssertionError("No project rows — run migrate_v2 + start poller")
    p = data[0]
    must_have = ["github_owner", "github_repo", "has_github_token", "has_gemini_api_key", "active"]
    for f in must_have:
        if f not in p:
            raise AssertionError(f"Project missing field: {f}")
    return p


def check_stats_overview(base: str) -> Any:
    data = _get(f"{base}/stats/overview")
    for f in ("total", "open", "sast_open", "deps_open", "sast_critical_high", "deps_critical_high"):
        if f not in data:
            raise AssertionError(f"Stats missing: {f}")
    return data


def check_findings_list(base: str) -> Any:
    sast = _get(f"{base}/findings?category=sast&limit=5")
    deps = _get(f"{base}/findings?category=deps&limit=5")
    if not isinstance(sast, list) or not isinstance(deps, list):
        raise AssertionError("Findings not list-shaped")
    return {"sast_sample": len(sast), "deps_sample": len(deps)}


def check_integration_endpoint(base: str) -> Any:
    project = _get(f"{base}/projects")[0]
    data = _get(f"{base}/projects/{project['id']}/integration")
    for f in ("webhook_url", "secrets_to_set_in_target_repo", "github_actions_yaml_step"):
        if f not in data:
            raise AssertionError(f"Integration missing: {f}")
    return {"webhook_url": data["webhook_url"]}


def check_swagger(base: str) -> Any:
    spec = _get(f"{base}/openapi.json")
    if "paths" not in spec:
        raise AssertionError("OpenAPI spec malformed")
    return {"path_count": len(spec["paths"])}


def check_webhook_unauth(base: str) -> Any:
    """Hit webhook with bad/missing auth — expect 403 if CI_WEBHOOK_TOKEN is set,
    or 202 if disabled. Either case == server reachable."""
    try:
        _post(f"{base}/webhook/pipeline-complete", {"run_id": 1})
        return "auth disabled (202)"
    except urllib.error.HTTPError as e:
        if e.code in (202, 403):
            return f"server reachable, code {e.code}"
        raise
    # URLError (connection refused, DNS, etc.) propagates to Check.run and
    # surfaces as a normal FAIL — same behaviour as the other checks.


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _precheck_reachable(base: str) -> tuple[bool, str]:
    """Fast (2s) connectivity probe — surfaces a clean error message
    when the backend is down instead of letting every check time out."""
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=2):
            return True, ""
    except urllib.error.URLError as e:
        return False, str(e.reason if hasattr(e, "reason") else e)
    except (OSError, ConnectionError) as e:
        return False, str(e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    args = ap.parse_args()

    print(f"=== Smoke test against {args.base} ===\n")

    ok, detail = _precheck_reachable(args.base)
    if not ok:
        print("  [FAIL]  backend unreachable")
        print(f"      {detail}")
        print()
        print("Backend chua chay. Khoi dong:")
        print("  cd mcp")
        print("  .venv\\Scripts\\activate")
        print("  uvicorn src.main:app --reload --port 8000")
        return 1

    checks = [
        Check("health", check_health),
        Check("swagger", check_swagger),
        Check("projects.list", check_projects_listed),
        Check("stats.overview", check_stats_overview),
        Check("findings.list", check_findings_list),
        Check("integration endpoint", check_integration_endpoint),
        Check("webhook reachable", check_webhook_unauth),
    ]

    failed = 0
    for c in checks:
        ok = c.run(args.base)
        marker = "[OK]" if ok else "[FAIL]"
        print(f"  {marker}  {c.name:32s}  {c.result}")
        if not ok:
            print(f"      {c.detail}")
            failed += 1

    print()
    print(f"{len(checks) - failed}/{len(checks)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
