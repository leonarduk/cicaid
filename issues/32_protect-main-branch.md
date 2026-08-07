# 32 — Protect main branch to prevent accidental changes

**URL:** https://github.com/leonarduk/cicaid/issues/32
**Labels:** enhancement, Medium Value
**State:** closed

## What

Protect the main branch to ensure that it remains stable and only receives intentional changes.

## Why

To safeguard against accidental or malicious modifications that could disrupt the project's integrity or release cycle.

## How

Applied branch protection rules via the GitHub API (`gh api`). The configuration is stored in `.github/branch-protection.json`.

## Rules applied

| Rule | Value |
|------|-------|
| Require pull request reviews before merging | ✅ 1 approving review |
| Dismiss stale pull request approvals | ✅ |
| Require conversation resolution before merging | ✅ |
| Allow force pushes | ❌ Disabled |
| Allow deletions | ❌ Disabled |
| Enforce for admins | ❌ Not enforced |

## Success looks like

- [x] Branch protection rules are successfully applied to the main branch
- [x] Direct pushes to main are blocked
- [x] PRs require at least 1 approving review before merging
- [x] Conversation must be resolved before merging
