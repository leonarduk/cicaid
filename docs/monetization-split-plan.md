# Open-core split: what's public vs private

`cicaid` is the free, open-source shell of a larger toolset. The LLM-backed
review and triage engine lives in a separate private package, `cicaid-pro`.

## What's here (public, MIT)

GitHub-plumbing commands that need no LLM access:

- `sync-issues` — sync GitHub issues to local markdown files
- `update-issue` — update a GitHub issue from a changed local file
- `work-on-issue` — check out a branch for an issue
- `work-on-pr` — check out the branch for an open PR
- `add-issue-to-pr` — link an issue to its PR
- `dependabot-auto-merge` — auto-merge green Dependabot PRs
- `run-ci-checks` — run a repo's local CI check suite
- `setup-review-actions` — scaffold AI-review GitHub Actions into a repo

## What's in `cicaid-pro` (private)

The LLM review/triage engine, and the commands built on it:

- `create-issue` — draft and create a new GitHub issue
- `local-review` — LLM-review uncommitted local changes
- `pr-review` — LLM-review an open PR
- `review-issue` — refresh a stale issue with an LLM
- `triage-issues` — triage unmilestoned open issues
- `clear-ai-slop-issues` — detect and close duplicate/stale/AI-slop issues
- `implement-issue-with-aider` — extract an issue prompt for Aider
- `commit-and-push` — commit with an AI-drafted message

Provider support (Claude, DeepSeek, GPT, Ollama) and the underlying
diff/verdict parsing all live here too.

Installing the public `cicaid` package without `cicaid-pro` gives you the
commands above; running a `cicaid-pro`-only command will tell you it isn't
available and point you at the private repo.

## Access

`cicaid-pro` is a private repository — see
[leonarduk/cicaid-pro](https://github.com/leonarduk/cicaid-pro) for
access.
