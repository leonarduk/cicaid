# 54 — Add test for repo names containing `.wiki` in the middle (e.g., `my.wiki.project`)

**URL:** https://github.com/leonarduk/cicaid/issues/54
**Labels:** ai-suggested, sonnet
**State:** open

## Add test for repo names containing `.wiki` in the middle (e.g., `my.wiki.project`)

### What

Add a test case to the test suite that verifies `get_repo_info()` correctly handles repo names containing `.wiki` in the middle (e.g., `my.wiki.project`). The test should assert that the `.wiki` suffix is **not** stripped from such names.

### Why

The current `.wiki` stripping logic in `get_repo_info()` uses `[:-len(".wiki")]` which will strip the suffix from any repo name ending in `.wiki`, regardless of whether it's a true wiki repo. A repo like `my.wiki.project` would be incorrectly truncated to `my.wiki`. While this is an edge case, it represents a correctness risk for real-world repo names that happen to contain `.wiki` in the middle.

### How

1. Locate the existing test file that covers `get_repo_info()` (likely `tests/test_github_repo.py` or similar)
2. Add a test case similar to:
   ```python
   def test_repo_name_with_wiki_in_middle():
       # Should NOT strip .wiki from middle of name
       result = get_repo_info("https://github.com/owner/my.wiki.project.git")
       assert result["repo_name"] == "my.wiki.project"
   ```
3. Run the test suite to confirm the new test fails (demonstrating the bug) and then fix the implementation if needed

### Files Affected

- `tests/test_github_repo.py` (or the existing test file for `get_repo_info()`)

### Constraints

- Must not break existing tests for `.wiki` suffix stripping (e.g., `cicaid.wiki` → `cicaid`)
- Must not change the behavior for repos without `.wiki` suffix
- Out of scope: `FileNotFoundError` handling for git not installed (separate follow-up issue)
- Out of scope: changing the stripping logic to use `rstrip(".wiki")` (separate follow-up issue)

### LLM Tier

**Sonnet** — This requires moderate design judgment to determine the correct test placement and to verify whether the current implementation actually fails for this case, plus potentially fixing the stripping logic if the test reveals a bug.

### Success Looks Like

- New test case added that covers `my.wiki.project` (and possibly `my.wiki.project.wiki` for completeness)
- Test passes, confirming the implementation correctly handles `.wiki` in the middle of repo names
- All existing tests continue to pass

### Failure Looks Like

- Test is added but passes without any implementation change (indicating the test doesn't actually exercise the edge case)
- Test fails and the fix breaks existing `.wiki` suffix stripping behavior
- Test is added but doesn't assert the correct expected behavior (e.g., asserts stripping when it shouldn't)

_Follow-up from AI review of PR #52._