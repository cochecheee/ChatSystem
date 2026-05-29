"""Backward-compat shim. Prompts live in `mcp/prompts/v1/` since 2026-05-28.

Old imports still resolve to the same strings via the registry, so:

    from src.services.llm.prompts import SYSTEM_INSTRUCTION, build_prompt

keeps working. New code should call `get_registry().render(...)` or
`get_registry().system_for(...)` directly — see prompt_loader.py.

When all callers are migrated, delete this module.
"""
from __future__ import annotations

from .prompt_loader import get_registry


def _system(prompt_id: str) -> str:
    return get_registry().system_for(prompt_id).rstrip()


# Module-level attribute access wires backward-compat names to the registry.
# Lazy: a single import doesn't pay the cost unless one of the old names is read.
def __getattr__(name: str) -> str:
    if name == "SYSTEM_INSTRUCTION":
        return _system("analyze")
    if name == "CHAT_SYSTEM_INSTRUCTION":
        return _system("chat")
    if name == "USER_PROMPT_TEMPLATE":
        # Legacy: a Python str.format template. New code passes vars to render().
        # We can't faithfully reconstruct {field} syntax from the Jinja file
        # without losing alignment, so callers reading this directly must move
        # to get_registry().render("analyze", **vars).user.
        raise AttributeError(
            "USER_PROMPT_TEMPLATE removed — use "
            "get_registry().render('analyze', **vars).user instead"
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def build_prompt(
    tool_name: str,
    rule_id: str,
    message: str,
    file_path: str,
    line_number: int | None,
    cwe_id: str | None,
    cvss_score: float | None,
    code_context: str,
) -> str:
    """Legacy entry point — kept so old imports don't break.

    New code should call:
        get_registry().render("analyze", tool_name=..., rule_id=..., ...).user
    """
    return get_registry().render(
        "analyze",
        tool_name=tool_name,
        rule_id=rule_id,
        message=message,
        file_path=file_path,
        line_number=line_number,
        cwe_id=cwe_id,
        cvss_score=cvss_score,
        code_context=code_context,
    ).user or ""
