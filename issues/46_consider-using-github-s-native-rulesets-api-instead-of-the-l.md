# 46 — Consider using GitHub's native rulesets API instead of the legacy branch protection API for better maintainability

**URL:** https://github.com/leonarduk/cicaid/issues/46
**Labels:** ai-suggested, sonnet
**State:** open

# Consider using GitHub's native rulesets API instead of the legacy branch protection API for better maintainability

## What

Replace the legacy branch protection API calls in `scripts/apply-branch-protection.sh` and `.github/workflows/branch-protection-audit.yml` with GitHub's native rulesets API. Specifically:

- Update the `apply` function in `scripts/apply-branch-protection.sh` to use the rulesets API (`PUT /repos/{owner}/{repo}/rulesets`) instead of the branch protection endpoint (`PUT /repos/{owner}/{repo}/branches/{branch}/protection`)
- Update the `verify` function in the same script to check rulesets instead of branch protection rules
- Update the audit workflow to validate rulesets configuration

## Why

The legacy branch protection API is deprecated and being phased out by GitHub. Rulesets provide:

- **Better maintainability**: Rulesets support more granular controls (e.g., required workflows, merge queue, file path restrictions) that branch protection cannot express
- **Future-proofing**: GitHub is actively migrating users away from the legacy API; continuing to use it risks breakage when it's eventually removed
- **Consistency**: Rulesets are the recommended way to enforce repository policies going forward

## How

1. **Update `scripts/apply-branch-protection.sh`**:
   - Change the `apply` function to create/update a ruleset via `gh api --method PUT /repos/{owner}/{repo}/rulesets/{ruleset_id}` (or POST if creating a new one)
   - Map the existing 8 protection rules to equivalent ruleset conditions and rules (e.g., `pull_request` rule with `required_approving_review_count`, `deletion` rule, `non_fast_forward` rule)
   - Update the `--verify` mode to fetch and validate the ruleset configuration instead of branch protection settings
   - Adjust error handling to account for ruleset API response formats

2. **Update `.github/workflows/branch-protection-audit.yml`**:
   - Change the verification step to call the updated `--verify` mode
   - Update any comments referencing branch protection endpoints

3. **Add a CI job** (suggested follow-up): Add a job that runs `apply-branch-protection.sh --verify` on every PR to catch drift earlier than the weekly schedule

## Files Affected

- `scripts/apply-branch-protection.sh`
- `.github/workflows/branch-protection-audit.yml`

## Constraints

- Must maintain the same 8 protection rules currently enforced (do not reduce security posture)
- Must preserve the graceful handling of missing `gh_token` secret (skip with warning, not fail)
- Must keep `set -euo pipefail` and variable quoting practices in the shell script
- Out of scope: applying the rulesets to the repository (this PR only updates tooling, not execution)
- Out of scope: adding documentation for PAT creation (separate follow-up issue)

## LLM tier

**Sonnet** — This is a moderate multi-file change requiring design judgment to map legacy branch protection rules to equivalent ruleset configurations, but it doesn't involve architectural ambiguity or cross-cutting concerns.

## Success looks like

- `scripts/apply-branch-protection.sh --verify` passes against a repository with rulesets configured
- The audit workflow runs successfully and reports no drift when rulesets match expected configuration
- All 8 existing protection rules are enforced via rulesets with equivalent or stronger guarantees
- The script handles ruleset API errors gracefully (non-zero exit with clear error message, not masked by `--jq`)

## Failure looks like

- The script still calls the legacy branch protection API endpoints
- Ruleset configuration is incomplete or drops any of the 8 existing protection rules
- The audit workflow fails or silently skips when rulesets are misconfigured
- Error messages from the ruleset API are obscured by `--jq` parsing failures
- The script requires new permissions beyond what the existing `gh_token` PAT provides

_Follow-up from AI review of PR #44._