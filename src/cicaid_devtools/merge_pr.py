"""CLI tool to merge an open GitHub pull request.

Wraps `gh pr merge` so merging a PR doesn't require leaving the terminal for
the GitHub UI. Given a PR number, merges it with the chosen strategy (squash
by default); without one, lists open PRs and prompts for a choice (mirrors
work-on-pr's picker).

Requires the `gh` CLI to be authenticated with a token that can merge PRs
(and delete branches, if --delete-branch is passed) on the target repo.
Defaults to operating on the `origin` git remote's repo; pass --repo
owner/name to override.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from github_repo import get_repo_info  # noqa: E402

GH_TIMEOUT_SECONDS = 60
MERGE_METHODS = {"squash": "--squash", "merge": "--merge", "rebase": "--rebase"}


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


def list_open_prs(owner: str, repo: str) -> list[dict]:
    """List open PRs (number, title, head branch, author) for the given repo."""
    result = run_gh(
        [
            "pr",
            "list",
            "--repo",
            f"{owner}/{repo}",
            "--state",
            "open",
            "--json",
            "number,title,headRefName,author",
            "--limit",
            "200",
        ]
    )
    if result.returncode != 0:
        logger.error(f"ERROR: gh pr list failed: {result.stderr}")
        raise SystemExit(1)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error(f"ERROR: gh pr list returned non-JSON output: {exc}")
        raise SystemExit(1) from exc


def prompt_for_pr(prs: list[dict]) -> dict:
    """List open PRs and prompt the user to pick one."""
    if not prs:
        logger.error("No open pull requests found.")
        raise SystemExit(1)

    logger.info("Open pull requests:")
    for pr in prs:
        author = (pr.get("author") or {}).get("login", "unknown")
        logger.info("  #%d: %s [%s] (by %s)", pr["number"], pr["title"], pr["headRefName"], author)

    try:
        choice = input("\nEnter PR number to merge: ").strip()
    except (EOFError, KeyboardInterrupt):
        logger.error("Aborted.")
        raise SystemExit(1)
    try:
        pr_number = int(choice)
    except ValueError:
        logger.error("Invalid PR number: %r", choice)
        raise SystemExit(1)

    for pr in prs:
        if pr["number"] == pr_number:
            return pr
    logger.error("PR #%d not found among open pull requests.", pr_number)
    raise SystemExit(1)


def merge_pr(
    owner: str,
    repo: str,
    pr_number: int,
    method: str,
    delete_branch: bool,
    admin: bool,
) -> bool:
    """Merge `pr_number` with the given strategy. Returns False on failure."""
    args = [
        "pr",
        "merge",
        str(pr_number),
        "--repo",
        f"{owner}/{repo}",
        MERGE_METHODS[method],
    ]
    if delete_branch:
        args.append("--delete-branch")
    if admin:
        args.append("--admin")
    logger.info("Merging PR #%d (%s, delete-branch=%s)...", pr_number, method, delete_branch)
    result = run_gh(args)
    if result.returncode != 0:
        logger.error("ERROR: failed to merge PR #%d: %s", pr_number, result.stderr.strip())
        return False
    logger.info("[OK] Merged PR #%d", pr_number)
    return True


def main() -> int:
    """Merge a selected open GitHub pull request."""
    parser = argparse.ArgumentParser(description="Merge an open GitHub pull request")
    parser.add_argument(
        "pr_number",
        type=int,
        nargs="?",
        default=None,
        help="GitHub PR number (omit to list open PRs and choose interactively)",
    )
    parser.add_argument(
        "--method",
        choices=sorted(MERGE_METHODS),
        default="squash",
        help="Merge strategy (default: squash)",
    )
    parser.add_argument(
        "--delete-branch",
        action="store_true",
        help="Delete the head branch after merging",
    )
    parser.add_argument(
        "--admin",
        action="store_true",
        help="Bypass branch-protection enforcement for this merge (gh pr merge --admin)",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Repository to operate on as 'owner/name'. Defaults to the 'origin' git remote.",
    )
    args = parser.parse_args()

    if args.repo:
        owner, _, repo = args.repo.partition("/")
        if not owner or not repo:
            logger.error("ERROR: --repo must be in 'owner/name' form, got %r", args.repo)
            return 1
    else:
        try:
            owner, repo = get_repo_info()
        except ValueError as exc:
            logger.error("Error: %s", exc)
            return 1

    if args.pr_number is not None:
        pr_number = args.pr_number
    else:
        prs = list_open_prs(owner, repo)
        pr_number = prompt_for_pr(prs)["number"]

    return 0 if merge_pr(owner, repo, pr_number, args.method, args.delete_branch, args.admin) else 1


if __name__ == "__main__":
    raise SystemExit(main())
