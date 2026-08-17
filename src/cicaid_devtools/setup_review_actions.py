"""CLI to scaffold GitHub Actions review/quality workflows into a repo.

Generates ``.github/workflows/_ai-pr-review.yml`` (the reusable workflow) plus
a thin caller workflow per selected provider (DeepSeek and/or GPT), each
invoking the review logic from the installed ``cicaid-devtools`` package --
the same workflows this repo uses on itself, adapted to install
cicaid-devtools as a dependency instead of from a local checkout. Also
includes, by default, the other repo-agnostic workflows this repo runs on
itself: dependency-review.yml, workflow-lint.yml, codeql.yml, and pr-lint.yml (each
individually opt-out-able). Whether CodeQL is wanted (and for which
language(s)), whether Dependency Review is wanted, and whether PR linting is
wanted are interactively prompted for when running in a terminal and not already pinned down via CLI
flags -- non-interactively (CI, pipes, tests) they fall back to their
defaults without prompting. When Dependency Review is enabled, this also
checks whether the target repo's GitHub "Dependency graph" is turned on
(required for the review to have any data to work with) and attempts to
enable it via the API, since GitHub defaults it to off. Opens a branch + PR
with the generated files, and files a tracking issue. The optional
``--branch-protection`` flag also creates or updates a GitHub ruleset for the
repository's default branch.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

from cicaid_devtools.lib.github_issue_create import (
    create_issue_via_api,
    create_issue_via_gh,
    get_github_token,
)
from cicaid_devtools.lib.github_repo import get_repo_info, get_repo_root, is_wiki_repo
from cicaid_devtools.lib.publish_pr import (
    check_gh_available,
    check_working_tree_clean,
    create_pr,
    get_default_branch,
    push_to_remote,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# The review integrations these generated workflows import (review_diff,
# review_comment, deepseek_review, gpt_review, verdict, followups, etc.) live
# in cicaid-core, not in this (leonarduk/cicaid) "free shell" package -- see
# https://github.com/leonarduk/cicaid-core. cicaid-core is private, so it has
# no public releases API to query; the install is pinned to a fixed tag here
# instead of resolved dynamically, and cloned over git+https using a
# short-lived, request-scoped git credential (see PIP_INSTALL_CICAID_CORE_SCRIPT).
CICAID_CORE_REPO = "leonarduk/cicaid-core"
CICAID_CORE_REF = "v0.9.1"
CICAID_CORE_TOKEN_SECRET = "CICAID_CORE_TOKEN"
DEFAULT_BRANCH_NAME = "chore/setup-review-actions"
PROVIDERS = ("deepseek", "gpt")
INSTALL_SPEC_PLACEHOLDER = "__CICAID_INSTALL_SPEC__"
DEFAULT_BRANCH_RULESET_NAME = "Protect the default branch (cicaid)"
TRACKING_ISSUE_TITLE_PREFIX = "Track GitHub Actions setup"

REUSABLE_WORKFLOW_TEMPLATE = """name: Reusable AI PR Review

on:
  workflow_call:
    inputs:
      provider_name:
        description: "Display name of the reviewer (e.g. DeepSeek, GPT)"
        required: true
        type: string
      provider_id:
        description: "Lowercase identifier used for file/output naming (e.g. deepseek, gpt)"
        required: true
        type: string
      review_module:
        description: "Dotted module name of the provider's review integration (e.g. cicaid_devtools.lib.deepseek_review)"
        required: true
        type: string
      workflow_file:
        description: "Filename of the calling workflow, used in the posted comment link"
        required: true
        type: string
      deepseek_model:
        description: "DEEPSEEK_MODEL override passed to the review script, if any"
        required: false
        type: string
        default: ""
      deepseek_max_tokens:
        description: "DEEPSEEK_MAX_TOKENS override passed to the review script, if any"
        required: false
        type: string
        default: ""
      discussion_max_chars:
        description: "Max characters of PR discussion to include in the review prompt, if any (default 20000)"
        required: false
        type: string
        default: ""
    secrets:
      openai_api_key:
        description: "OpenAI API key, used for GPT reviews"
        required: false
      deepseek_api_key:
        description: "DeepSeek API key, used for DeepSeek reviews"
        required: false
      gh_token:
        description: "Token used for gh CLI calls (PR/issue read and write)"
        required: true
      cicaid_core_token:
        description: "Fine-grained PAT (Contents: Read-only) scoped to leonarduk/cicaid-core, used to install cicaid-devtools since the review modules (review_diff, review_comment, deepseek_review, gpt_review, etc.) only exist in the private cicaid-core package"
        required: true

