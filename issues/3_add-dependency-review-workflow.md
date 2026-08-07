# 3 — Add Dependency Review workflow

**URL:** https://github.com/leonarduk/cicaid/issues/3
**Labels:** enhancement
**State:** open

## What

Add a Dependency Review GitHub Actions workflow, matching [allotmint-mcp's](https://github.com/leonarduk/allotmint-mcp/blob/main/.github/workflows/dependency-review.yml):

```yaml
name: Dependency Review

on:
  pull_request:

permissions:
  contents: read

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/dependency-review-action@v5
        with:
          fail-on-severity: high
```

## Why

cicaid currently only has `release.yml` and `test.yml` — no supply-chain scanning on PRs. This is a small, self-contained, no-secrets-needed workflow (uses the default `GITHUB_TOKEN`), good first port.

## Success looks like

- [ ] `.github/workflows/dependency-review.yml` added
- [ ] Runs on PRs and flags high-severity new dependencies