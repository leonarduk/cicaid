# 53 — Add `FileNotFoundError` handling in `github_repo.py` for consistency with previous error handling

**URL:** https://github.com/leonarduk/cicaid/issues/53
**Labels:** ai-suggested, sonnet
**State:** open

# Add `FileNotFoundError` handling in `github_repo.py` for consistency with previous error handling

## What

Add explicit `FileNotFoundError` handling around the `subprocess.run` call in `github_repo.py` (specifically in the `get_repo_info()` function). This should match the error handling that existed in the old implementation in `pr_review.py`.

## Why

During the refactoring in PR #52, the shared `get_repo_info()` implementation was moved to `github_repo.py`. The old implementation in `pr_review.py` had explicit `FileNotFoundError` handling for when git is not installed, but this was lost in the refactoring. This is a regression in error handling quality — without it, users without git installed will get an unhandled traceback instead of a clear error message.

## How

1. Locate the `subprocess.run` call in `get_repo_info()` in `github_repo.py`
2. Wrap the call in a `try`/`except FileNotFoundError` block
3. In the except block, raise a clear error message indicating that git is required but not installed (or handle it gracefully, matching the previous behavior in `pr_review.py`)
4. Ensure the error message is actionable and consistent with the project's existing error handling style

## Files Affected

- `github_repo.py`

## Constraints

- Do not change the function signature or return type of `get_repo_info()`
- Do not alter the regex pattern or `.wiki` stripping logic — that is out of scope for this issue
- The error handling should be consistent with what was previously in `pr_review.py` (the exact behavior can be referenced from git history)
- No new dependencies should be introduced

## LLM tier

**Sonnet** — This requires understanding the existing error handling patterns in the codebase and making a judgment call about the appropriate error message and handling strategy. It's a single-file change but involves non-trivial design decisions about error reporting.

## Success looks like

- `get_repo_info()` in `github_repo.py` catches `FileNotFoundError` when git is not installed
- A clear, actionable error message is raised (or handled) instead of an unhandled traceback
- Existing tests still pass
- The behavior matches what was previously in `pr_review.py` before the refactoring

## Failure looks like

- The `FileNotFoundError` is still unhandled, producing a raw traceback
- The error handling is added but changes the function's behavior in unexpected ways (e.g., returns a different type, swallows the error silently)
- The change introduces a regression in the regex or `.wiki` stripping logic
- Existing tests break due to the change

_Follow-up from AI review of PR #52._