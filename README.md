# cicaid

One CLI for the GitHub-plumbing every repo ends up needing: sync issues,
branch onto one, check out a PR, run the repo's local CI checks, link a PR
back to its issue, auto-merge green Dependabot PRs. Install once — every
command auto-detects the repo from your `origin` remote.

This is the free shell. The LLM-backed commands (`triage-issues`,
`review-issue`, `create-issue`, `local-review`, `pr-review`,
`commit-and-push`, `implement-issue-with-aider`, `clear-ai-slop-issues`) are
part of [cicaid-pro](https://github.com/leonarduk/cicaid-pro), a private
package — `cicaid <command>` reports itself unavailable with a pointer there
until it's installed.

## Install

```bash
pip install cicaid-devtools
```

For tracking an unreleased commit instead of a tagged version:

```bash
pip install "cicaid-devtools @ git+https://github.com/leonarduk/cicaid.git@<ref>"
```

## Quick start

```bash
cd your-repo                 # any repo with a github.com origin remote
cicaid --help                # list every command
cicaid help work-on-issue    # show one command's usage and parameters
cicaid sync-issues           # pull open issues into ./issues/*.md
cicaid work-on-issue 123     # branch + checkout for issue #123
cicaid publish-pr            # open the PR
cicaid run-ci-checks --list  # this repo's local check suite
```

## Access to cicaid-pro

The LLM review/triage engine is the part of cicaid that's actually hard to
reproduce, and is kept in a private package, cicaid-pro. Contact the
maintainer for access.

## License

MIT — see [LICENSE](./LICENSE).
