# 4 — Add CodeQL analysis (Python)

**URL:** https://github.com/leonarduk/cicaid/issues/4
**Labels:** enhancement
**State:** open

## What

Add a CodeQL workflow for static analysis, adapted from [allotmint-mcp's](https://github.com/leonarduk/allotmint-mcp/blob/main/.github/workflows/codeql.yml) — but for Python, not java-kotlin (cicaid has no Java code):

```yaml
name: CodeQL

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '30 4 * * 1'

jobs:
  analyze:
    name: Analyze (python)
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      packages: read
      actions: read
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: github/codeql-action/init@v4
        with:
          languages: python
      - uses: github/codeql-action/analyze@v4
        with:
          category: '/language:python'
```

No build step needed before `analyze` for Python (unlike allotmint-mcp's Maven compile step) — CodeQL's Python analysis works directly from source.

## Why

Static security analysis on every push/PR to main, matching the other leonarduk repos' baseline.

## Success looks like

- [ ] `.github/workflows/codeql.yml` added, language set to `python`
- [ ] Runs clean on a push to main