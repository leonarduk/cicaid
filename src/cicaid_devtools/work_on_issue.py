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
from github_repo import get_repo_info, is_wiki_repo  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

ISSUE_REF_PATTERN = re.compile(
    r"\b(closes?|closed|fix(?:es|ed)?|resolves?|resolved)\s*:?\s*#(\d+)",
    re.IGNORECASE,
)


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


def get_main_branch_sha(owner: str, repo: str) -> str:
    """Get the SHA of the branch referenced by the remote's HEAD."""
    remote_prefix = "refs/remotes/origin/"
    result = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    remote_ref = result.stdout.strip()
    if result.returncode != 0 or not remote_ref.startswith(remote_prefix):
        logger.error("Failed to determine the default branch from origin/HEAD")
        sys.exit(1)

    branch_name = remote_ref.removeprefix(remote_prefix)
    result = subprocess.run(
        ["git", "rev-parse", f"refs/remotes/origin/{branch_name}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        logger.error("Failed to get default branch SHA for origin/%s", branch_name)
        sys.exit(1)
    return result.stdout.strip()


def create_branch(owner: str, repo: str, branch_name: str, sha: str, token: str | None = None) -> None:
    """Create a branch in the remote repo.

    First checks whether the branch ref already exists via a GET request.
    Only POSTs to create if the ref is absent (404).
    """
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    # Check if the branch already exists
    ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{branch_name}"
    try:
        resp = requests.get(ref_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            logger.info("Branch %s already exists, skipping creation.", branch_name)
            return
        if resp.status_code != 404:
            logger.warning(
                "Unexpected status %d checking branch ref, will attempt creation.",
                resp.status_code,
            )
    except requests.RequestException as exc:
        logger.warning("Could not check for existing branch (%s); will attempt creation.", exc)

    # Branch does not exist; create it
    url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
    data = {"ref": f"refs/heads/{branch_name}", "sha": sha}
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=10)
        resp.raise_for_status()
    except requests.HTTPError as exc:
        if resp.status_code == 422 and "Reference already exists" in resp.text:
            logger.warning("Branch %s already exists (will proceed with checkout)", branch_name)
        else:
            logger.exception("Failed to create branch: %s", exc)
            sys.exit(1)
    except requests.RequestException as exc:
        logger.exception("Failed to create branch: %s", exc)
        sys.exit(1)


def referenced_issue_ids(text: str) -> set[int]:
    """Return issue numbers referenced by a closing keyword (e.g. ``Closes #155``)."""
    return {int(match.group(2)) for match in ISSUE_REF_PATTERN.finditer(text or "")}


def find_pr_branch_for_issue(
    owner: str, repo: str, issue_id: int, issue_text: str, token: str | None = None
) -> tuple[int, str] | None:
    """Return ``(pr_number, head_branch)`` for an open PR that already resolves this issue.

    Checks PRs that close ``issue_id`` directly, and also PRs that close any
    issue this one references (e.g. a duplicate issue whose body says
    ``Closes #155`` -- the PR closing #155 resolves this issue too). Returns
    None (never raises) if the lookup fails, so a lookup problem just falls
    back to creating a new branch instead of blocking the workflow.
    """
    wanted_ids = {issue_id} | referenced_issue_ids(issue_text)

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    try:
        resp = requests.get(
            url, headers=headers, params={"state": "open", "per_page": 100}, timeout=10
        )
        resp.raise_for_status()
        prs = resp.json()
    except requests.RequestException as exc:
        logger.warning(
            "Could not check for an existing linked PR (%s); creating a new branch.", exc
        )
        return None

    for pr in prs:
        if referenced_issue_ids(pr.get("body") or "") & wanted_ids:
            return pr["number"], pr["head"]["ref"]
    return None


def stash_if_dirty(issue_id: int) -> bool:
    """Stash uncommitted local changes (including untracked files), if any.

    Returns True if a stash entry was created.
    """
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    if not status.stdout.strip():
        return False
    logger.info("Stashing uncommitted local changes...")
    subprocess.run(
        ["git", "stash", "push", "-u", "-m", f"cicaid: auto-stash before issue-{issue_id}"],
        check=True,
    )
    return True


def pop_stash() -> bool:
    """Restore the most recently created stash. Returns True on success."""
    logger.info("Restoring stashed local changes...")
    result = subprocess.run(
        ["git", "stash", "pop"],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if result.returncode != 0:
        logger.error(
            "Could not automatically restore your stashed changes:\n%s\n"
            "Your changes are safe in the stash -- resolve the conflict and run "
            "`git stash pop` manually, or `git stash list` to find them.",
            (result.stdout + result.stderr).strip(),
        )
        return False
    return True


def main(argv: list[str] | None = None) -> None:
    """Create and check out a remote branch for the requested issue.

    ``argv`` defaults to ``sys.argv[1:]`` (the normal CLI entry point); pass
    an explicit list to invoke this programmatically, e.g. from
    ``create_issue.offer_to_start_work``, without touching ``sys.argv``.
    """
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
    args = parser.parse_args(argv)

    token = args.token or os.getenv("GITHUB_TOKEN")

    # Issue lookups always go to the non-wiki repo.
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

    # Wiki repos don't support branches or PRs on GitHub -- work on the
    # default branch and push when done (wikis update immediately).
    try:
        _wiki = is_wiki_repo()
    except ValueError:
        _wiki = False
    if _wiki:
        logger.info(
            "Wiki repo detected -- edit files directly on the default "
            "branch and push when done (wikis update immediately)."
        )
        issue_file = Path(f".issue-{args.issue_id}.md")
        issue_file.write_text(f"{title}\n\n{body}\n", encoding="utf-8")
        logger.info("Wrote issue to %s", issue_file)
        logger.info(
            "\n[OK] Issue #%d loaded. Edit on the default branch and push.",
            args.issue_id,
        )
        return

    # If an open PR already resolves this issue (directly, or via an issue
    # this one duplicates/references), reuse its branch instead of creating
    # a new, redundant one.
    existing = find_pr_branch_for_issue(issue_owner, issue_repo, args.issue_id, f"{title}\n{body}", token)
    if existing:
        pr_number, branch_name = existing
        logger.info(
            "Issue #%d is already resolved by PR #%d -- using its branch: %s",
            args.issue_id, pr_number, branch_name,
        )
    else:
        slug = slugify(title)
        branch_name = f"{args.type}/issue-{args.issue_id}-{slug}"
        logger.info("Branch name: %s", branch_name)

    # Stash any uncommitted local changes so checkout doesn't abort on them.
    stashed = stash_if_dirty(args.issue_id)
    # Set True only once we make the deliberate, final restore attempt below --
    # lets `finally` tell "already handled" apart from "blew up before we got
    # there", without popping the same stash twice.
    reached_restore = False

    try:
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
            subprocess.run(
                ["git", "fetch", "origin", branch_name], check=True, capture_output=True
            )
        elif local_exists:
            logger.info("Branch %s exists locally; pushing to remote", branch_name)
            subprocess.run(["git", "checkout", branch_name], check=True)
            try:
                subprocess.run(["git", "push", "-u", "origin", branch_name], check=True)
            except subprocess.CalledProcessError as exc:
                logger.error("Failed to push branch: %s", exc)
                sys.exit(1)
        else:
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
            try:
                subprocess.run(
                    ["git", "push", "-u", "origin", branch_name],
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                logger.error("Failed to push branch: %s", exc)
                sys.exit(1)

        # Checkout the branch if not already on it
        try:
            current = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, encoding="utf-8", check=True,
            )
            if current.stdout.strip() != branch_name:
                subprocess.run(["git", "checkout", branch_name], check=True)
        except subprocess.CalledProcessError:
            pass

        # Write issue to markdown file
        issue_file = Path(f".issue-{args.issue_id}.md")
        issue_file.write_text(f"{title}\n\n{body}\n", encoding="utf-8")
        logger.info("Wrote issue to %s", issue_file)

        # Restore any stashed local changes last, so a failure earlier in
        # this block doesn't drop a still-recoverable stash before everything
        # else has succeeded.
        reached_restore = True
        if stashed and not pop_stash():
            sys.exit(1)
    finally:
        # Something above failed/exited before the deliberate restore point --
        # get the user's changes back rather than leaving a dangling stash.
        if stashed and not reached_restore:
            logger.warning(
                "Workflow failed before your changes could be restored -- "
                "restoring the stash now..."
            )
            pop_stash()

    logger.info("\n[OK] Ready to work on issue #%d", args.issue_id)


if __name__ == "__main__":
    main()
