# CLAUDE.md

Fast orientation for working in `cicaid` — the public/free GitHub-plumbing CLI.
See [README.md](README.md) for full user-facing docs; this file is the
concise agent-facing companion.

## What this repo is

`cicaid` is the free, public shell of the `cicaid-devtools` package: issue
sync, branch/checkout-for-issue, checkout-for-PR, local CI checks, link PR to
issue, merge a PR, keep a PR's branch up to date with its base, and
auto-merge green Dependabot PRs.

The LLM-backed commands (`triage-issues`, `review-issue`, `create-issue`,
`local-review`, `pr-review`, `commit-and-push`, `implement-issue-with-aider`,
`clear-ai-slop-issues`) and `setup-review-actions` (scaffolds AI-review GitHub
Actions into a target repo — moved here in #477 since it only scaffolds
cicaid-pro's review logic, which never runs without cicaid-pro installed)
live in the sibling private repo **`cicaid-pro`** (`../cicaid-pro`), not
here. If asked to add/fix an LLM-review, triage, or review-scaffolding
feature, that's almost certainly the other repo — see
`../cicaid-pro/CLAUDE.md` and `../CLAUDE.md` for the workspace layout.

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

- **`cicaid-pro` depends on this package (`cicaid-devtools`) rather than
  duplicating it** (issue #472): `cicaid_devtools` is a PEP 420 namespace
  package (no `__init__.py`) so cicaid-pro's own LLM-backed modules merge
  into the same `cicaid_devtools.*` namespace from a sibling checkout.
  cicaid-pro installs as a separate distribution, `cicaid-devtools-pro`, so
  the two no longer collide on distribution name or clobber each other's
  files the way they used to. If both repos are checked out as siblings
  (they are here — `GitHub/cicaid/{cicaid,cicaid-pro}`), set up cicaid-pro's
  dev venv with `cicaid-pro/scripts/test_all.py`, or by hand: `pip install -e
  ../cicaid` then `pip install -e ".[test]"` from inside `cicaid-pro/`.
- No `version` field in `pyproject.toml` — version comes from
  `setuptools-scm` off the git tag at build time. Don't hand-edit a version.
- The `README.md` install commands and latest-tag comment
  (`<!-- cicaid-version:start -->` etc.) are updated automatically by the
  release workflow when a `v*` tag is pushed — don't hand-edit those blocks,
  they'll be overwritten on the next release anyway.
- `scripts/bump_readme_version.py`, `scripts/bump_wiki_version.py`,
  `scripts/version_bump.py` support the release workflow — check there before
  assuming a version/README sync issue needs a manual fix.

## Releasing

Cut from GitHub UI → Releases → Draft a new release → new `v*` tag targeting
`main`. Triggers [`.github/workflows/release.yml`](.github/workflows/release.yml),
which builds sdist/wheel, uploads release assets, and pushes a commit that
updates README install commands automatically.
