"""CLI helper to create a GitHub issue checkout branch and file."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from github_repo import get_repo_info  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug.

    Falls back to a deterministic hash when the title has no ASCII
    word characters (e.g. emoji-only titles), so branch names never end up
    with a trailing hyphen like ``fix/issue-4445-``.
    """
    slug = text.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    slug = slug.strip("-")[:50]
    if not slug:
        slug = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    return slug


def fetch_issue(owner: str, repo: str, issue_id: int, token: str | None = None) -> dict:
    """Fetch issue details from GitHub API."""
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_id}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch issue #%d: %s", issue_id, exc)
        sys.exit(1)
    return resp.json()


def main() -> None:
    """Create and check out a remote branch for the requested issue."""
    parser = argparse.ArgumentParser(description="Create a GitHub issue checkout branch")
    parser.add_argument("issue_id", type=int, help="GitHub issue ID")
    parser.add_argument(
        "--token",
        help="GitHub personal access token (for creating branches)",
        default=None,
    )
    parser.add_argument(
        "--type",
        choices=["fix", "feat"],
        default="fix",
        help="Branch prefix to use (default: fix)",
    )
    args = parser.parse_args()

    token = args.token or os.getenv("GITHUB_TOKEN")

    # Issue lookups go to the non-wiki repo (get_repo_info strips .wiki).
    try:
        issue_owner, issue_repo = get_repo_info()
    except ValueError as exc:
        logger.error("Error: %s", exc)
        sys.exit(1)

    logger.info("Issue from: %s/%s", issue_owner, issue_repo)

    # Fetch issue from the main (non-wiki) repo
    logger.info("Fetching issue #%d...", args.issue_id)
    issue = fetch_issue(issue_owner, issue_repo, args.issue_id, token)
    title = issue.get("title", "")
    body = issue.get("body") or ""
    if not title:
        logger.error("Error: Issue #%d has no title", args.issue_id)
        sys.exit(1)

    # Create branch name
    slug = slugify(title)
    branch_name = f"{args.type}/issue-{args.issue_id}-{slug}"
    logger.info("Branch name: %s", branch_name)

    # Wiki repos don't support branches or PRs on GitHub - work on master
    # directly, push when done, and the wiki updates immediately.
    try:
        _current_repo = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, encoding="utf-8", check=True,
        )
        _current_name = _current_repo.stdout.strip().split("/")[-1].replace(".git", "")
    except Exception:
        _current_name = ""

    if _current_name.endswith(".wiki"):
        logger.info(
            "Wiki repo detected - skipping branch creation. Edit files "
            "directly on master and push when done (wikis update immediately)."
        )
        # Write issue to markdown file for reference
        issue_file = Path(f".issue-{args.issue_id}.md")
        content = f"{title}\n\n{body}\n"
        issue_file.write_text(content, encoding="utf-8")
        logger.info("Wrote issue to %s", issue_file)
        logger.info("\n[OK] Issue #%d loaded. Edit files on master and push.", args.issue_id)
        return

    # Ensure we have the latest from origin and are on a stable base
    logger.info("Fetching from origin...")
    try:
        subprocess.run(["git", "fetch", "origin"], check=True)
    except subprocess.CalledProcessError as exc:
        logger.error("Failed to fetch from origin: %s", exc)
        sys.exit(1)

    # Check if branch already exists locally or remotely
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch_name],
            capture_output=True,
            check=False,
        )
        local_exists = result.returncode == 0
    except Exception:
        local_exists = False

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", f"origin/{branch_name}"],
            capture_output=True,
            check=False,
        )
        remote_exists = result.returncode == 0
    except Exception:
        remote_exists = False

    if remote_exists:
        logger.info("Branch %s already exists on remote", branch_name)
        # Fetch the existing branch
        subprocess.run(
            ["git", "fetch", "origin", branch_name], check=True, capture_output=True
        )
    elif local_exists:
        logger.info("Branch %s exists locally; pushing to remote", branch_name)
        subprocess.run(["git", "checkout", branch_name], check=True)
        subprocess.run(["git", "push", "-u", "origin", branch_name], check=True)
    else:
        # Create branch locally from origin/main (or origin/master)
        logger.info("Creating branch...")
        base_ref = None
        for candidate in ("origin/main", "origin/master"):
            try:
                subprocess.run(
                    ["git", "rev-parse", "--verify", candidate],
                    capture_output=True,
                    check=True,
                )
                base_ref = candidate
                break
            except subprocess.CalledProcessError:
                continue

        if base_ref is None:
            logger.error("Could not find origin/main or origin/master")
            sys.exit(1)

        subprocess.run(
            ["git", "checkout", "-b", branch_name, base_ref],
            check=True,
        )
        logger.info("Pushing branch to remote...")
        subprocess.run(
            ["git", "push", "-u", "origin", branch_name],
            check=True,
        )

    # Write issue to markdown file
    issue_file = Path(f".issue-{args.issue_id}.md")
    content = f"{title}\n\n{body}\n"
    issue_file.write_text(content, encoding="utf-8")
    logger.info("Wrote issue to %s", issue_file)
    logger.info("\n[OK] Ready to work on issue #%d", args.issue_id)


if __name__ == "__main__":
    main()
