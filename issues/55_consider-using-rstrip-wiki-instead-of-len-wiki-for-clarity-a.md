# 55 — Consider using `rstrip(".wiki")` instead of `[:-len(".wiki")]` for clarity and to handle multiple suffixes

**URL:** https://github.com/leonarduk/cicaid/issues/55
**Labels:** ai-suggested, haiku
**State:** open

## Consider using `rstrip(".wiki")` instead of `[:-len(".wiki")]` for clarity and to handle multiple suffixes

### What

In `github_repo.py`, the `get_repo_info()` function currently strips the `.wiki` suffix from repository names using slice notation:

```python
repo_name = repo_name[:-len(".wiki")] if repo_name.endswith(".wiki") else repo_name
```

Replace this with `rstrip(".wiki")`:

```python
repo_name = repo_name.rstrip(".wiki")
```

### Why

- **Correctness risk**: The current `[:-len(".wiki")]` approach only strips a single `.wiki` suffix. A repo name like `foo.wiki.wiki` would only have one suffix removed, leaving `foo.wiki`. `rstrip(".wiki")` removes all trailing occurrences, which is more robust.
- **Maintainability**: `rstrip(".wiki")` is more readable and expresses intent directly. The slice notation requires the reader to mentally compute the string length and verify the `endswith` guard.
- **Protocol compliance**: Wiki repos can theoretically have multiple `.wiki` suffixes (e.g., `project.wiki.wiki`), and `rstrip` handles this correctly without additional logic.

### How

1. Locate the `.wiki` stripping logic in `get_repo_info()` in `github_repo.py`.
2. Replace the conditional slice with `repo_name = repo_name.rstrip(".wiki")`.
3. Verify existing tests still pass — the behavior for single `.wiki` suffixes is identical.
4. Optionally add a test case for a repo name with multiple `.wiki` suffixes (e.g., `my.wiki.wiki` → `my`).

### Files Affected

- `github_repo.py`

### Constraints

- Must not change behavior for repo names without a `.wiki` suffix (they should remain unchanged).
- Must not affect the regex matching logic in `get_repo_info()` — only the post-match suffix stripping.
- Out of scope: the `FileNotFoundError` handling concern and the `my.wiki.project` edge case test (these are separate follow-up issues).

### LLM tier

**Haiku** — This is a simple, mechanical one-line change with no design ambiguity. The replacement is obvious and the test impact is minimal.

### Success looks like

- `repo_name.rstrip(".wiki")` is used in `get_repo_info()`.
- All existing tests pass without modification.
- A repo name like `foo.wiki.wiki` correctly becomes `foo` (if a test is added).
- No behavior change for repo names without `.wiki` suffix.

### Failure looks like

- The change introduces a regression where repo names without `.wiki` are incorrectly modified (e.g., `myproject` becomes `myproject` — should be unchanged).
- The change breaks the regex match or the returned repo name format.
- Tests fail because `rstrip(".wiki")` strips characters that shouldn't be stripped (e.g., a repo named `my.wiki` should become `my`, but `my.wiki` with a trailing space would behave differently).

_Follow-up from AI review of PR #52._