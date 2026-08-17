# CLAUDE.md

Fast orientation for working in `cicaid` — the public/free GitHub-plumbing CLI.
See [README.md](README.md) for full user-facing docs; this file is the
concise agent-facing companion.

## What this repo is

`cicaid` is the free, public shell of the `cicaid-devtools` package: issue
sync, branch/checkout-for-issue, checkout-for-PR, local CI checks, link PR to
issue, auto-merge green Dependabot PRs, and `setup-review-actions` (scaffolds
AI-review GitHub Actions into a target repo).

The LLM-backed commands (`triage-issues`, `review-issue`, `create-issue`,
`local-review`, `pr-review`, `commit-and-push`, `implement-issue-with-aider`,
`clear-ai-slop-issues`) live in the sibling private repo **`cicaid-core`**
(`../cicaid-core`), not here. If asked to add/fix an LLM-review or triage
feature, that's almost certainly the other repo — see
`../cicaid-core/CLAUDE.md` and `../CLAUDE.md` for the workspace layout.

## Quick start

```bash
pip install -e ".[test]"
pytest
```

- Entry point: `cicaid = "cicaid_devtools.cli:main"` (`src/cicaid_devtools/cli.py`)
- Commands live as top-level modules in `src/cicaid_devtools/` (e.g.
  `sync_issues.py`, `work_on_issue.py`, `run_ci_checks.py`), each with a
  `main()` also exposed as its own `[project.scripts]` entry in
  [pyproject.toml](pyproject.toml).
- Shared helpers: `src/cicaid_devtools/lib/` (`github_repo.py`,
  `github_issues.py`, `linked_issue.py`, `publish_pr.py`, ...).
- Tests: `tests/`, one `test_<module>.py` per command/lib module.
- Lint/format: `black` + `ruff` (line-length 100, target py311; see
  `[tool.black]` / `[tool.ruff]` in pyproject.toml).

## High-signal warnings

- **`cicaid` and `cicaid-core` both install as the same package name
  (`cicaid-devtools`) with the same `cicaid` entry point.** Installing both
  into one environment has the second `pip install` silently overwrite the
  first's files. If both repos are checked out as siblings (they are here —
  `GitHub/cicaid/{cicaid,cicaid-core}`), use cicaid-core's venv switcher
  (`cicaid-core/scripts/use.ps1 free` / `use.ps1 core`) instead of installing
  both by hand.
- No `version` field in `pyproject.toml` — version comes from
  `setuptools-scm` off the git tag at build time. Don't hand-edit a version.
- The `README.md` install commands and latest-tag comment
  (`<!-- cicaid-version:start -->` etc.) are updated automatically by the
  release workflow when a `v*` tag is pushed — don't hand-edit those blocks,
  they'll be overwritten on the next release anyway.
- `setup-review-actions` makes **no LLM calls itself**; it only scaffolds
  workflow YAML into a *target* repo that later calls into `cicaid-core`'s
  review logic using that target repo's own API-key secrets.
- `scripts/bump_readme_version.py`, `scripts/bump_wiki_version.py`,
  `scripts/version_bump.py` support the release workflow — check there before
  assuming a version/README sync issue needs a manual fix.

## Releasing

Cut from GitHub UI → Releases → Draft a new release → new `v*` tag targeting
`main`. Triggers [`.github/workflows/release.yml`](.github/workflows/release.yml),
which builds sdist/wheel, uploads release assets, and pushes a commit that
updates README install commands automatically.
