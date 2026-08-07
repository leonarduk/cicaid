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
| Require pull request reviews before merging | ✅ 1 approving review |
| Dismiss stale pull request approvals | ✅ |
| Require conversation resolution before merging | ✅ |
| Enforce for admins | ✅ |
| Allow force pushes | ❌ Disabled |
| Allow deletions | ❌ Disabled |

## Verification

- **CI:** `.github/workflows/branch-protection-audit.yml` runs weekly and on config changes to verify rules haven't drifted.
- **CLI:** `./scripts/apply-branch-protection.sh --verify` checks the live rules against `.github/branch-protection.json`.
- **Manual:** `./scripts/apply-branch-protection.sh` (re-)applies rules and verifies them.

## Success looks like

- [x] Branch protection rules are successfully applied to the main branch
- [x] Direct pushes to main are blocked (including for admins)
- [x] PRs require at least 1 approving review before merging
- [x] Conversation must be resolved before merging
- [x] CI audit workflow verifies protection weekly
- [x] Reproducible apply/verify script committed
