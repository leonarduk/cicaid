# cicaid

One CLI for the repo automation every leonarduk project ends up needing: sync
issues locally, check out a branch for one, get an LLM review of your uncommitted
diff or an open PR, commit with an AI-drafted message, run a repo's local CI
checks, clean up stale AI-suggested issues. Install once, run `cicaid --help`,
and every command auto-detects which repo it's acting on from your `origin`
remote — no per-repo setup beyond an optional config file for the checks list.

## Install

<!-- cicaid-version:start -->
```bash
pip install "cicaid-devtools @ https://github.com/leonarduk/cicaid/releases/download/v0.4.4/cicaid_devtools-0.4.4-py3-none-any.whl"
```
<!-- cicaid-version:end -->

This always points at the latest release — the install command above is updated
automatically as part of every release, so it never goes stale. Want an older
version instead? See [Releases](https://github.com/leonarduk/cicaid/releases) for
every version's exact install command.

The `[dotenv]` extra loads `DEEPSEEK_API_KEY` and similar from a repo-root `.env`
file for local runs (CI should set real env vars instead):

<!-- cicaid-version-dotenv:start -->
```bash
pip install "cicaid-devtools[dotenv] @ https://github.com/leonarduk/cicaid/releases/download/v0.4.4/cicaid_devtools-0.4.4-py3-none-any.whl"
```
<!-- cicaid-version-dotenv:end -->

For tracking an unreleased commit instead of a tagged version:

```bash
pip install "cicaid-devtools @ git+https://github.com/leonarduk/cicaid.git@<ref>"
```

## Quick start

```bash
cd your-repo                 # any repo with a github.com origin remote
cicaid --help                # list every command
cicaid sync-issues           # pull open issues into ./issues/*.md
cicaid work-on-issue 123     # branch + checkout for issue #123
cicaid local-review          # LLM review of your uncommitted changes
cicaid commit-and-push       # commit with an AI-drafted message, push
cicaid publish-pr            # open the PR
cicaid run-ci-checks --list  # this repo's local check suite
```

## Commands

| Command | What it does |
|---|---|
| `sync-issues` | Sync GitHub issues to local markdown files |
| `create-issue` | Draft and create a new GitHub issue |
| `triage-issues` | Triage unmilestoned open issues |
| `work-on-issue` | Check out a branch for an issue |
| `work-on-pr` | Check out the branch for an open PR |
| `implement-issue-with-aider` | Extract an issue prompt for Aider |
| `run-ci-checks` | Run the local CI check suite |
| `local-review` | LLM-review uncommitted local changes |
| `pr-review` | LLM-review an open PR |
| `dependabot-auto-merge` | Auto-merge green Dependabot PRs |
| `review-issue` | Refresh a stale issue with an LLM |
| `add-issue-to-pr` | Link an issue to its PR |
| `clear-ai-slop-issues` | Detect and close duplicate/stale/AI-slop issues |
| `commit-and-push` | Commit with an LLM-drafted message and push |
| `publish-pr` | Publish a PR from the current branch |

Run any command with `--help` for its full flags. Every command above also
installs as `cicaid <command>` (e.g. `cicaid sync-issues`) if you'd rather
remember one name than fifteen.

### PowerShell wrappers

[`templates/`](templates/) has example PowerShell wrappers
(`j_commit_and_push.ps1`, `k_publish-pr.ps1`) that call the installed commands
above with named parameters, if you'd rather use that calling convention. Copy
them into a consuming repo — they aren't part of the installed package.

`templates/g_run_tests.ps1` is a plain example (`pytest tests --cov=backend`,
`allotmint`'s own test layout), not wired to a shared command — adapt it per repo.

### Local CI checks

`run-ci-checks` reads its check list from a `.cicaid-checks.toml` file in the
target repo's root (see `templates/allotmint-mcp.cicaid-checks.toml` for a
Maven/Java example), so it runs whatever *that* repo's own CI actually does. A
repo without a config file falls back to `DEFAULT_CHECKS` in
[`h_run_ci_checks.py`](src/cicaid_devtools/run_ci_checks.py) (allotmint's own
Python/npm/CDK checks — only correct for allotmint itself). Format:

```toml
[[checks]]
name = "build"
description = "What this check verifies"
workflow = ".github/workflows/whatever.yml"   # informational only
commands = ["./mvnw verify"]                  # run via `shell=True`, one at a time
```

## Package layout

```
src/cicaid_devtools/
  cli.py                                      # `cicaid` umbrella dispatcher
  a_sync_issues.py ... q_clear_ai_slop_issues.py   # the a_/b_/c_/.../q_ command chain
  lib/                                        # shared helpers (github_repo, llm_common,
                                               # ollama_common, remote_openai_common,
                                               # deepseek_review, review_common, ...)
```

## Development

```bash
pip install -e ".[test]"
pytest
```

## Releasing

Bump `version` in `pyproject.toml`, then push a matching tag:

```bash
git tag v0.4.0
git push origin v0.4.0
```

The [release workflow](.github/workflows/release.yml) builds the sdist/wheel,
publishes them as assets on a new GitHub Release, and pushes a commit updating
this README's install commands to the new version — all automatically.

## Background

The commands here used to be `scripts/developer_tools/`, duplicated (and slowly
drifting) between [`allotmint`](https://github.com/leonarduk/allotmint) and
[`allotmint-mcp`](https://github.com/leonarduk/allotmint-mcp). cicaid is the
single source of truth now — see
[allotmint-mcp#374](https://github.com/leonarduk/allotmint-mcp/issues/374) for
the original migration proposal and
[allotmint#6151](https://github.com/leonarduk/allotmint/issues/6151) /
[allotmint-mcp#404](https://github.com/leonarduk/allotmint-mcp/issues/404) /
[ai-systems-lab#81](https://github.com/leonarduk/ai-systems-lab/issues/81) for
the per-repo migrations.
