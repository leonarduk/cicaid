"""CLI helper to update a GitHub issue from a changed local .issue-<id>.md file.

`work-on-issue` writes ``.issue-<id>.md`` from GitHub (first line = issue
title, rest = body), and the local file is the editable spec refined while
working (LLM review fills in ``## How``, ``## Files Affected``, acceptance
criteria). This command pushes those local edits back to GitHub:

    cicaid update-issue 367

reads ``.issue-367.md``, shows the diff against the current GitHub issue, and
(after confirmation) runs ``gh issue edit`` with the new title/body. Only the
title and body are touched -- labels, assignees, state and comments are left
alone. Pass ``--dry-run`` to preview, or ``--yes`` to skip the prompt.
"""

from __future__ import annotations

import argparse
import difflib
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
from github_issues import GitHubIssuesError, get_issue, update_issue  # noqa: E402
from github_repo import get_repo_info  # noqa: E402
from interactive import NON_INTERACTIVE_ENV  # noqa: E402

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def parse_issue_file(file_path: Path) -> tuple[str, str]:
    """Read ``(title, body)`` from a local ``.issue-<id>.md`` file.

    Matches the convention shared with ``implement_issue_with_aider``'s
    ``load_issue_from_file``: the first line is the issue title and everything
    after it is the body.
    """
    content = file_path.read_text(encoding="utf-8")
    lines = content.strip().split("\n", 1)
    title = lines[0].strip()
    body = lines[1].strip() if len(lines) > 1 else ""
    return title, body


def print_changes(current_title: str, current_body: str, title: str, body: str) -> None:
    """Print a human-readable diff of what would change (GitHub -> local)."""
    if current_title != title:
        print(f"Title: {current_title!r} -> {title!r}")
    if current_body != body:
        diff = difflib.unified_diff(
            current_body.splitlines(),
            body.splitlines(),
            fromfile="github",
            tofile="local",
            lineterm="",
        )
        diff = list(diff)
        if diff:
            print("Body diff (GitHub -> local):")
            for line in diff:
                print(line)


def main(argv: list[str] | None = None) -> int:
    """Update a GitHub issue from a changed local ``.issue-<id>.md`` file.

    ``argv`` defaults to ``sys.argv[1:]`` (the normal CLI entry point); pass
    an explicit list to invoke this programmatically, e.g. from tests, without
    touching ``sys.argv`` (mirrors ``work_on_issue.main``).
    """
    parser = argparse.ArgumentParser(
        description="Update a GitHub issue from a changed local .issue-<id>.md file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("issue_id", type=int, help="GitHub issue number to update")
    parser.add_argument(
        "-y", "--yes", action="store_true", help="Skip the confirmation prompt"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without pushing"
    )
    args = parser.parse_args(argv)

    try:
        owner, repo_name = get_repo_info()
    except ValueError as exc:
        logger.error("Error: %s", exc)
        return 1

    repo = f"{owner}/{repo_name}"
    issue_file = Path(f".issue-{args.issue_id}.md")
    if not issue_file.exists():
        logger.error("Issue file not found: %s", issue_file)
        return 1
    try:
        title, body = parse_issue_file(issue_file)
    except OSError as exc:
        logger.error("Failed to read %s: %s", issue_file, exc)
        return 1
    if not title:
        logger.error("%s does not start with an issue title", issue_file)
        return 1

    try:
        current = get_issue(repo, args.issue_id)
    except GitHubIssuesError as exc:
        logger.error("Failed to fetch issue #%d: %s", args.issue_id, exc)
        return 1

    # GitHub bodies keep a trailing newline; the parsed local body is stripped.
    # Treat trailing-whitespace-only differences as already matching, so a no-op
    # push isn't offered for content that renders identically.
    if current.title == title and current.body.rstrip() == body.rstrip():
        logger.info(
            "Issue #%d already matches %s; nothing to update", args.issue_id, issue_file
        )
        return 0

    label = current.url or f"#{args.issue_id}"
    print()
    print(f"Issue: {label} in {repo}")
    print_changes(current.title, current.body, title, body)
    print()

    if args.dry_run:
        logger.info("[DRY RUN] Would update issue #%d in %s", args.issue_id, repo)
        return 0

    if not args.yes:
        if os.environ.get(NON_INTERACTIVE_ENV):
            logger.error(
                "Not running interactively (%s is set); pass --yes to update the issue.",
                NON_INTERACTIVE_ENV,
            )
            return 1
        try:
            confirm = input("Update this issue on GitHub? [Y/n] ").strip().lower()
        except EOFError:
            confirm = "y"
        if confirm and confirm not in ("y", "yes", ""):
            print("Aborted.")
            return 0

    if not update_issue(repo, args.issue_id, title, body):
        return 1
    logger.info("[OK] Updated issue #%d in %s", args.issue_id, repo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
