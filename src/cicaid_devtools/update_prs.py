"""CLI tool to bring stale open PRs up to date with their base branch.

Open PRs drift behind their base branch (usually `main`) over time, which
lets CI results go stale and can block merges once branch protection
requires an up-to-date branch. This script lists open PRs, finds the ones
whose head is actually behind their base, and updates their branch via
`gh pr update-branch` (optionally with `--rebase` instead of the default
merge commit).

`gh pr list`'s `mergeStateStatus` only reports "behind" when the base
branch's protection rule requires branches to be up to date before
merging -- on a repo without that rule, a PR dozens of commits behind
`main` reports "clean"/"unstable" instead, which would make this command
a no-op on most repos. So staleness is instead measured directly via
`gh api repos/{owner}/{repo}/compare/{base}...{head}`'s `behind_by` count,
which doesn't depend on branch protection at all. `mergeStateStatus` is
only used to skip PRs with a real conflict ("dirty").

Safety:
  - Defaults to dry-run: prints which PRs would be updated without doing
    anything. Pass --yes to actually update branches.
  - Never touches a PR GitHub reports as "dirty" (a real merge conflict).
  - A PR whose behind-count can't be determined (the compare API call
    failed) is skipped rather than guessed at.

Requires the `gh` CLI to be authenticated with a token that can update
pull request branches on the target repo. Defaults to operating on the
`origin` git remote's repo; pass --repo owner/name to override.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from github_repo import get_repo_info

GH_TIMEOUT_SECONDS = 60


@dataclass
class PullRequest:
    """A single open pull request under consideration."""

    number: int
    title: str
    author: str
    base_ref: str
    head_ref: str
    mergeable_state: str


def run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a single `gh` CLI command. Never raises."""
    cmd = ["gh", *args]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=GH_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            cmd, returncode=124, stdout="", stderr=f"gh {' '.join(args)} timed out"
        )


def fetch_open_prs(owner: str, repo: str) -> list[PullRequest]:
    """List open PRs (author, base/head refs, mergeable state) for the given repo."""
    result = run_gh(
        [
            "pr",
            "list",
            "--repo",
            f"{owner}/{repo}",
            "--state",
            "open",
            "--json",
            "number,title,author,baseRefName,headRefName,mergeStateStatus",
            "--limit",
            "200",
        ]
    )
    if result.returncode != 0:
        logger.error(f"ERROR: gh pr list failed: {result.stderr}")
        raise SystemExit(1)

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error(f"ERROR: gh pr list returned non-JSON output: {exc}")
        raise SystemExit(1) from exc

    prs = []
    for item in data:
        prs.append(
            PullRequest(
                number=item["number"],
                title=item["title"],
                author=(item.get("author") or {}).get("login", ""),
                base_ref=item.get("baseRefName", ""),
                head_ref=item.get("headRefName", ""),
                mergeable_state=(item.get("mergeStateStatus") or "").lower(),
            )
        )
    return prs


def fetch_behind_by(owner: str, repo: str, base_ref: str, head_ref: str) -> int | None:
    """Return how many commits `head_ref` is behind `base_ref`, or None if undetermined."""
    result = run_gh(
        [
            "api",
            f"repos/{owner}/{repo}/compare/{base_ref}...{head_ref}",
            "--jq",
            ".behind_by",
        ]
    )
    if result.returncode != 0:
        logger.warning(
            f"WARNING: could not compare {base_ref}...{head_ref}: {result.stderr.strip()}"
        )
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        logger.warning(f"WARNING: unexpected compare output for {base_ref}...{head_ref}")
        return None


def update_branch(owner: str, repo: str, pr: PullRequest, dry_run: bool, rebase: bool) -> bool:
    """Update a single PR's branch from its base branch via `gh pr update-branch`."""
    prefix = "[DRY RUN] " if dry_run else ""
    logger.info(f"{prefix}PR #{pr.number} ({pr.title}) is behind base -- updating branch")
    if dry_run:
        return True

    args = ["pr", "update-branch", "--repo", f"{owner}/{repo}", str(pr.number)]
    if rebase:
        args += ["--rebase"]
    result = run_gh(args)
    if result.returncode != 0:
        logger.error(f"ERROR: failed to update branch for PR #{pr.number}: {result.stderr.strip()}")
        return False
    logger.info(f"  Updated PR #{pr.number}'s branch")
    return True


def process_pr(owner: str, repo: str, pr: PullRequest, dry_run: bool, rebase: bool) -> bool:
    """Update a single PR's branch if it's behind. Returns False only on a failed update."""
    if pr.mergeable_state == "dirty":
        logger.info(f"SKIP: PR #{pr.number} ({pr.title}) -- has a real merge conflict")
        return True

    behind_by = fetch_behind_by(owner, repo, pr.base_ref, pr.head_ref)
    if behind_by is None:
        logger.info(f"SKIP: PR #{pr.number} ({pr.title}) -- could not determine behind-count")
        return True
    if behind_by == 0:
        logger.info(f"SKIP: PR #{pr.number} ({pr.title}) -- already up to date with {pr.base_ref}")
        return True

    return update_branch(owner, repo, pr, dry_run, rebase)


def resolve_repo(explicit: str | None) -> tuple[str, str]:
    """Resolve the (owner, repo) to operate on: an explicit --repo, else the origin remote."""
    if explicit:
        owner, _, name = explicit.partition("/")
        if not owner or not name:
            logger.error(f"ERROR: --repo must be in 'owner/name' form, got '{explicit}'")
            raise SystemExit(1)
        return owner, name

    try:
        return get_repo_info()
    except ValueError as exc:
        logger.error(f"ERROR: {exc}")
        raise SystemExit(1) from exc


def main() -> int:
    """Run the stale-PR branch-update flow."""
    parser = argparse.ArgumentParser(
        description="Update open PRs that are behind their base branch"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Actually update PR branches. Without this flag, runs in dry-run mode.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Repository to operate on as 'owner/name'. Defaults to the 'origin' git remote.",
    )
    parser.add_argument(
        "--pr",
        type=int,
        default=None,
        help="Only process this single PR number instead of scanning all open PRs.",
    )
    parser.add_argument(
        "--author",
        default=None,
        help="Only process PRs authored by this GitHub login.",
    )
    parser.add_argument(
        "--rebase",
        action="store_true",
        help="Rebase the branch onto the base instead of merging the base in.",
    )
    args = parser.parse_args()
    dry_run = not args.yes

    owner, repo = resolve_repo(args.repo)

    logger.info(f"INFO: Fetching open PRs for {owner}/{repo}...")
    prs = fetch_open_prs(owner, repo)
    if args.pr is not None:
        prs = [pr for pr in prs if pr.number == args.pr]
        if not prs:
            logger.error(f"ERROR: PR #{args.pr} not found among open PRs")
            return 1
    if args.author:
        prs = [pr for pr in prs if pr.author == args.author]
    logger.info(f"INFO: {len(prs)} open PR(s) to check")

    if dry_run:
        logger.info("Running in dry-run mode. Pass --yes to actually update branches.")

    had_failures = False
    for pr in prs:
        if not process_pr(owner, repo, pr, dry_run, args.rebase):
            had_failures = True

    return 1 if had_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
