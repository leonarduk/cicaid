# 50 — Correct misleading documentation about GitHub self-approval behavior in `issues/32_protect-main-branch.md`

**URL:** https://github.com/leonarduk/cicaid/issues/50
**Labels:** ai-suggested, sonnet
**State:** open

# Correct misleading documentation about GitHub self-approval behavior in `issues/32_protect-main-branch.md`

## What

The file `issues/32_protect-main-branch.md` contains a factually incorrect statement about GitHub's self-approval behavior. The current text claims:

> "GitHub never allows self-approval, so requiring 1+ would permanently block merges"

This needs to be corrected to accurately describe GitHub's actual behavior.

## Why

The current documentation is misleading and could confuse future maintainers about how GitHub's branch protection works. Specifically:

- GitHub does allow self-approval — the restriction is that the PR author cannot approve their own PR, but a collaborator (or the maintainer from a different account) can approve it.
- With `required_approving_review_count=1`, a solo maintainer is not permanently blocked — they can merge via the "Merge without waiting for requirements to be met" option (if they have admin rights) or via the API with `bypass_pull_request_allowances`.
- The actual reason for setting `required_approving_review_count=0` is likely that the maintainer wants to merge their own PRs without needing a second reviewer — a legitimate choice that should be documented accurately.

## How

1. Open `issues/32_protect-main-branch.md`.
2. Locate the paragraph containing the incorrect claim about self-approval.
3. Replace it with an accurate explanation, for example:
   - GitHub requires approval from someone other than the PR author.
   - A solo maintainer can still merge with `required_approving_review_count=1` via admin bypass options.
   - The choice of `0` is intentional to allow self-merging without workarounds.
4. Ensure the revised text is consistent with the actual configuration change made in PR #49.

## Files Affected

- `issues/32_protect-main-branch.md`

## Constraints

- Do not change the actual configuration value (`required_approving_review_count=0`) — this is correct and already applied.
- Do not modify the audit workflow or verification script — they are consistent with the current value.
- Only the documentation text in the specified file should change.

## LLM tier

**Sonnet** — This requires moderate judgment to accurately describe GitHub's self-approval behavior and rewrite the justification without introducing new inaccuracies.

## Success looks like

- The file `issues/32_protect-main-branch.md` no longer contains the false claim that GitHub "never allows self-approval."
- The revised text accurately describes GitHub's approval rules and the rationale for `required_approving_review_count=0`.
- The documentation is consistent with the actual configuration and does not mislead future maintainers.

## Failure looks like

- The incorrect claim remains or is replaced with another inaccurate statement about GitHub's behavior.
- The documentation contradicts the actual configuration or the audit workflow.
- The change introduces confusion about why `0` was chosen instead of `1`.

_Follow-up from AI review of PR #49._