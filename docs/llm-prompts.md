# LLM Prompts — `mcp/prompts/`

> Externalized in Phase 2 (V3.5). Before this, the 4 system instructions
> + 2 user templates lived as inline Python strings across 3 files. Now
> they live as plain markdown + Jinja2 files under `mcp/prompts/v1/`.

## Layout

```
mcp/prompts/
├── registry.yaml        # manifest: id → file paths + response schema + meta
└── v1/
    ├── analyze.system.md     # one-finding vulnerability analysis (system)
    ├── analyze.user.j2       # user prompt body for /findings/{id}/explain
    ├── chat.system.md        # Sentinel free-form chat assistant
    ├── triage.system.md      # batch FP triage
    ├── triage.user.j2        # rendered with a list of findings per call
    ├── summary.system.md     # Overview risk briefing
    └── summary.user.j2       # rendered with stats dict + top findings
```

Loader: `mcp/src/services/llm/prompt_loader.py`.
Call signature: `get_registry().render("<id>", **vars)` returns a
`RenderedPrompt(system, user, meta)` dataclass.
For prompts called without user vars (e.g. chat): `get_registry().system_for("<id>")`.

## File format

System files are markdown with an optional YAML frontmatter block:

```markdown
---
id: analyze.system
version: 1
model: gemini-2.5-flash
notes: |
  Single-finding analysis. Output is parsed via AnalysisOutput pydantic model.
  Vietnamese is mandatory for explanation_vi and impact_vi.
---
Bạn là Chuyên gia Bảo mật Ứng dụng cao cấp với hơn 10 năm kinh nghiệm...
```

The body below the second `---` is the actual instruction sent to Gemini.
The frontmatter is merged into the `meta` dict on the returned
`RenderedPrompt` — handy for routing or for the dashboard prompt-inspector.

User templates are pure Jinja2 — variables passed to `render()` are
available as top-level names. Strict undefined mode is enabled: a typo'd
variable name raises rather than silently rendering an empty string.

## Adding a new prompt

1. Pick an id and version (use the current `v1/` folder unless the change
   is semantic-breaking).
2. Drop `prompts/v1/<id>.system.md` and (optional) `prompts/v1/<id>.user.j2`.
3. Register it in `prompts/registry.yaml`:
   ```yaml
   prompts:
     yourprompt:
       description: ...
       system: yourprompt.system.md
       user: yourprompt.user.j2     # or null
       response_schema: YourModel   # name of pydantic model in src/services/llm/schemas.py
       temperature: null
   ```
4. Add a golden snapshot test in `tests/test_prompt_loader.py` so
   accidental edits are caught:
   ```python
   def test_yourprompt_snapshot():
       rendered = get_registry().render("yourprompt", **fixture)
       _assert_snapshot("yourprompt.user", rendered.user)
   ```
5. Run `UPDATE_PROMPT_SNAPSHOTS=1 pytest tests/test_prompt_loader.py` to
   write the initial snapshot. Commit both the prompt file and the
   snapshot file (`tests/snapshots/prompts/yourprompt.user.txt`).

## Editing an existing prompt

The snapshot tests will fail on the next pytest run. If the edit is
intentional, re-run with `UPDATE_PROMPT_SNAPSHOTS=1` to overwrite the
snapshot file and commit both changes in the same PR. Reviewers see the
old/new prompt text side-by-side in the diff.

## Versioning bump (`v1` → `v2`)

When the change is large enough that prior callers shouldn't auto-pick
it up:

1. `cp -r mcp/prompts/v1 mcp/prompts/v2` and edit the v2 copy.
2. Bump `registry.yaml` `version: v2` (and reference v2 files).
3. Code call sites: `get_registry(version="v2").render(...)`. Leave the
   old call sites on `v1` until they're individually migrated. The
   loader caches per version so both can coexist in one process.
4. Delete `v1/` only after every call site moved.

## Why externalize at all

- **Prompts evolve faster than code.** Editing a prompt shouldn't require
  a Python rebuild or a Docker push of the MCP image.
- **Snapshot diffs in PRs.** A subtle reword from "MUST" to "should" is
  invisible in a Python diff (looks like a string literal change) but
  obvious in a markdown diff.
- **Per-prompt config.** Frontmatter lets one prompt set a different
  temperature or model without polluting the global registry.
- **Future-proof.** When the dashboard adds a "Prompt inspector" admin
  tab, the loader already exposes everything it needs.
