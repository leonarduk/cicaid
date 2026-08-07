# 42 — Document the redaction behavior in the project's security guidelines

**URL:** https://github.com/leonarduk/cicaid/issues/42
**Labels:** ai-suggested, sonnet
**State:** open

## Document the redaction behavior in the project's security guidelines

### What

Add a section to the project's security guidelines (likely `SECURITY.md` or `docs/security.md` — exact path to be confirmed) that documents:

1. The redaction utility `redact_env_var_names()` in `review_common.py` and its purpose
2. The regex pattern `_ENV_VAR_NAME_RE` and its suffix-based matching behavior
3. Which error paths currently use the utility: `get_required_env`, `ProviderAuthError`, `ProviderOutageError`, `emit_invalid_key_notice`, and HTTP error logging in `fetch_review`
4. The known limitation: the suffix-based regex is inconsistent (e.g., `SOME_VENDOR_API` is redacted but `FOLLOWUP_LLM_PROVIDER` is not, even though both are plausible env var names)
5. The exception redaction behavior: `ProviderAuthError.__init__` and `ProviderOutageError.__init__` redact all string args, but preserve non-string first args (e.g., error codes)

### Why

- **Correctness risk**: Without documentation, future contributors may assume all error paths are redacted, or may extend the regex without understanding its limitations, leading to either secret leakage or over-redaction.
- **Maintainability**: The current behavior has known inconsistencies (suffix-based matching) that need to be explicitly acknowledged so maintainers can decide whether to fix or accept them.
- **Protocol compliance**: Security guidelines should describe how sensitive data is handled in error paths so reviewers and contributors can verify compliance during code review.

### How

1. Locate the security guidelines file (likely `SECURITY.md` at repo root, or `docs/security.md` — verify before editing).
2. Add a new section titled "Environment Variable Redaction in Error Paths" (or similar).
3. Document:
   - The utility function name and its location (`review_common.py`)
   - The regex pattern and its suffix-based approach
   - The list of error paths that currently use the utility
   - The known inconsistency with the suffix list (e.g., `PROVIDER` not in suffix list)
   - The exception redaction behavior (string args redacted, non-string args preserved)
   - A note that the regex is intentionally conservative to avoid over-redaction, but may under-redact some env var names
4. Add a "Future improvements" note referencing the potential for a more comprehensive regex (e.g., `[A-Z][A-Z0-9_]*` with at least one underscore).

### Files Affected

- `SECURITY.md` (or `docs/security.md` — verify exact path)
- `review_common.py` (reference only — no code changes expected)

### Constraints

- Do not change the redaction behavior itself — this issue is documentation-only.
- Do not modify the regex pattern or the exception classes.
- Do not add new dependencies.
- The documentation must accurately reflect the current behavior, including its limitations.

### LLM tier

**Sonnet** — This requires moderate design judgment to accurately describe the current behavior and its limitations, and to structure the documentation appropriately for a security guidelines document.

### Success looks like

- A new section in the security guidelines that accurately describes:
  - The `redact_env_var_names()` utility and its location
  - The regex pattern and its suffix-based matching behavior
  - All error paths that use the utility
  - The known inconsistency (e.g., `FOLLOWUP_LLM_PROVIDER` not redacted)
  - The exception redaction behavior (string args redacted, non-string args preserved)
- The documentation is clear enough that a new contributor can understand the redaction behavior without reading the source code.

### Failure looks like

- The documentation is inaccurate or misleading (e.g., claims all env vars are redacted when they are not).
- The documentation is so vague that it doesn't help contributors understand the actual behavior.
- The documentation implies the behavior is comprehensive when it is known to be incomplete.
- The issue results in code changes to the redaction logic (out of scope).

_Follow-up from AI review of PR #31._