# 47 — Add documentation on how to create and store the `gh_token` PAT with the correct permissions

**URL:** https://github.com/leonarduk/cicaid/issues/47
**Labels:** ai-suggested, sonnet
**State:** open

## Add documentation on how to create and store the `gh_token` PAT with the correct permissions

### What

Add documentation to the repository explaining how to create a GitHub Personal Access Token (PAT) for use as the `gh_token` secret, including the exact permissions/scopes required and how to store it as a repository secret.

### Why

The branch protection audit workflow (`.github/workflows/branch-protection-audit.yml`) and the apply script (`scripts/apply-branch-protection.sh`) both require a PAT with specific permissions. Currently, the only guidance is a warning message in the workflow that says "Add a repo-admin PAT as the 'gh_token' secret" — this is insufficient for users who need to set this up. Without proper documentation, users may create a PAT with incorrect scopes (e.g., missing `repo` scope or admin permissions), causing the workflow to silently skip or the apply script to fail with confusing errors.

### How

1. Create a new documentation file (e.g., `docs/gh-token-setup.md`) that covers:
   - Step-by-step instructions for creating a PAT via GitHub's UI (Settings → Developer settings → Personal access tokens → Fine-grained tokens or classic tokens)
   - The exact scopes/permissions required: `repo` scope (full control of private repositories) and admin permissions on the repository (or `repo:admin` scope for classic tokens)
   - Why `GITHUB_TOKEN` cannot be used (it lacks branch protection endpoint access)
   - How to store the token as a repository secret named `gh_token` (Settings → Secrets and variables → Actions → New repository secret)
   - How to verify the token works (e.g., running `gh auth login` with the token and testing `gh api repos/{owner}/{repo}/branches/main/protection`)
2. Add a link to this documentation in the workflow file's warning message (line 28) and in the apply script's error message (line 24) so users know where to find setup instructions.

### Files Affected

- `docs/gh-token-setup.md` (new file)
- `.github/workflows/branch-protection-audit.yml`
- `scripts/apply-branch-protection.sh`

### Constraints

- Do not change the logic of the workflow or script — this is documentation-only plus minor message updates
- The documentation must be accurate for both classic and fine-grained PATs
- The workflow must continue to skip gracefully when the secret is missing (non-blocking behavior must be preserved)
- Out of scope: switching to GitHub's native rulesets API, adding CI verification on every PR, or changing the audit schedule

### LLM tier

**Sonnet** — This requires moderate design judgment to write clear, accurate documentation that covers both PAT types and to update error messages without breaking existing behavior.

### Success looks like

- A new `docs/gh-token-setup.md` file exists with complete, accurate setup instructions
- The workflow warning message and script error message reference the documentation file
- A user following the documentation can successfully create a PAT, store it as `gh_token`, and have the audit workflow run without skipping
- The apply script works when run with the documented token

### Failure looks like

- Documentation is incomplete or inaccurate (e.g., missing the `repo` scope requirement)
- The workflow or script behavior changes unintentionally (e.g., now fails instead of skipping when secret is missing)
- The documentation is not linked from the existing warning/error messages
- Instructions don't work for either classic or fine-grained PATs

_Follow-up from AI review of PR #44._