# github.workflow resolves to the *calling* workflow's name (DeepSeek/GPT PR
# Review), so this groups per-provider without cross-cancelling other
# providers' runs for the same PR.
concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  ai-review:
    name: ${{ inputs.provider_name }} AI code review
    runs-on: ubuntu-latest
    if: ${{ github.actor != 'dependabot[bot]' }}
    permissions:
      pull-requests: write
      contents: read
      issues: write
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v7
        with:
          python-version: '3.12'

      # The AI-review modules this workflow imports below (review_diff,
      # review_comment, deepseek_review, gpt_review, etc.) only exist in the
      # private leonarduk/cicaid-core package, not this public "free shell"
      # repo -- installing from here either 404s or is missing these
      # modules. pip_install_cicaid_core.sh validates the token up front and
      # exposes the credential only to the pip process through GIT_CONFIG_*
      # variables.
      - name: Install cicaid-devtools (PR review helpers)
        env:
          CICAID_CORE_TOKEN: ${{ secrets.cicaid_core_token }}
        run: bash .github/scripts/pip_install_cicaid_core.sh pip install --retries 10 "__CICAID_INSTALL_SPEC__"

      - name: Get linked issue body
        id: issue
        env:
          GH_TOKEN: ${{ secrets.gh_token }}
        run: |
          # Only Closes/Fixes count as the closing reference; a contextual
          # 'Refs #N' must not be picked up as the linked issue (issue #409).
          ISSUE_NUM=$(gh pr view ${{ github.event.pull_request.number }} --json body,title \\
            | jq -r '[.title, .body] | join(" ")' \\
            | python3 -m cicaid_devtools.lib.linked_issue || true)
          if [ -n "$ISSUE_NUM" ]; then
            ISSUE_BODY=$(gh issue view "$ISSUE_NUM" --json body -q .body 2>/dev/null || echo "Issue not found")
          else
            ISSUE_BODY="No linked issue found. Review code on its own merits."
          fi
          DELIM="EOF_$(uuidgen | tr -d '-')"
          {
            echo "body<<$DELIM"
            echo "$ISSUE_BODY"
            echo "$DELIM"
          } >> "$GITHUB_OUTPUT"

      - name: Get PR diff
        id: diff
        env:
          BASE_REF: ${{ github.base_ref }}
          PR_TITLE: ${{ github.event.pull_request.title }}
          ISSUE_BODY: ${{ steps.issue.outputs.body }}
        run: |
          git fetch origin "$BASE_REF"
          DIFF=$(python3 -m cicaid_devtools.lib.review_diff \\
            --base-ref "$BASE_REF" \\
            --pr-title "$PR_TITLE" \\
            --issue-body "$ISSUE_BODY")
          DELIM="EOF_$(uuidgen | tr -d '-')"
          {
            echo "diff<<$DELIM"
            echo "$DIFF"
            echo "$DELIM"
          } >> "$GITHUB_OUTPUT"

      - name: Get PR discussion since last review
        id: discussion
        env:
          GH_TOKEN: ${{ secrets.gh_token }}
          DISCUSSION_MAX_CHARS: ${{ inputs.discussion_max_chars }}
        run: |
          MAX_CHARS_ARGS=()
          if [ -n "$DISCUSSION_MAX_CHARS" ]; then
            MAX_CHARS_ARGS=(--max-chars "$DISCUSSION_MAX_CHARS")
          fi
          DISCUSSION=$(python3 -m cicaid_devtools.lib.review_discussion \\
            --repo "${{ github.repository }}" \\
            --pr-number "${{ github.event.pull_request.number }}" \\
            --provider-name "${{ inputs.provider_name }}" \\
            "${MAX_CHARS_ARGS[@]}")
          DELIM="EOF_$(uuidgen | tr -d '-')"
          {
            echo "text<<$DELIM"
            echo "$DISCUSSION"
            echo "$DELIM"
          } >> "$GITHUB_OUTPUT"

      - name: Extract verified symbols from diff
        id: verified
        env:
          DIFF_OUTPUT: ${{ steps.diff.outputs.diff }}
        run: |
          VERIFIED=$(python3 -m cicaid_devtools.lib.verified_symbols \\
            --diff "$DIFF_OUTPUT")
          DELIM="EOF_$(uuidgen | tr -d '-')"
          {
            echo "facts<<$DELIM"
            echo "$VERIFIED"
            echo "$DELIM"
          } >> "$GITHUB_OUTPUT"

      - name: Call ${{ inputs.provider_name }} API
        env:
          OPENAI_API_KEY: ${{ secrets.openai_api_key }}
          DEEPSEEK_API_KEY: ${{ secrets.deepseek_api_key }}
          DEEPSEEK_MODEL: ${{ inputs.deepseek_model }}
          DEEPSEEK_MAX_TOKENS: ${{ inputs.deepseek_max_tokens }}
          PR_TITLE: ${{ github.event.pull_request.title }}
          DIFF: ${{ steps.diff.outputs.diff }}
          ISSUE_BODY: ${{ steps.issue.outputs.body }}
          DISCUSSION: ${{ steps.discussion.outputs.text }}
          VERIFIED_FACTS: ${{ steps.verified.outputs.facts }}
        run: |
          python3 -m ${{ inputs.review_module }} > /tmp/${{ inputs.provider_id }}_review_body.md

          # Guard: `-s` returns true only if the file exists AND has size > 0.
          # This distinguishes a successful API response (review body written to stdout)
          # from a failure (empty output, missing file, or API error).
          if [ ! -s /tmp/${{ inputs.provider_id }}_review_body.md ]; then
            echo "ERROR: ${{ inputs.provider_name }} review output was empty" >&2
            exit 1
          fi

      - name: Check ${{ inputs.provider_name }} approval
        id: check_approval
        continue-on-error: true  # REQUEST CHANGES exits 1; allow later steps (post comment, create issues) to still run
        run: |
          set +e
          python3 -m cicaid_devtools.lib.verdict /tmp/${{ inputs.provider_id }}_review_body.md "${{ inputs.provider_name }}"
          verdict_exit=$?
          set -e

          # Exit codes from extract_verdict.py: 0 = APPROVE, 2 = provider outage
          # (soft-fail, doesn't block merge), anything else = REQUEST CHANGES /
          # missing verdict (hard fail).
          if [ "$verdict_exit" -eq 0 ]; then
            echo "approved=true" >> "$GITHUB_OUTPUT"
          elif [ "$verdict_exit" -eq 2 ]; then
            echo "approved=skipped" >> "$GITHUB_OUTPUT"
          else
            echo "approved=false" >> "$GITHUB_OUTPUT"
            exit 1
          fi

      - name: Post ${{ inputs.provider_name }} review comment
        if: (success() || failure()) && !cancelled()
        continue-on-error: true  # If posting fails (e.g. API rate limit), don't fail job; review is also in Actions summary
        env:
          GH_TOKEN: ${{ secrets.gh_token }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        run: |
          python3 -m cicaid_devtools.lib.review_comment /tmp/${{ inputs.provider_id }}_review_body.md \\
            "${{ inputs.provider_name }}" "${{ inputs.workflow_file }}" "$RUN_URL" > /tmp/${{ inputs.provider_id }}_comment_body.md

          # Write to Actions job summary so the review is always visible in the UI,
          # even if the gh pr comment call below fails.
          cat /tmp/${{ inputs.provider_id }}_comment_body.md >> "$GITHUB_STEP_SUMMARY"

          if ! gh pr comment "$PR_NUMBER" --body-file /tmp/${{ inputs.provider_id }}_comment_body.md; then
            echo "::warning title=${{ inputs.provider_name }} review comment::Failed to post the ${{ inputs.provider_name }} review comment to PR #$PR_NUMBER — check the Actions log above for the gh error (rate limit, token scope, or network)."
            echo "WARNING: failed to post review comment — check the Actions log" >&2
            exit 0
          fi

      - name: Create follow-up issues
        if: steps.check_approval.outputs.approved == 'true'
        env:
          GH_TOKEN: ${{ secrets.gh_token }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
          OPENAI_API_KEY: ${{ secrets.openai_api_key }}
          DEEPSEEK_API_KEY: ${{ secrets.deepseek_api_key }}
          FOLLOWUP_LLM_PROVIDER: ${{ vars.FOLLOWUP_LLM_PROVIDER }}
          REPO_NAME: ${{ github.event.repository.name }}
        run: |
          # Fetch existing label names once and only create the ones missing,
          # instead of firing a gh label create call (and eating a 422) for
          # every label on every run.
          existing_labels="$(gh label list --json name -q '.[].name')"

          create_label_if_missing() {
            local name="$1" color="$2" description="$3"
            if ! grep -qxF "$name" <<< "$existing_labels"; then
              gh label create "$name" --color "$color" --description "$description" 2>/dev/null || true
            fi
          }

          create_label_if_missing "ai-suggested" "0075ca" "Suggested by AI code review"
          create_label_if_missing "haiku" "C5DEF5" "Suitable for Claude Haiku (simple/mechanical task)"
          create_label_if_missing "sonnet" "BFD4F2" "Suitable for Claude Sonnet (moderate reasoning)"
          create_label_if_missing "opus" "0052CC" "Suitable for Claude Opus (complex design/architecture)"

          # Extract titles to a file, then create issues via Python subprocess (no shell injection)
          python3 -m cicaid_devtools.lib.followups /tmp/${{ inputs.provider_id }}_review_body.md \\
            > /tmp/followups.json
          python3 -m cicaid_devtools.lib.followup_issues \\
            /tmp/followups.json "${PR_NUMBER}" /tmp/${{ inputs.provider_id }}_review_body.md

      - name: Add 'Changes Requested' label if review failed
        if: steps.check_approval.outputs.approved == 'false'
        continue-on-error: true
        env:
          GH_TOKEN: ${{ secrets.gh_token }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          # Create the label only if it doesn't already exist
          if ! gh label list --json name -q '.[].name' | grep -qxF "Changes Requested"; then
            gh label create "Changes Requested" --color "d73a49" --description "PR requested changes from code review" \\
              2>/dev/null || true
          fi

          # Add the label to the PR
          gh pr edit "$PR_NUMBER" --add-label "Changes Requested"

      - name: Remove 'Changes Requested' label if review approved
        if: steps.check_approval.outputs.approved == 'true'
        continue-on-error: true
        env:
          GH_TOKEN: ${{ secrets.gh_token }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: |
          # gh pr edit --remove-label errors when the label is not on the PR
          # (same caveat as github_issues.remove_issue_label), so only remove
          # it when it is currently applied -- keeps the step idempotent.
          if gh pr view "$PR_NUMBER" --json labels -q '.labels[].name' | grep -qxF "Changes Requested"; then
            gh pr edit "$PR_NUMBER" --remove-label "Changes Requested"
          fi

      - name: Fail if ${{ inputs.provider_name }} did not approve
        if: always() && contains(fromJson('["failure","skipped"]'), steps.check_approval.outcome)
        run: |
          echo "::error::${{ inputs.provider_name }} review: CHANGES REQUESTED — address the review findings before merging."
          exit 1
"""

CALLER_WORKFLOW_TEMPLATES = {
    "deepseek": """name: DeepSeek PR Review

on:
  pull_request:
    types: [opened, reopened, synchronize]

jobs:
  ai-review:
    if: ${{ github.actor != 'dependabot[bot]' && vars.ENABLE_DEEPSEEK_REVIEW != 'false' }}
    permissions:
      pull-requests: write
      contents: read
      issues: write
    uses: ./.github/workflows/_ai-pr-review.yml
    with:
      provider_name: DeepSeek
      provider_id: deepseek
      review_module: cicaid_devtools.lib.deepseek_review
      workflow_file: deepseek-pr-review.yml
    secrets:
      openai_api_key: ${{ secrets.OPENAI_API_KEY }}
      deepseek_api_key: ${{ secrets.DEEPSEEK_API_KEY }}
      gh_token: ${{ secrets.GITHUB_TOKEN }}
      cicaid_core_token: ${{ secrets.CICAID_CORE_TOKEN }}
""",
    "gpt": """name: GPT PR Review

on:
  pull_request:
    types: [opened, reopened, synchronize]

jobs:
  ai-review:
    if: ${{ github.actor != 'dependabot[bot]' && vars.ENABLE_GPT_REVIEW != 'false' }}
    permissions:
      pull-requests: write
      contents: read
      issues: write
    uses: ./.github/workflows/_ai-pr-review.yml
    with:
      provider_name: GPT
      provider_id: gpt
      review_module: cicaid_devtools.lib.gpt_review
      workflow_file: gpt-pr-review.yml
    secrets:
      openai_api_key: ${{ secrets.OPENAI_API_KEY }}
      deepseek_api_key: ${{ secrets.DEEPSEEK_API_KEY }}
      gh_token: ${{ secrets.GITHUB_TOKEN }}
      cicaid_core_token: ${{ secrets.CICAID_CORE_TOKEN }}
""",
}

PIP_INSTALL_CICAID_CORE_SCRIPT = """#!/usr/bin/env bash
# Runs a command (typically a pip install) with git credentials configured so it
# can clone the private leonarduk/cicaid-core repo. The AI-review modules the
# generated workflows import (review_diff, review_comment, deepseek_review,
# gpt_review, etc.) only exist in cicaid-core, not the public leonarduk/cicaid
# "free shell" package, so a plain pip install of the public wheel/repo 404s
# or is missing these modules.
#
# Fails fast with an actionable message if CICAID_CORE_TOKEN is unset or empty,
# instead of letting the wrapped command fail later with a confusing git auth
# error. The credential rewrite is scoped to exactly this invocation through
# Git's GIT_CONFIG_* environment variables; the token is never written to a
# config file.
#
# Uses `url.<base>.insteadOf` with the token embedded as URL userinfo, rather
# than a `credential.<url>.helper` shell snippet that reads the token from the
# env var at request time. The helper form looks more secure on paper (the raw
# token never touches disk), but empirically it is NOT reliable here: any
# pre-existing generic `credential.helper` (e.g. Git Credential Manager, or a
# local `gh auth login`) is consulted first and can supply -- or fail to yield
# to -- a different credential before a URL-scoped helper ever runs, since
# helpers accumulate across config scopes rather than "most specific wins".
# The `insteadOf` rewrite has no such ambiguity: the token is embedded
# directly in the URL, which git's transport layer uses unconditionally
# without consulting the credential-helper chain at all. GitHub's own PAT
# formats (ghp_/github_pat_/gho_/ghs_/ghr_) are always alphanumeric and never
# contain the URL-reserved characters (@, :, /) that would make this rewrite
# unsafe, so that's not a practical concern for the token this script expects.
#
# Usage: pip_install_cicaid_core.sh <command...>
# Required env: CICAID_CORE_TOKEN
set -euo pipefail

if [ -z "${CICAID_CORE_TOKEN:-}" ]; then
  echo "::error::CICAID_CORE_TOKEN is empty or unset. Add a fine-grained PAT (Contents: Read-only, scoped to leonarduk/cicaid-core) as the CICAID_CORE_TOKEN repository secret (Settings > Secrets and variables > Actions) before this workflow can install cicaid-devtools." >&2
  exit 1
fi

export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0="url.https://x-access-token:${CICAID_CORE_TOKEN}@github.com/leonarduk/cicaid-core.insteadOf"
export GIT_CONFIG_VALUE_0="https://github.com/leonarduk/cicaid-core"

exec "$@"
"""

DEPENDENCY_REVIEW_TEMPLATE = """name: Dependency Review

on:
  pull_request:

permissions:
  contents: read

jobs:
  dependency-review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/dependency-review-action@v5.0.0
        with:
          fail-on-severity: high
"""

CODEQL_LANGUAGES_PLACEHOLDER = "__CICAID_CODEQL_LANGUAGES__"

# Matrix-based (one job per language) rather than a single multi-language job,
# matching GitHub's own default "Set up code scanning" template -- compiled
# languages (Java, C++, C#, Go, Swift) often need a per-language autobuild
# step, which a shared job can't isolate cleanly.
CODEQL_TEMPLATE = """name: CodeQL

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: "30 4 * * 1"

jobs:
  analyze:
    name: Analyze (${{ matrix.language }})
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      actions: read
      contents: read
    strategy:
      fail-fast: false
      matrix:
        language: [__CICAID_CODEQL_LANGUAGES__]
    steps:
      - uses: actions/checkout@v7
      - uses: github/codeql-action/init@v4
        with:
          languages: ${{ matrix.language }}
      - uses: github/codeql-action/analyze@v4
        with:
          category: "/language:${{ matrix.language }}"
"""

WORKFLOW_LINT_TEMPLATE = """name: Workflow Lint

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  actionlint:
    runs-on: ubuntu-latest
    continue-on-error: true
    steps:
      - uses: actions/checkout@v4

      - name: Download actionlint
        run: |
          curl -sSL https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash | bash -s -- latest /usr/local/bin
        shell: bash

      - name: Lint workflow files
        run: |
          actionlint -color -shellcheck= .github/workflows/*.yml
        shell: bash
"""

PR_LINT_TEMPLATE = r"""name: PR Body Issue Reference Check

on:
  pull_request:
    types: [opened, edited, synchronize, reopened, ready_for_review]

permissions:
  contents: read

jobs:
  require-issue-reference:
    if: ${{ github.event.pull_request.user.login != 'dependabot[bot]' && github.event.pull_request.draft == false }}
    runs-on: ubuntu-latest
    steps:
      - name: Validate pull request body includes issue reference
        env:
          PR_BODY: ${{ github.event.pull_request.body }}
        run: |
          body="${PR_BODY:-}"

          if printf '%s' "$body" | grep -iPq '(closes|fixes|resolves|refs|relates\s+to)\s+#\d+'; then
            echo 'PR body includes a valid issue reference.'
            exit 0
          fi

          echo 'Pull request body must include an issue reference such as Closes #123, Fixes #123, Resolves #123, Refs #123, or Relates to #123.' >&2
          exit 1
"""

# GitHub issue templates installed into the target repo during setup
# (issue #334). Content mirrors this repo's own .github/ISSUE_TEMPLATE/*
# (byte-identical to allotmint's), embedded as constants so the installed
# wheel needs no extra data files; tests guard against drift.
BUG_REPORT_TEMPLATE = """---
name: Bug report
about: Report something that is broken or behaving incorrectly
title: ""
labels: bug
assignees: ""
---

## What

<!-- What is broken? Describe the observed behavior, including exact error
messages, screenshots, or logs where relevant. -->

## Why

<!-- Why does this matter? What's the user/dev impact of leaving it broken? -->

## How

<!-- Steps to reproduce, and (if you know it) what the fix likely involves. -->

1.
2.
3.

**Expected behavior:**

**Actual behavior:**

**Environment:** (backend/frontend/CDK, browser, OS, commit/branch)

## Files Affected

<!-- List the specific file paths (from the repo root) that need to be
changed, added, or deleted to fix this. Use one path per line. -->

## Constraints

<!-- Anything the fix must not break, e.g. "must not change the public API
shape" or "must preserve bash/PowerShell parity". -->

## LLM tier

<!-- If this will be worked by an AI agent, suggest a tier: haiku / sonnet / opus -->

## Value

<!-- How much impact/priority does this have: Low Value / Medium Value / High Value
- High Value: real bugs, security/auth gaps, financial-data correctness issues,
  or substantive product features.
- Medium Value: reliability/observability improvements with real (if non-urgent)
  blast radius, or consolidated multi-item hardening/test-coverage backlogs.
- Low Value: single-file "add a test for X" / rename / doc-comment /
  formatting-only suggestions with no functional risk. -->

## Success looks like

- [ ]

## Failure looks like

-
"""

ISSUE_TEMPLATE_CONFIG = """blank_issues_enabled: true
contact_links: []
"""

FEATURE_REQUEST_TEMPLATE = """---
name: Feature request
about: Propose a new feature or enhancement
title: ""
labels: enhancement
assignees: ""
---

## What

<!-- What should be built or changed? -->

## Why

<!-- Why is this needed? What problem does it solve, or what value does it add? -->

## How

<!-- Outline the intended approach at a high level. Link to affected files or
areas of the codebase if known. -->

## Files Affected

<!-- List the specific file paths (from the repo root) that need to be
changed, added, or deleted to implement this. Use one path per line. -->

## Constraints

<!-- Anything the implementation must respect, e.g. "no application code
changes", "must confirm licensing decisions before implementing", scope
boundaries, backwards compatibility requirements. -->

## LLM tier

<!-- If this will be worked by an AI agent, suggest a tier and briefly justify
it: haiku (mechanical/additive) / sonnet (judgment required) / opus (complex,
cross-cutting) -->

## Value

<!-- How much impact/priority does this have: Low Value / Medium Value / High Value
- High Value: real bugs, security/auth gaps, financial-data correctness issues,
  or substantive product features.
- Medium Value: reliability/observability improvements with real (if non-urgent)
  blast radius, or consolidated multi-item hardening/test-coverage backlogs.
- Low Value: single-file "add a test for X" / rename / doc-comment /
  formatting-only suggestions with no functional risk. -->

## Success looks like

- [ ]

## Failure looks like

-
"""

ISSUE_TEMPLATE_FILES = {
    ".github/ISSUE_TEMPLATE/bug_report.md": BUG_REPORT_TEMPLATE,
    ".github/ISSUE_TEMPLATE/config.yml": ISSUE_TEMPLATE_CONFIG,
    ".github/ISSUE_TEMPLATE/feature_request.md": FEATURE_REQUEST_TEMPLATE,
}

SECRET_NAMES = {"deepseek": "DEEPSEEK_API_KEY", "gpt": "OPENAI_API_KEY"}


def get_cicaid_core_install_spec(ref: str = CICAID_CORE_REF) -> str:
    """Return the pip install spec for cicaid-devtools, pinned to a cicaid-core ref.

    cicaid-core is private, so unlike this repo it has no public releases API
    to query for "latest" -- and even if it did, an unauthenticated lookup
    would 404. The generated workflow clones it over git+https using a
    request-scoped credential (CICAID_CORE_TOKEN, injected by
    pip_install_cicaid_core.sh), so the install spec here is just the git URL
    pinned to a fixed, known-good tag rather than a resolved release asset.
    """
    return f"cicaid-devtools @ git+https://github.com/{CICAID_CORE_REPO}.git@{ref}"


def prompt_yes_no(question: str, default: bool) -> bool:
    """Ask a yes/no question interactively; return `default` unanswered.

    Non-interactive runs (CI, pipes, tests -- anywhere stdin isn't a TTY)
    never prompt, so this is a no-op there and existing scripted/CI usage
    keeps working unchanged.
    """
    if not sys.stdin.isatty():
        return default
    suffix = "[Y/n]" if default else "[y/N]"
    try:
        answer = input(f"{question} {suffix}: ").strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in ("y", "yes")


def prompt_text(question: str, default: str) -> str:
    """Ask a free-text question interactively; return `default` unanswered."""
    if not sys.stdin.isatty():
        return default
    try:
        answer = input(f"{question} [{default}]: ").strip()
    except EOFError:
        return default
    return answer or default


def ensure_dependency_graph_enabled(owner: str, repo: str, token: str) -> None:
    """Best-effort: turn on GitHub's Dependency graph for the target repo, so
    dependency-review.yml has data to check PRs against -- GitHub defaults it
    to off (see https://github.blog/changelog/2025-06-17-dependency-graph-now-defaults-to-off/).

    The REST API has no "graph only" toggle (unlike the repo Settings UI):
    the same `vulnerability-alerts` endpoint that enables the dependency
    graph also turns on Dependabot alerts. Never fails the run -- just logs
    guidance to enable it manually if the automatic attempt doesn't work
    (e.g. insufficient permissions, org-level policy disabling it).
    """
    settings_url = f"https://github.com/{owner}/{repo}/settings/security_analysis"
    api_url = f"https://api.github.com/repos/{owner}/{repo}/vulnerability-alerts"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {token}",
    }
    try:
        check = requests.get(api_url, headers=headers, timeout=10)
        if check.status_code == 204:
            logger.info("Dependency graph is already enabled for %s/%s.", owner, repo)
            return
        enable = requests.put(api_url, headers=headers, timeout=10)
        if enable.status_code == 204:
            logger.info(
                "Enabled the dependency graph (and Dependabot alerts) for %s/%s.", owner, repo
            )
        else:
            logger.warning(
                "Could not enable the dependency graph automatically (HTTP %s). "
                "Enable it manually: %s",
                enable.status_code, settings_url,
            )
    except requests.RequestException as exc:
        logger.warning(
            "Could not check/enable the dependency graph (%s). Enable it manually: %s",
            exc, settings_url,
        )


def ensure_default_branch_ruleset(owner: str, repo: str, token: str) -> bool:
    """Create or update cicaid's ruleset protecting the default branch."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/rulesets"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {
        "name": DEFAULT_BRANCH_RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {
                "type": "pull_request",
                "parameters": {
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 0,
                    "required_review_thread_resolution": True,
                },
            },
        ],
    }
    settings_url = f"https://github.com/{owner}/{repo}/settings/rules"
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        existing = next(
            (item for item in response.json() if item.get("name") == DEFAULT_BRANCH_RULESET_NAME),
            None,
        )
        if existing:
            response = requests.put(
                f"{api_url}/{existing['id']}", headers=headers, json=payload, timeout=10
            )
            action = "Updated"
        else:
            response = requests.post(api_url, headers=headers, json=payload, timeout=10)
            action = "Created"
        response.raise_for_status()
        logger.info("%s default-branch ruleset for %s/%s.", action, owner, repo)
        return True
    except (requests.RequestException, KeyError, TypeError, ValueError) as exc:
        logger.error(
            "Could not configure default-branch protection (%s). Check admin access or "
            "configure it manually: %s",
            exc,
            settings_url,
        )
        return False


def render_codeql_languages(languages: list[str]) -> str:
    """Render a YAML flow-sequence body (e.g. "'python', 'javascript'") for
    the CodeQL matrix's `language:` list.
    """
    return ", ".join(f"'{lang}'" for lang in languages)


def render_workflows(
    install_spec: str,
    providers: list[str],
    *,
    dependency_review: bool = True,
    workflow_lint: bool = True,
    codeql: bool = True,
    pr_lint: bool = True,
    codeql_languages: list[str] = ("python",),
) -> dict[str, str]:
    """Build the {relative path: file content} map for the selected extras."""
    files = {
        ".github/workflows/_ai-pr-review.yml": REUSABLE_WORKFLOW_TEMPLATE.replace(
            INSTALL_SPEC_PLACEHOLDER, install_spec
        ),
        # Required by the "Install cicaid-devtools" step above -- cicaid-core
        # is private, so the install needs a scoped git credential injected
        # via this wrapper rather than a plain `pip install`.
        ".github/scripts/pip_install_cicaid_core.sh": PIP_INSTALL_CICAID_CORE_SCRIPT,
    }
    for provider in providers:
        files[f".github/workflows/{provider}-pr-review.yml"] = CALLER_WORKFLOW_TEMPLATES[provider]
    if dependency_review:
        files[".github/workflows/dependency-review.yml"] = DEPENDENCY_REVIEW_TEMPLATE
    if workflow_lint:
        files[".github/workflows/workflow-lint.yml"] = WORKFLOW_LINT_TEMPLATE
    if pr_lint:
        files[".github/workflows/pr-lint.yml"] = PR_LINT_TEMPLATE
    if codeql:
        files[".github/workflows/codeql.yml"] = CODEQL_TEMPLATE.replace(
            CODEQL_LANGUAGES_PLACEHOLDER, render_codeql_languages(list(codeql_languages))
        )
    # Issue templates are always installed during setup (issue #334).
    files.update(ISSUE_TEMPLATE_FILES)
    return files


def write_files(files: dict[str, str]) -> list[str]:
    """Write each {relative path: content} entry to disk, creating parent dirs."""
    written = []
    for rel_path, content in files.items():
        path = Path(rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(rel_path)
    return written


def ensure_origin_default_branch(default_branch: str) -> None:
    """Make sure refs/remotes/origin/<default_branch> resolves, seeding if needed.

    Fresh/empty repos have no branches on origin, so ``origin/<default_branch>``
    cannot be used as a branch base and ``git checkout -b <branch>
    origin/<default>`` would crash (see #377). When it is missing, create the
    default branch locally -- from an unborn HEAD, or from the current local
    state -- commit an empty "Initial commit" if the branch has no commits yet,
    and push it with -u. Skipped entirely when origin/<default_branch> already
    resolves, so existing repos issue zero new git commands.
    """
    origin_default = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/remotes/origin/{default_branch}"],
        capture_output=True,
        check=False,
    )
    if origin_default.returncode == 0:
        return
    logger.info(
        "origin/%s does not exist yet (fresh/empty repo); seeding it.", default_branch
    )
    local_default = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/heads/{default_branch}"],
        capture_output=True,
        check=False,
    )
    if local_default.returncode == 0:
        subprocess.run(["git", "checkout", default_branch], check=True)
    else:
        subprocess.run(["git", "checkout", "-b", default_branch], check=True)
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        capture_output=True,
        check=False,
    )
    if head.returncode != 0:
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "Initial commit"], check=True
        )
    subprocess.run(["git", "push", "-u", "origin", default_branch], check=True)


def create_branch_from_default(branch: str, default_branch: str) -> bool:
    """Fetch origin and check out `branch`.

    Creates it from origin/<default_branch> if it doesn't exist yet locally;
    otherwise reuses it when the branch still exists on origin. A local branch
    that has since been deleted from origin is reset to the default branch so
    an earlier incarnation cannot make the subsequent push non-fast-forward.
    Seeding runs up front (not just before the final checkout) because the
    reset path also references origin/<default_branch> and must not crash on a
    fresh/empty repo either.
    """
    subprocess.run(["git", "fetch", "--prune", "origin"], check=True)
    ensure_origin_default_branch(default_branch)
    local = subprocess.run(
        ["git", "rev-parse", "--verify", f"refs/heads/{branch}"],
        capture_output=True,
        check=False,
    )
    if local.returncode == 0:
        logger.info("Branch '%s' already exists locally; reusing it.", branch)
        subprocess.run(["git", "checkout", branch], check=True)
        remote = subprocess.run(
            ["git", "rev-parse", "--verify", f"refs/remotes/origin/{branch}"],
            capture_output=True,
            check=False,
        )
        if remote.returncode != 0:
            logger.info(
                "Branch '%s' no longer exists on origin; resetting it to origin/%s.",
                branch,
                default_branch,
            )
            subprocess.run(
                ["git", "reset", "--hard", f"origin/{default_branch}"], check=True
            )
        return False
    subprocess.run(["git", "checkout", "-b", branch, f"origin/{default_branch}"], check=True)
    return True


def cleanup_local_branch(branch: str, default_branch: str) -> bool:
    """Return to the default branch and force-delete a failed setup branch.

    Cleanup is best-effort so a cleanup error does not obscure the push
    failure that prompted it.
    """
    try:
        subprocess.run(["git", "checkout", default_branch], check=True)
        subprocess.run(["git", "branch", "-D", branch], check=True)
    except subprocess.CalledProcessError as exc:
        logger.warning("Could not clean up local branch '%s': %s", branch, exc)
        return False
    logger.info("Cleaned up local branch '%s' after the push failed.", branch)
    return True


def diff_against_default_branch(files: dict[str, str], default_branch: str) -> dict[str, str]:
    """Return the entries of `files` whose content differs from what's already
    on origin/<default_branch> (or that don't exist there yet). Assumes
    origin has already been fetched.
    """
    changed = {}
    for path, content in files.items():
        result = subprocess.run(
            ["git", "show", f"origin/{default_branch}:{path}"],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )
        current = result.stdout if result.returncode == 0 else None
        if current != content:
            changed[path] = content
    return changed


def derive_branch_name(issue_number: str | None) -> str:
    """Name the setup branch after the tracking issue, so reruns (which file a
    fresh issue each time) never collide with a previous attempt's branch.
    """
    if issue_number:
        return f"chore/issue-{issue_number}-setup-review-actions"
    return DEFAULT_BRANCH_NAME


def issue_is_open(owner: str, repo: str, issue_number: str) -> bool:
    """True when ``gh issue view`` reports the given issue as open."""
    result = subprocess.run(
        ["gh", "issue", "view", issue_number, "--repo", f"{owner}/{repo}", "--json", "state"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return False
    try:
        return json.loads(result.stdout).get("state") == "open"
    except json.JSONDecodeError:
        return False


def find_existing_tracking_issue(owner: str, repo: str) -> str | None:
    """Return the number of the most recent open setup-tracking issue, or None.

    Matches the ``Track GitHub Actions setup (...)`` title prefix this tool files
    its tracking issues under, so a re-run after a crash (see #377/#378) can reuse
    the previous run's tracker instead of duplicating it. When several are open,
    the most recently created (highest number) wins. A ``gh`` failure is logged
    and treated as "none found" -- the caller decides whether that is fatal.
    """
    result = subprocess.run(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            f"{owner}/{repo}",
            "--state",
            "open",
            "--search",
            f'"{TRACKING_ISSUE_TITLE_PREFIX}" in:title',
            "--json",
            "number,title",
            "--limit",
            "50",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        logger.warning(
            "Could not search for an existing tracking issue: %s", result.stderr.strip()
        )
        return None
    try:
        issues = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    numbers = [int(item["number"]) for item in issues if item.get("number")]
    return str(max(numbers)) if numbers else None


EXTRA_LABELS = (
    ("dependency-review.yml", "dependency review"),
    ("workflow-lint.yml", "workflow lint"),
    ("codeql.yml", "CodeQL"),
    ("pr-lint.yml", "PR lint"),
)


def describe_included(providers: list[str], paths: list[str]) -> str:
    """Human-readable summary of everything actually generated (for commit,
    issue, and PR titles). Derived from `paths` rather than hardcoded, so it
    can't drift out of sync when an extra is toggled off via CLI flags.
    """
    parts = list(providers)
    for filename, label in EXTRA_LABELS:
        if any(path.endswith(f"/{filename}") for path in paths):
            parts.append(label)
    return ", ".join(parts)


def build_issue_body(providers: list[str], written: list[str]) -> str:
    """Build the tracking issue body for the review-actions setup."""
    files_list = "\n".join(f"- `{path}`" for path in written)
    secrets_list = "\n".join(f"- `{SECRET_NAMES[p]}` (for {p})" for p in providers)
    secrets_list += f"\n- `{CICAID_CORE_TOKEN_SECRET}` (fine-grained PAT, Contents: Read-only, scoped to leonarduk/cicaid-core -- required to install cicaid-devtools)"
    return (
        "## What\n\n"
        f"Set up GitHub Actions: {describe_included(providers, written)}, "
        "using the shared workflows from "
        "[cicaid-devtools](https://github.com/leonarduk/cicaid-core).\n\n"
        "## Why\n\n"
        "To get automated PR review and baseline security/quality checks without "
        "hand-rolling the workflow, review-posting, and follow-up-issue logic per repo.\n\n"
        "## How\n\n"
        f"`cicaid setup-review-actions` generated the following files on a branch "
        f"and opened a PR:\n\n{files_list}\n\n"
        "## Files Affected\n\n"
        f"{files_list}\n\n"
        "## Constraints\n\n"
        "None\n\n"
        "## LLM tier\n\n"
        "haiku\n\n"
        "## Value\n\n"
        "Medium Value\n\n"
        "## Success looks like\n\n"
        "- [ ] The generated PR is merged\n"
        "- [ ] The following repository secrets are provisioned "
        "(Settings → Secrets and variables → Actions → Secrets):\n"
        f"{secrets_list}\n"
        "- [ ] A subsequent PR shows a review comment from each enabled provider\n\n"
        "## Failure looks like\n\n"
        "- The review workflows fail on every PR because a required secret is missing\n"
        "- No review comment is posted despite the workflows running"
    )


def build_pr_body(providers: list[str], written: list[str], issue_number: str | None) -> str:
    """Build the PR body for the review-actions setup PR."""
    files_list = "\n".join(f"- `{path}`" for path in written)
    body = (
        "## What\n"
        f"Adds GitHub Actions ({describe_included(providers, written)}):\n\n{files_list}\n\n"
        "## Why\n"
        "Automated PR review coverage, reusing the shared review logic "
        "shipped in the `cicaid-devtools` package.\n\n"
        "## Testing\n"
        "N/A (workflow files; will run on the next PR opened against this repo).\n\n"
        "## Checklist\n"
        f"- [ ] Provision `{CICAID_CORE_TOKEN_SECRET}` (fine-grained PAT, Contents: "
        "Read-only, scoped to leonarduk/cicaid-core) under Settings → Secrets and "
        "variables → Actions -- required to install cicaid-devtools at all\n"
        "- [ ] Provision the required API key secret(s) under Settings → "
        "Secrets and variables → Actions\n"
        "- [ ] Confirm a review comment is posted on the next PR"
    )
    if issue_number:
        body += f"\n\nCloses #{issue_number}"
    return body


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scaffold AI review GitHub Actions into the current repo (branch + PR + issue)"
    )
    parser.add_argument(
        "--providers",
        default=",".join(PROVIDERS),
        help=f"Comma-separated reviewers to wire up (default: {','.join(PROVIDERS)})",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help=(
            "Branch name to create (default: derived from the tracking issue, "
            f"e.g. 'chore/issue-123-setup-review-actions', or '{DEFAULT_BRANCH_NAME}' "
            "when no tracking issue number is known)"
        ),
    )
    parser.add_argument(
        "--no-issue",
        action="store_true",
        help=(
            "Skip creating a tracking issue (pass --issue N to reuse an existing "
            "open one instead)"
        ),
    )
    parser.add_argument(
        "--issue",
        default=None,
        help=(
            "Reuse existing open tracking issue <number> instead of creating a new "
            "one (implies --no-issue). The PR body closes it with 'Closes #<number>', "
            "so the generated pr-lint passes while keeping a single tracker across "
            "re-runs (e.g. after a crash)."
        ),
    )
    parser.add_argument(
        "--dependency-review",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Include dependency-review.yml, and try to enable GitHub's Dependency "
            "graph on the repo (default: prompt interactively, else included)"
        ),
    )
    parser.add_argument(
        "--workflow-lint",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include workflow-lint.yml (actionlint) (default: included)",
    )
    parser.add_argument(
        "--codeql",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Include codeql.yml (default: prompt interactively, else included)",
    )
    parser.add_argument(
        "--pr-lint",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Include pr-lint.yml to require issue references in pull request bodies "
            "(default: prompt interactively, else included)"
        ),
    )
    parser.add_argument(
        "--codeql-language",
        default=None,
        help=(
            "Comma-separated language(s) passed to the CodeQL workflow, e.g. "
            "'python,javascript' (default: prompt interactively, else python)"
        ),
    )
    parser.add_argument(
        "--branch-protection",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "Create or update a GitHub ruleset protecting the repository's default branch "
            "(default: disabled)"
        ),
    )
    return parser


def main() -> int:
    """File the tracking issue, then branch (named after it), commit, and PR.

    The issue is created before the branch so the branch name -- and the
    commit/PR that reference it -- can embed the issue number, which also
    means each run gets its own uniquely-named branch instead of colliding
    with a previous attempt's.
    """
    args = build_arg_parser().parse_args()

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    unknown = [p for p in providers if p not in PROVIDERS]
    if unknown:
        logger.error("Unknown provider(s): %s (choices: %s)", ", ".join(unknown), ", ".join(PROVIDERS))
        return 1
    if not providers:
        logger.error("No providers selected.")
        return 1

    try:
        os.chdir(get_repo_root())
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    try:
        owner, repo = get_repo_info()
    except ValueError as exc:
        logger.error("%s", exc)
        return 1

    if is_wiki_repo():
        logger.error(
            "%s/%s is a wiki repo; GitHub Actions and PRs aren't supported there.", owner, repo
        )
        return 1

    check_gh_available()

    if not check_working_tree_clean():
        logger.error("Working tree has uncommitted changes. Commit or stash them first.")
        return 1

    default_branch = get_default_branch(owner, repo)
    logger.info("Target repo: %s/%s (default branch: %s)", owner, repo, default_branch)

    subprocess.run(["git", "fetch", "origin"], check=True)

    codeql = (
        args.codeql
        if args.codeql is not None
        else prompt_yes_no("Set up CodeQL code scanning?", default=True)
    )
    codeql_languages = ["python"]
    if codeql:
        language_input = args.codeql_language or prompt_text(
            "CodeQL language(s), comma-separated", default="python"
        )
        codeql_languages = [lang.strip() for lang in language_input.split(",") if lang.strip()]

    dependency_review = (
        args.dependency_review
        if args.dependency_review is not None
        else prompt_yes_no(
            "Enable Dependency Review? (also enables GitHub's Dependency graph + "
            "Dependabot alerts on the repo)",
            default=True,
        )
    )

    pr_lint = (
        args.pr_lint
        if args.pr_lint is not None
        else prompt_yes_no(
            "Require pull request bodies to reference an issue?", default=True
        )
    )

    token: str | None = None
    if args.branch_protection:
        token = get_github_token()
        if not ensure_default_branch_ruleset(owner, repo, token):
            return 1

    install_spec = get_cicaid_core_install_spec()
    files = render_workflows(
        install_spec,
        providers,
        dependency_review=dependency_review,
        workflow_lint=args.workflow_lint,
        codeql=codeql,
        codeql_languages=codeql_languages,
        pr_lint=pr_lint,
    )

    changed_files = diff_against_default_branch(files, default_branch)
    if not changed_files:
        logger.info("Workflow files already match '%s'; nothing to do.", default_branch)
        return 0

    if dependency_review:
        token = get_github_token()
        ensure_dependency_graph_enabled(owner, repo, token)

    issue_url = None
    issue_number = None
    if args.issue:
        if not args.issue.isdigit():
            logger.error("--issue expects a numeric issue number, got '%s'.", args.issue)
            return 1
        issue_number = args.issue
        if not issue_is_open(owner, repo, issue_number):
            logger.error(
                "Issue #%s does not exist or is not open; --issue needs an existing "
                "open tracking issue to reference.",
                issue_number,
            )
            return 1
        issue_url = f"https://github.com/{owner}/{repo}/issues/{issue_number}"
        logger.info("Reusing existing tracking issue: %s", issue_url)
    elif not args.no_issue:
        # Reuse the most recent open setup-tracking issue (e.g. a crash re-run,
        # see #377) instead of stranding a duplicate; only file a fresh one when
        # none is open. Completed setups close theirs via 'Closes #N' in the PR
        # body, so a genuine re-setup still gets a new tracker.
        existing = find_existing_tracking_issue(owner, repo)
        if existing:
            issue_number = existing
            issue_url = f"https://github.com/{owner}/{repo}/issues/{issue_number}"
            logger.info("Reusing existing tracking issue: %s", issue_url)
        else:
            token = token or get_github_token()
            issue_title = f"Track GitHub Actions setup ({describe_included(providers, list(files))})"
            issue_body = build_issue_body(providers, list(files))
            issue_url = create_issue_via_api(owner, repo, issue_title, issue_body, ["enhancement"], token)
            if not issue_url:
                issue_url = create_issue_via_gh(owner, repo, issue_title, issue_body, ["enhancement"])
            if issue_url:
                match = re.search(r"/issues/(\d+)", issue_url)
                issue_number = match.group(1) if match else None
                logger.info("Created tracking issue: %s", issue_url)
            else:
                logger.error(
                    "Failed to create the tracking issue via both the API and the gh CLI. "
                    "Pass --no-issue to skip it, or fix GitHub auth and retry."
                )
                return 1
    else:
        # --no-issue without --issue: never open a PR that the pr-lint.yml we
        # generate would reject. Reuse an existing open setup-tracking issue (the
        # #377 crash-recovery flow) or, when pr-lint is enabled, fail fast.
        existing = find_existing_tracking_issue(owner, repo)
        if existing:
            issue_number = existing
            issue_url = f"https://github.com/{owner}/{repo}/issues/{issue_number}"
            logger.info("Reusing existing tracking issue: %s", issue_url)
        elif pr_lint:
            logger.error(
                "No existing '%s' issue found to reference, and pr-lint.yml "
                "requires PR bodies to reference an issue. Pass --issue <number> "
                "to reference an existing issue, or drop --no-issue to create a "
                "fresh tracking issue.",
                TRACKING_ISSUE_TITLE_PREFIX,
            )
            return 1

    branch = args.branch or derive_branch_name(issue_number)
    branch_created = create_branch_from_default(branch, default_branch)
    written = write_files(files)

    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *written],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    if status.stdout.strip():
        subprocess.run(["git", "add", "--", *written], check=True)
        commit_message = f"Set up GitHub Actions ({describe_included(providers, written)})"
        if issue_number:
            commit_message += f"\n\nRefs #{issue_number}"
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
    else:
        logger.info("Branch '%s' already has these files committed; resuming.", branch)

    if not push_to_remote(branch):
        if branch_created:
            cleanup_local_branch(branch, default_branch)
        else:
            logger.info(
                "Leaving pre-existing local branch '%s' in place after the push failed.", branch
            )
        return 1

    pr_title = f"Set up GitHub Actions ({describe_included(providers, written)})"
    pr_body = build_pr_body(providers, written, issue_number)
    pr_url = create_pr(owner, repo, branch, default_branch, pr_title, pr_body)
    if not pr_url:
        logger.error("Failed to create PR.")
        return 1

    logger.info("\n[OK] PR created: %s", pr_url)
    if issue_url:
        logger.info("[OK] Tracking issue: %s", issue_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
