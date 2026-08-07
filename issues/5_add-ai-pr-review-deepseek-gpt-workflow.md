# 5 — Add AI PR review (DeepSeek + GPT) workflow

**URL:** https://github.com/leonarduk/cicaid/issues/5
**Labels:** enhancement
**State:** open

## What

Port allotmint-mcp's automated PR review system: [`_ai-pr-review.yml`](https://github.com/leonarduk/allotmint-mcp/blob/main/.github/workflows/_ai-pr-review.yml) (a reusable workflow) plus the two thin callers [`deepseek-pr-review.yml`](https://github.com/leonarduk/allotmint-mcp/blob/main/.github/workflows/deepseek-pr-review.yml) and [`gpt-pr-review.yml`](https://github.com/leonarduk/allotmint-mcp/blob/main/.github/workflows/gpt-pr-review.yml). On every PR it posts an AI-drafted review comment, requires an APPROVE verdict to pass, and files follow-up issues from the review findings.

## Why

Every PR to cicaid currently gets zero automated review. This is the same review pipeline allotmint/allotmint-mcp already run — worth having on cicaid's own PRs too, and cicaid is arguably the *right* home for it long-term (same duplication problem #374 solved for `scripts/developer_tools/`: allotmint-mcp's `.github/scripts/*.py` for this pipeline aren't shared with allotmint's copies either).

## What's already here vs. what's missing

`src/cicaid_devtools/lib/deepseek_review.py` and `review_common.py` are **already in cicaid** (ported earlier for `llm_common.py`'s local/PR-review dispatch — they happen to double as the CI-invoked script, since `deepseek_review.py` has both a `fetch_deepseek_review()` function and a `main()` that reads the same env vars the CI workflow sets).

Still missing, all from `allotmint-mcp/.github/scripts/`:
- `gpt_review.py`
- `prepare_review_diff.py`
- `prepare_review_discussion.py`
- `extract_verified_symbols.py`
- `extract_verdict.py`
- `build_review_comment.sh`
- `extract_followups.py`
- `create_followup_issues.py`
- `llm_labels.py` (used elsewhere in the label-creation step)

## How

1. Decide where these scripts live: `.github/scripts/` in cicaid (workflow-only, not part of the pip package) is the simplest match to how `_ai-pr-review.yml` invokes them (`python3 .github/scripts/whatever.py`) — no packaging changes needed, just copy them in.
2. Port `_ai-pr-review.yml` as-is (it's already fully parameterized by `provider_name`/`provider_id`/`review_script`).
3. Add `deepseek-pr-review.yml` and `gpt-pr-review.yml` callers.
4. Wire up repo secrets (`DEEPSEEK_API_KEY`, `OPENAI_API_KEY`) and the `ENABLE_DEEPSEEK_REVIEW`/`ENABLE_GPT_REVIEW` repo variables — these need to be set in cicaid's repo settings (human step, not scriptable).
5. The workflow auto-creates labels (`ai-suggested`, `haiku`/`sonnet`/`opus`, `Changes Requested`) on first run — no manual label setup needed.

## Constraints

Needs `DEEPSEEK_API_KEY`/`OPENAI_API_KEY` configured as repo secrets before it'll do anything other than post an empty-review failure — flag this clearly in the PR that closes this issue.

## Success looks like

- [ ] `.github/scripts/` has all 9 scripts (2 already present + 7 ported)
- [ ] `_ai-pr-review.yml`, `deepseek-pr-review.yml`, `gpt-pr-review.yml` added
- [ ] A test PR gets an AI review comment posted