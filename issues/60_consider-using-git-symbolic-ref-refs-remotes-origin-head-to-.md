# 60 — Consider using `git symbolic-ref refs/remotes/origin/HEAD` to detect the default branch instead of hardcoding main/master

**URL:** https://github.com/leonarduk/cicaid/issues/60
**Labels:** ai-suggested, sonnet
**State:** open

## Consider using `git symbolic-ref refs/remotes/origin/HEAD` to detect the default branch instead of hardcoding main/master

### What

In `get_main_branch_sha()` (likely in the main script or a git helper module), replace the current logic that tries `origin/master` first and falls back to `origin/main` with a single call to:

```bash
git symbolic-ref refs/remotes/origin/HEAD
```

This command returns the symbolic ref of the remote's HEAD, which points to the actual default branch (e.g., `refs/remotes/origin/main` or `refs/remotes/origin/master`). Parse the output to extract the branch name and use it for the SHA lookup.

### Why

- **Correctness risk**: Hardcoding `main`/`master` assumes one of these two names. Repositories can have a different default branch (e.g., `trunk`, `develop`, `production`). If neither `main` nor `master` exists, the function fails even though a valid default branch exists.
- **Maintainability**: The current fallback chain (`master` → `main`) is brittle and requires updating if GitHub changes its default branch naming convention.
- **Protocol compliance**: `git symbolic-ref refs/remotes/origin/HEAD` is the canonical way to determine the remote's default branch and is guaranteed to work with any branch name.

### How

1. Replace the two `subprocess.run` calls (one for `origin/master`, one for `origin/main`) with a single call:
   ```python
   result = subprocess.run(
       ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
       capture_output=True, text=True, check=False
   )
   ```
2. If `result.returncode != 0`, raise a clear error indicating the remote HEAD could not be determined (e.g., no remote configured or remote HEAD not set).
3. Parse `result.stdout` to extract the branch name (e.g., strip the `refs/remotes/origin/` prefix).
4. Use the extracted branch name to fetch the SHA (e.g., `git rev-parse refs/remotes/origin/<branch>`).

### Files Affected

- `cicaid/` (main script or module containing `get_main_branch_sha()`)

### Constraints

- Must not break the existing behavior when the remote is `origin` and the default branch is `main` or `master`.
- Must preserve the current error handling: if the remote HEAD cannot be determined, the function should exit gracefully with a helpful message.
- Out of scope: changing the error message to distinguish "no remote" vs "no default branch" (that's a separate follow-up issue).
- Must not introduce new dependencies.

### LLM tier

**Sonnet** — This is a moderate change: it requires updating a single function's logic, handling a new subprocess call, and parsing its output. It involves some design judgment (how to parse the output, what error message to use) but is not architecturally complex.

### Success looks like

- `get_main_branch_sha()` returns the correct SHA for a repo whose default branch is `main`, `master`, or any other name (e.g., `trunk`).
- The function fails gracefully with a clear error message when no remote is configured or the remote HEAD is not set.
- Existing tests for the function (if any) pass; new tests cover the `git symbolic-ref` success and failure paths.

### Failure looks like

- The function still hardcodes `main`/`master` or falls back to them.
- The function breaks for repos with a non-`main`/`master` default branch.
- The function raises an unhelpful error (e.g., a raw `CalledProcessError`) when the remote HEAD is missing.
- The change introduces a regression in the existing branch-existence pre-check flow.

_Follow-up from AI review of PR #58._