"""Prompt registry — load + render prompts from `mcp/prompts/<version>/`.

Why not just inline Python strings? Three reasons:

1. **Version control without code change.** Prompts evolve faster than code.
   Editing `summary.system.md` doesn't trigger a Python rebuild and is easy
   to diff in PRs.

2. **Snapshot testing.** `tests/test_prompt_loader.py` renders every prompt
   against a fixed fixture and asserts the output is byte-equal to the
   committed snapshot. Accidental prompt edits surface as a failing test.

3. **Multi-version coexistence.** When prompts change semantically (not just
   wording), bump folder to `v2/`. The loader takes `version="v1"` so old
   call sites can stay pinned during a rollout.

Frontmatter on the system file is optional. When present, it overrides
the defaults from registry.yaml — useful for per-prompt model or
temperature without editing the registry every time.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

log = logging.getLogger(__name__)

# Resolve `mcp/prompts/` relative to repo root, not CWD. The package layout
# is mcp/src/services/llm/prompt_loader.py → 4 parents up = mcp/.
_DEFAULT_PROMPTS_ROOT = Path(__file__).resolve().parents[3] / "prompts"

_FRONTMATTER_DELIM = "---"


@dataclass(frozen=True)
class RenderedPrompt:
    """One prompt ready to hand to GeminiClient.

    `system` is always present. `user` is None when the caller passes its
    own user content (chat assistant) or when there is no Jinja template.
    `meta` carries the merged registry + frontmatter so callers can pick
    up temperature / response_schema name without re-reading the YAML.
    """
    id: str
    system: str
    user: str | None
    meta: dict[str, Any]


class PromptRegistry:
    def __init__(self, root: Path | None = None, version: str = "v1") -> None:
        self._root = root or _DEFAULT_PROMPTS_ROOT
        self._version = version
        self._versioned_root = self._root / version
        registry_path = self._root / "registry.yaml"
        if not registry_path.exists():
            raise FileNotFoundError(f"Prompt registry not found: {registry_path}")
        with registry_path.open("r", encoding="utf-8") as f:
            self._manifest = yaml.safe_load(f) or {}
        if self._manifest.get("version") != version:
            log.warning(
                "Prompt registry declares version=%r but caller requested %r",
                self._manifest.get("version"), version,
            )
        self._jinja = Environment(
            loader=FileSystemLoader(str(self._versioned_root)),
            keep_trailing_newline=True,
            undefined=StrictUndefined,
        )

    # ------------------------------------------------------------------

    def _parse_frontmatter(self, raw: str) -> tuple[dict, str]:
        """Strip optional YAML frontmatter, return (meta, body).

        Frontmatter is the block between the first two `---` lines at the
        top of the file. Missing frontmatter is fine — returns `({}, raw)`.
        """
        lines = raw.splitlines(keepends=True)
        if not lines or lines[0].rstrip() != _FRONTMATTER_DELIM:
            return {}, raw
        for i in range(1, len(lines)):
            if lines[i].rstrip() == _FRONTMATTER_DELIM:
                meta_yaml = "".join(lines[1:i])
                body = "".join(lines[i + 1:])
                meta = yaml.safe_load(meta_yaml) or {}
                # Strip the leading newline that almost always sits between
                # `---` and the actual content.
                return meta, body.lstrip("\n")
        # Unterminated frontmatter → treat as plain content (don't lose data).
        return {}, raw

    # ------------------------------------------------------------------

    def _load_entry(self, prompt_id: str) -> dict:
        entry = (self._manifest.get("prompts") or {}).get(prompt_id)
        if entry is None:
            raise KeyError(f"Prompt {prompt_id!r} not in registry.yaml")
        return entry

    def _load_system(self, entry: dict) -> tuple[str, dict]:
        system_path = self._versioned_root / entry["system"]
        if not system_path.exists():
            raise FileNotFoundError(f"System prompt missing: {system_path}")
        raw = system_path.read_text(encoding="utf-8")
        frontmatter, body = self._parse_frontmatter(raw)
        return body.rstrip() + "\n", frontmatter

    def system_for(self, prompt_id: str) -> str:
        """Return only the system instruction. Use when the user prompt is
        built externally (e.g. the dashboard chat tab streams text directly).
        """
        return self._load_system(self._load_entry(prompt_id))[0]

    def render(self, prompt_id: str, **vars: Any) -> RenderedPrompt:
        """Render system + user templates for `prompt_id`.

        Vars are passed to the user-template Jinja render. System files are
        not templated (avoids accidental Jinja interpretation of an edit).
        Callers that only need the system instruction should use
        `system_for(prompt_id)` instead.
        """
        entry = self._load_entry(prompt_id)
        system_body, frontmatter = self._load_system(entry)

        user_template_name = entry.get("user")
        user_body: str | None = None
        if user_template_name:
            template = self._jinja.get_template(user_template_name)
            user_body = template.render(**vars)

        # Merge precedence: registry entry < file frontmatter. Per-prompt
        # notes/temperature in the markdown win over registry defaults.
        meta = {**{k: v for k, v in entry.items() if k not in ("system", "user")},
                **frontmatter}
        return RenderedPrompt(
            id=prompt_id,
            system=system_body,
            user=user_body,
            meta=meta,
        )

    # ------------------------------------------------------------------

    def list_ids(self) -> list[str]:
        return sorted((self._manifest.get("prompts") or {}).keys())


@lru_cache(maxsize=4)
def get_registry(version: str = "v1") -> PromptRegistry:
    """Cached singleton — prompts are read once per process.

    Tests that mutate prompts on disk should call `get_registry.cache_clear()`.
    """
    return PromptRegistry(version=version)
