# 61 — Improve error message in `get_main_branch_sha()` to distinguish between "no remote configured" and "no main/master branch found"

**URL:** https://github.com/leonarduk/cicaid/issues/61
**Labels:** ai-suggested, sonnet
**State:** open

# Improve error message in `get_main_branch_sha()` to distinguish between "no remote configured" and "no main/master branch found"

## What

In `get_main_branch_sha()`, the current implementation uses `subprocess.run` with `check=True` for `origin/master` and `check=False` for `origin/main`. When both fail, the `CalledProcessError` from the second call is caught and the process exits, but the error message does not indicate whether the failure was due to:
- No remote configured (e.g., `origin` doesn't exist)
- No `main` or `master` branch on the remote

The error message should be updated to distinguish between these two scenarios.

## Why

- **Correctness risk**: Users may be confused when the error message doesn't explain the root cause. A user with a misconfigured remote (e.g., no `origin`) would see a generic "branch not found" error, leading to wasted debugging time.
- **Maintainability**: Clear error messages reduce support burden and make the codebase more self-documenting.
- **Protocol compliance**: The function is called in `main()`, so a failure here breaks the entire flow. A precise error message helps users self-diagnose.

## How

1. In `get_main_branch_sha()`, after the first `subprocess.run` for `origin/master` fails, check whether the remote `origin` exists (e.g., by running `git remote get-url origin` or inspecting `git remote` output).
2. If the remote doesn't exist, raise an error with a message like: `"No remote 'origin' configured. Please add a remote and try again."`
3. If the remote exists but neither `origin/main` nor `origin/master` is found, raise an error with a message like: `"Could not find a 'main' or 'master' branch on remote 'origin'. Please specify the default branch explicitly."`
4. Ensure the error message includes the underlying `CalledProcessError` details for debugging.

## Files Affected

- `cicaid/` (the module containing `get_main_branch_sha()` — exact path not confirmed from review text)

## Constraints

- Must not change the function's signature or return type.
- Must not alter the existing behavior when `origin/master` or `origin/main` is found successfully.
- Must not introduce new dependencies.
- Must not break existing tests for the function (if any exist).
- Out of scope: adding tests for `get_main_branch_sha()` (covered by a separate follow-up issue), changing the branch-detection logic (e.g., using `git symbolic-ref`).

## LLM tier

**Sonnet** — This requires moderate design judgment to determine the best way to detect "no remote" vs "no branch" and to craft clear error messages. It's a single-file change but involves non-trivial logic and error-handling decisions.

## Success looks like

- `get_main_branch_sha()` raises a distinct, actionable error message when no remote is configured.
- `get_main_branch_sha()` raises a distinct, actionable error message when the remote exists but has neither `main` nor `master`.
- The error messages include the underlying exception details for debugging.
- Existing behavior for successful cases is unchanged.
- All existing tests pass.

## Failure looks like

- The error message is still ambiguous (e.g., a single generic message for both failure modes).
- The function's behavior changes for successful cases (e.g., it now fails when it previously succeeded).
- The change introduces a regression in error handling (e.g., uncaught exceptions or swallowed errors).
- The implementation is overly complex or introduces new dependencies.

_Follow-up from AI review of PR #58._