#!/usr/bin/env bash
# Apply branch protection rules from .github/branch-protection.json to the main branch.
# Prerequisites: gh CLI authenticated with repo scope.
# Usage: ./scripts/apply-branch-protection.sh [--verify]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_FILE="$REPO_ROOT/.github/branch-protection.json"
BRANCH="main"

if [ ! -f "$CONFIG_FILE" ]; then
  echo "ERROR: Config file not found: $CONFIG_FILE"
  exit 1
fi

apply() {
  echo "==> Applying branch protection to '$BRANCH'..."
  gh api -X PUT "repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/branches/$BRANCH/protection" \
    --input "$CONFIG_FILE" \
    --jq '"  enforce_admins: \(.enforce_admins.enabled)"'
  echo "  ✓ Applied successfully"
}

verify() {
  echo "==> Verifying branch protection on '$BRANCH'..."

  local repo
  repo=$(gh repo view --json nameWithOwner -q .nameWithOwner)
  local rules
  rules=$(gh api "repos/$repo/branches/$BRANCH/protection" 2>&1) || {
    echo "ERROR: $rules"
    exit 1
  }

  local failed=0
  check() {
    local field="$1" desc="$2" expected="$3"
    local actual
    actual=$(echo "$rules" | jq -r "$field")
    if [ "$actual" = "$expected" ]; then
      echo "  ✓ $desc: $actual"
    else
      echo "  ✗ $desc: expected '$expected', got '$actual'"
      failed=1
    fi
  }

  check '.required_pull_request_reviews.required_approving_review_count' \
    'required_approving_review_count' '1'
  check '.required_pull_request_reviews.dismiss_stale_reviews' \
    'dismiss_stale_reviews' 'true'
  check '.required_conversation_resolution.enabled' \
    'required_conversation_resolution' 'true'
  check '.enforce_admins.enabled' \
    'enforce_admins' 'true'
  check '.allow_force_pushes.enabled' \
    'allow_force_pushes' 'false'
  check '.allow_deletions.enabled' \
    'allow_deletions' 'false'

  if [ "$failed" -eq 1 ]; then
    echo "ERROR: Branch protection has drifted from expected state."
    exit 1
  fi
  echo "  ✓ All checks passed"
}

case "${1:-}" in
  --verify) verify ;;
  *) apply && verify ;;
esac
