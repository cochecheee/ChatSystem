"""Lint GitHub Actions workflows + composite actions in this repo.

Catches common mistakes without needing actionlint installed (which is
the proper Go-binary tool for this job and recommended for CI use):

- YAML parse errors
- Required top-level keys (on/jobs for workflows; runs.using for actions)
- Composite action: each step must have `shell` if it has `run`
- Local action references (./actions/foo) point to an existing action.yml
- Workflow `uses:` of in-repo composite uses correct relative path

Returns exit 0 if clean, 1 otherwise.

Usage:
    python -m scripts.lint_workflows
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def _files() -> list[Path]:
    paths: list[Path] = []
    paths.extend(sorted(REPO.glob("action.yml")))
    paths.extend(sorted(REPO.glob("actions/*/action.yml")))
    paths.extend(sorted(REPO.glob(".github/workflows/*.yml")))
    paths.extend(sorted(REPO.glob(".github/workflows/*.yaml")))
    paths.extend(sorted(REPO.glob("examples/**/.github/workflows/*.yml")))
    return paths


def _is_action(p: Path) -> bool:
    return p.name == "action.yml"


def _check_action(p: Path, data: dict, errs: list[str]) -> None:
    if "runs" not in data:
        errs.append(f"{p}: missing 'runs' key")
        return
    runs = data["runs"]
    using = runs.get("using")
    if using not in ("composite", "docker", "node20", "node16"):
        errs.append(f"{p}: runs.using must be composite/docker/node20 (got {using!r})")
        return
    if using == "composite":
        steps = runs.get("steps", [])
        if not steps:
            errs.append(f"{p}: composite has no steps")
        for i, step in enumerate(steps):
            if "run" in step and "shell" not in step:
                errs.append(f"{p}: step #{i+1} has 'run:' but missing 'shell:'")


def _check_workflow(p: Path, data: dict, errs: list[str]) -> None:
    # YAML 1.1 parses bare `on:` as True. Accept either.
    if "on" not in data and True not in data:
        errs.append(f"{p}: missing 'on' trigger")
    if "jobs" not in data:
        errs.append(f"{p}: missing 'jobs'")
        return
    for job_name, job in (data.get("jobs") or {}).items():
        # Reusable workflow caller — has `uses:` at job level
        if "uses" in job:
            uses = job["uses"]
            if uses.startswith("./"):
                target = REPO / uses[2:]
                if not target.exists():
                    errs.append(f"{p}: job '{job_name}' references missing local workflow: {uses}")
            continue

        # Regular job — check steps
        for i, step in enumerate(job.get("steps") or []):
            uses = step.get("uses") or ""
            if uses.startswith("./"):
                # Local action reference
                target = REPO / uses[2:] / "action.yml"
                if not target.exists():
                    errs.append(f"{p}:{job_name}:step {i+1}: local action {uses} -> {target} not found")
            if "run" in step and "shell" in step and step["shell"] not in (
                "bash", "sh", "pwsh", "powershell", "cmd", "python",
            ):
                errs.append(f"{p}:{job_name}:step {i+1}: unusual shell {step['shell']!r}")


def main() -> int:
    files = _files()
    if not files:
        print("No action / workflow files found.")
        return 0

    print(f"Linting {len(files)} file(s)...\n")
    errs: list[str] = []
    for p in files:
        rel = p.relative_to(REPO).as_posix()
        try:
            with p.open(encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            errs.append(f"{rel}: YAML error: {e}")
            print(f"  [FAIL] {rel}")
            continue

        before = len(errs)
        if _is_action(p):
            _check_action(p, data, errs)
        else:
            _check_workflow(p, data, errs)
        marker = "[FAIL]" if len(errs) > before else "[OK]  "
        print(f"  {marker} {rel}")

    print()
    if errs:
        print(f"{len(errs)} issue(s):")
        for e in errs:
            print(f"  - {e}")
        print("\nFor deeper checks (shell expressions, action input typing) install actionlint:")
        print("  https://github.com/rhysd/actionlint/releases")
        return 1

    print("Clean.")
    print("\nNote: this is a structural lint. For full validation install actionlint:")
    print("  https://github.com/rhysd/actionlint/releases  (Windows: actionlint_*_windows_amd64.zip)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
