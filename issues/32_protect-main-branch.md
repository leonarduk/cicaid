# 32 — Protect main branch to prevent accidental changes

**URL:** https://github.com/leonarduk/cicaid/issues/32
**Labels:** enhancement, Medium Value
**State:** closed

## What

Protect the main branch to ensure that it remains stable and only receives intentional changes.

## Why

To safeguard against accidental or malicious modifications that could disrupt the project's integrity or release cycle.

## How

Applied via `gh api` using the configuration in `.github/branch-protection.json`. A reproducible script is available at `scripts/apply-branch-protection.sh`.

## Rules applied

| Rule | Value |
|------|-------|
| Require pull request reviews before merging | ✅ (0 required approvals — solo maintainer; GitHub never allows self-approval, so requiring 1+ would permanently block merges) |
| Dismiss stale pull request approvals | ✅ |
| Require conversation resolution before merging | ✅ |
| Enforce for admins | ✅ |
| Allow force pushes | ❌ Disabled |
| Allow deletions | ❌ Disabled |

## Verification

- **CI:** `.github/workflows/branch-protection-audit.yml` runs weekly and on config changes to verify rules haven't drifted. This requires a `gh_token` repository secret holding a PAT from a user with admin/owner rights on the repo — the branch protection GET endpoint has no permission scope grantable to the default `GITHUB_TOKEN`. Until that secret is added, the workflow logs a warning and skips (non-blocking) rather than failing every run.
- **CLI:** `./scripts/apply-branch-protection.sh --verify` checks the live rules against `.github/branch-protection.json`.
- **Manual:** `./scripts/apply-branch-protection.sh` (re-)applies rules and verifies them.

## Success looks like

- [x] Branch protection rules are successfully applied to the main branch
- [x] Direct pushes to main are blocked (including for admins)
- [x] PRs go through a pull request (direct pushes to main are blocked); no minimum approval count, since there's a single maintainer
- [x] Conversation must be resolved before merging
- [x] CI audit workflow verifies protection weekly
- [x] Reproducible apply/verify script committed
