# cicaid

CI/CD with AI in it.

This repo is the shared home for the `developer_tools` issue/PR/review automation
pipeline that was previously duplicated between
[`allotmint`](https://github.com/leonarduk/allotmint) and
[`allotmint-mcp`](https://github.com/leonarduk/allotmint-mcp) (see
[allotmint-mcp#374](https://github.com/leonarduk/allotmint-mcp/issues/374)). The two
copies had already drifted from each other; this package is now the single source of
truth, installed as a dependency by every consuming repo instead of vendored in-tree.

## Install

Each push of a `vX.Y.Z` tag builds a wheel and attaches it to a
[GitHub Release](https://github.com/leonarduk/cicaid/releases). Install a specific
release directly from its asset URL — pin the version explicitly for reproducible
installs, the same as any other pinned dependency:

```bash
pip install "cicaid-devtools @ https://github.com/leonarduk/cicaid/releases/download/v0.1.0/cicaid_devtools-0.1.0-py3-none-any.whl"
```

Check the [Releases page](https://github.com/leonarduk/cicaid/releases) for the
latest version and its exact asset URL. Optional extras work the same way:

```bash
pip install "cicaid-devtools[dotenv] @ https://github.com/leonarduk/cicaid/releases/download/v0.1.0/cicaid_devtools-0.1.0-py3-none-any.whl"
```

For tracking an unreleased commit (e.g. testing a fix before it's tagged), install
straight from git instead:

```bash
pip install "cicaid-devtools @ git+https://github.com/leonarduk/cicaid.git@<ref>"
```

`dotenv` enables loading `DEEPSEEK_API_KEY` and similar secrets from a repo-root
`.env` file during local, interactive runs (CI should set real env vars instead).

## Usage

Every command below auto-detects the owner/repo it's operating on from the `origin`
git remote of the directory you run it from — run them from inside whichever repo
you want to act on (`allotmint`, `allotmint-mcp`, `ai-systems-lab`, ...), not from
inside `cicaid` itself.

| Command | Replaces (old in-repo path) | What it does |
|---|---|---|
| `sync-issues` | `scripts/developer_tools/a_sync_issues.py` | Sync GitHub issues to local markdown files |
| `create-issue` | `scripts/developer_tools/b_create_issue.py` | Draft and create a new GitHub issue |
| `triage-issues` | `scripts/developer_tools/c_triage_issues.py` | Triage unmilestoned open issues |
| `work-on-issue` | `scripts/developer_tools/d_work_on_issue.py` | Check out a branch for an issue |
| `work-on-pr` | `scripts/developer_tools/e_work_on_pr.py` | Check out the branch for an open PR |
| `implement-issue-with-aider` | `scripts/developer_tools/f_implement_issue_with_aider.py` | Extract an issue prompt for Aider |
| `run-ci-checks` | `scripts/developer_tools/h_run_ci_checks.py` | Run the local CI check suite |
| `local-review` | `scripts/developer_tools/i_local_review.py` | LLM-review uncommitted local changes |
| `pr-review` | `scripts/developer_tools/l_pr_review.py` | LLM-review an open PR |
| `dependabot-auto-merge` | `scripts/developer_tools/m_dependabot_auto_merge.py` | Auto-merge green Dependabot PRs |
| `review-issue` | `scripts/developer_tools/o_review_issue.py` | Refresh a stale issue with an LLM |
| `add-issue-to-pr` | `scripts/developer_tools/p_add_issue_to_pr.py` | Link an issue to its PR |
| `clear-ai-slop-issues` | `scripts/developer_tools/q_clear_ai_slop_issues.py` | Detect and close duplicate/stale/AI-slop issues |
| `commit-and-push` | `scripts/developer_tools/lib/commit_and_push.py` | Commit with an LLM-drafted message and push |
| `publish-pr` | `scripts/developer_tools/lib/publish_pr.py` | Publish a PR from the current branch |

Run any command with `--help` for its full argument list.

### PowerShell wrappers

[`templates/`](templates/) has example PowerShell wrappers
(`j_commit_and_push.ps1`, `k_publish-pr.ps1`) that call the installed console
scripts above with named parameters. Copy these into a consuming repo if you want
the `.ps1` calling convention; they are not part of the installed package.

`templates/g_run_tests.ps1` is **not** wired to a console script — it invokes
`pytest tests --cov=backend`, which encodes `allotmint`'s own test layout. Treat it
as a starting point to adapt per repo, not a shared command.

`run-ci-checks` reads its check list from a `.cicaid-checks.toml` file in the target
repo's root (see `templates/allotmint-mcp.cicaid-checks.toml` for a Maven/Java
example). A repo with no config file falls back to `DEFAULT_CHECKS` in
[`h_run_ci_checks.py`](src/cicaid_devtools/h_run_ci_checks.py) — allotmint's own
pytest/npm/CDK checks, which is *only* correct for allotmint itself. Every other
consumer repo (allotmint-mcp, ai-systems-lab, ...) should add its own
`.cicaid-checks.toml` rather than rely on that fallback. Format:

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
  a_sync_issues.py ... q_clear_ai_slop_issues.py   # the a_/b_/c_/.../q_ CLI chain
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
git tag v0.2.0
git push origin v0.2.0
```

The [release workflow](.github/workflows/release.yml) builds the sdist/wheel and
publishes them as assets on a new GitHub Release automatically.

## Related issues

- [allotmint-mcp#374](https://github.com/leonarduk/allotmint-mcp/issues/374) — parent: move developer tools into a shared repo
- [allotmint#6151](https://github.com/leonarduk/allotmint/issues/6151) — migrate allotmint off its local copy
- [allotmint-mcp#404](https://github.com/leonarduk/allotmint-mcp/issues/404) — migrate allotmint-mcp off its local copy
- [ai-systems-lab#81](https://github.com/leonarduk/ai-systems-lab/issues/81) — adopt this package as a new consumer
