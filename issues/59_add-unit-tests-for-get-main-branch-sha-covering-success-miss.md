# 59 — Add unit tests for `get_main_branch_sha()` covering success, missing remote, and missing main/master scenarios

**URL:** https://github.com/leonarduk/cicaid/issues/59
**Labels:** ai-suggested, sonnet
**State:** open

## Add unit tests for `get_main_branch_sha()` covering success, missing remote, and missing main/master scenarios

### What

Add unit tests for the `get_main_branch_sha()` function in the cicaid repository. This function is new (introduced in PR #58) and currently has no test coverage. It uses `subprocess.run` to determine the main branch SHA by checking `origin/master` first, then falling back to `origin/main`.

### Why

`get_main_branch_sha()` is called from `main()` and a failure here would break the entire workflow. The function has multiple failure modes (no remote configured, no main/master branch, git not installed) that are currently untested. Without tests, regressions in this critical path could go undetected. The review also noted that the error handling doesn't distinguish between "no remote" and "no main/master branch," which is a usability concern that tests would help clarify.

### How

1. Create a new test file (or add to an existing test file) for the module containing `get_main_branch_sha()`.
2. Mock `subprocess.run` to simulate the following scenarios:
   - **Success with `origin/master`**: `subprocess.run` returns a `CompletedProcess` with `returncode=0` and the SHA in `stdout`.
   - **Success with `origin/main`**: First call (master) returns `returncode=1`, second call (main) returns `returncode=0` with the SHA.
   - **Missing remote**: Both calls return `returncode=1` (or raise `CalledProcessError`), verify the function exits gracefully with an appropriate error message.
   - **Missing main/master**: Both calls return `returncode=1`, verify the error message is clear.
   - **Git not installed**: `subprocess.run` raises `FileNotFoundError`, verify graceful handling.
3. For each scenario, assert the return value (SHA) or the exit behavior/error message.
4. Consider testing the `check=True` vs `check=False` behavior difference between the master and main calls.

### Files Affected

- `tests/test_<module_containing_get_main_branch_sha>.py` (new file — exact path unknown, likely under `tests/`)
- The source file containing `get_main_branch_sha()` (exact path unknown from review text)

### Constraints

- Do not change the behavior of `get_main_branch_sha()` itself — only add tests.
- Do not introduce new dependencies (use `unittest.mock` or `pytest` with mocking, whichever is already in the project).
- Tests must not require a real git repository or network access — all subprocess calls must be mocked.
- Out of scope: improving the error message to distinguish "no remote" vs "no main/master" (that's a separate follow-up), and switching to `git symbolic-ref` for default branch detection.

### LLM tier

**Sonnet** — This requires moderate design judgment: deciding how to structure the mock scenarios, handling the `check=True` vs `check=False` asymmetry, and ensuring the tests are robust without changing the function's behavior.

### Success looks like

- All new tests pass in CI.
- Coverage for `get_main_branch_sha()` is at or near 100% for the scenarios listed above.
- Tests are deterministic (no reliance on actual git state or network).
- Tests clearly document the expected behavior for each failure mode.

### Failure looks like

- Tests are flaky or depend on the actual git repository state.
- Tests only cover the happy path (master exists) and miss the fallback/main-only scenarios.
- Tests require real subprocess calls or network access.
- The test file is placed in an unexpected location or doesn't follow existing test conventions in the repo.

_Follow-up from AI review of PR #58._