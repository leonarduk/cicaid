# 45 — Add a CI job that runs `apply-branch-protection.sh --verify` on every PR to catch drift earlier than the weekly schedule

**URL:** https://github.com/leonarduk/cicaid/issues/45
**Labels:** ai-suggested, sonnet
**State:** open

# Add a CI job that runs `apply-branch-protection.sh --verify` on every PR

## What

Add a new CI job to the repository that runs `scripts/apply-branch-protection.sh --verify` on every pull request. This should be a separate job in the existing workflow or a new workflow file, triggered on `pull_request` events.

## Why

The current branch protection audit workflow runs on a weekly schedule (every Monday) and on config changes. This means drift in branch protection rules can go undetected for up to a week. Running verification on every PR catches drift immediately, reducing the window where the main branch could be unprotected or misconfigured. This is a non-blocking follow-up from the AI review of PR #44, which noted that the weekly schedule could give a false sense of security.

## How

1. Add a new job to `.github/workflows/branch-protection-audit.yml` (or create a new workflow file) that:
   - Triggers on `pull_request` events (at minimum, on `opened`, `synchronize`, and `reopened`)
   - Checks out the repository
   - Installs the GitHub CLI (`gh`)
   - Sets `GH_TOKEN` from the `gh_token` secret (same as the existing audit job)
   - Runs `scripts/apply-branch-protection.sh --verify`
   - Fails the job if verification fails (unlike the weekly audit job which skips when the secret is missing, this job should fail if the secret is absent to make the requirement explicit)

2. Ensure the job handles the missing-secret case appropriately — since this is a PR gate, it should fail with a clear error message rather than silently skip, so contributors know the verification couldn't run.

## Files Affected

- `.github/workflows/branch-protection-audit.yml` (modify to add the PR-triggered job, or add a new workflow file)

## Constraints

- Must not break the existing weekly audit workflow — the new job should be additive
- Must not require changes to `scripts/apply-branch-protection.sh` — the existing `--verify` mode is sufficient
- Must not block PRs if the `gh_token` secret is missing — but should fail loudly with a clear message rather than silently passing
- Out of scope: changing the branch protection application logic, migrating to GitHub's rulesets API, or adding documentation for PAT creation (these are separate follow-ups)

## LLM Tier

**Sonnet** — This requires moderate design judgment: deciding how to structure the new job, handling the missing-secret case appropriately for a PR gate, and ensuring the change integrates cleanly with the existing workflow without breaking it.

## Success Looks Like

- A new CI job runs on every PR and executes `scripts/apply-branch-protection.sh --verify`
- The job passes when branch protection rules are correctly configured
- The job fails with a clear error message when branch protection rules have drifted
- The job fails with a clear error message when the `gh_token` secret is missing (rather than silently skipping)
- The existing weekly audit workflow continues to function unchanged

## Failure Looks Like

- The job silently skips when the `gh_token` secret is missing, giving a false sense of security
- The job fails on every PR due to a misconfiguration (e.g., wrong trigger event, incorrect script path)
- The job passes even when branch protection rules are misconfigured (e.g., `--verify` mode doesn't actually check all rules)
- The new job breaks the existing weekly audit workflow (e.g., by conflicting with its triggers or environment)

_Follow-up from AI review of PR #44._