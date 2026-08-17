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

<!-- cicaid-version:start -->
```bash
pip install "cicaid-devtools @ https://github.com/leonarduk/cicaid/releases/download/v0.1.0/cicaid_devtools-0.1.0-py3-none-any.whl"
```
<!-- cicaid-version:end -->

This always points at the latest release — the install command above is updated
automatically as part of every release, so it never goes stale. Want an older
version instead? See [Releases](https://github.com/leonarduk/cicaid/releases) for
every version's exact install command.

The standard installation loads `GITHUB_TOKEN` and similar from a repo-root
`.env` file for local runs (CI should set real env vars instead). The historical
`[dotenv]` extra remains available as a backwards-compatible alias:

<!-- cicaid-version-dotenv:start -->
```bash
pip install "cicaid-devtools[dotenv] @ https://github.com/leonarduk/cicaid/releases/download/v0.1.0/cicaid_devtools-0.1.0-py3-none-any.whl"
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

## Releasing

Releases are cut from the GitHub UI, not by hand-bumping a version file —
`pyproject.toml` has no `version` field; [setuptools-scm](https://github.com/pypa/setuptools-scm)
derives it from the git tag at build time.

1. Go to [Releases → Draft a new release](https://github.com/leonarduk/cicaid/releases/new).
2. Create a new tag (the most recently published release is
   <!-- cicaid-latest-tag:start -->`v0.1.0`<!-- cicaid-latest-tag:end -->,
   so pick the next one) targeting `main`, and publish the release.

The [release workflow](.github/workflows/release.yml) is triggered when a `v*`
tag is pushed. Publishing through the GitHub UI as described above triggers it
by creating and pushing the new tag; publishing a release for an existing tag
does not trigger the workflow again. The workflow builds the sdist/wheel,
uploads them as release assets, and pushes a commit updating this README's
install commands and the tag above to the new version — all automatically.

## License

MIT — see [LICENSE](./LICENSE).
