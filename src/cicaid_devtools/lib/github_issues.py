"""Read and write helpers for GitHub issues and issue comments.

Consolidates duplicate issue-fetching implementations across cicaid and
provides a single, tested code path for reading issues/comments and for
advisory writes (issue creation/editing, comments, labels) via `gh`.

Read helpers raise :class:`GitHubIssuesError` on failure; write helpers are
advisory side effects and instead log `gh`'s stderr and return ``False`` so a
failed write does not abort a caller looping over many issues.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class GitHubIssuesError(Exception):
    """Raised when a GitHub issues read operation fails."""

    pass


@dataclass(frozen=True)
class IssueComment:
    """A single GitHub issue comment."""

    author: str  # login, e.g. "leonarduk"
    body: str
    created_at: str  # ISO 8601 exactly as GitHub returns it, e.g. "2026-08-12T09:28:59Z"


@dataclass(frozen=True)
class Issue:
    """A single GitHub issue."""

    number: int
    title: str
    body: str  # "" when the issue has an empty body (GitHub returns null)
    labels: list[str] = field(default_factory=list)  # label names only, not full label objects
    url: str = ""  # URL to the issue on GitHub (optional, only populated by some call sites)
    state: str = "open"  # "open", "closed", or other state; only set when fetched via list_open_issues
    milestone: str | None = None  # milestone title, or None if unmilestoned


def _gh_api_list(path: str) -> list[dict]:
    """Return all paginated JSON objects for a `gh api` list endpoint.

    Reuses the pagination approach from review_discussion.py: concatenates
    multiple JSON arrays returned by --paginate into a single list.
    """
    result = subprocess.run(
        ["gh", "api", path, "--paginate"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise GitHubIssuesError(f"gh api {path} --paginate failed: {result.stderr.strip()}")

    items: list[dict] = []
    decoder = json.JSONDecoder()
    text = result.stdout
    pos = 0
    try:
        while pos < len(text):
            while pos < len(text) and text[pos].isspace():
                pos += 1
            if pos >= len(text):
                break
            page, end = decoder.raw_decode(text, pos)
            if not isinstance(page, list):
                raise GitHubIssuesError(
                    f"gh api {path} returned a non-list JSON value: {type(page).__name__}"
                )
            items.extend(page)
            pos = end
    except json.JSONDecodeError as exc:
        raise GitHubIssuesError(f"gh api returned non-JSON output: {exc}")
    return items


def list_open_issues(
    repo: str, label: str | None = None, limit: int = 200, state: str = "open"
) -> list[Issue]:
    """List issues in a repository.

    Args:
        repo: Repository in "owner/name" format.
        label: Optional label to filter by.
        limit: Maximum number of issues to return (default 200).
        state: Issue state: "open", "closed", or "all" (default "open").

    Returns:
        List of Issue objects, sorted by number ascending.

    Raises:
        GitHubIssuesError: If the gh command fails.
    """
    args: list[str] = [
        "gh",
        "issue",
        "list",
        "--state",
        state,
        "--json",
        "number,title,body,labels,url,state,milestone",
        "--limit",
        str(limit),
        "--repo",
        repo,
    ]
    if label:
        args += ["--label", label]

    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise GitHubIssuesError(f"gh issue list failed: {result.stderr.strip()}")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GitHubIssuesError(f"gh issue list returned non-JSON output: {exc}")

    return [
        Issue(
            number=item["number"],
            title=item.get("title", ""),
            body=item.get("body") or "",
            labels=[label_obj["name"] for label_obj in item.get("labels", [])],
            url=item.get("url", ""),
            state=item.get("state", state).lower(),
            milestone=(item.get("milestone") or {}).get("title"),
        )
        for item in data
    ]


def get_issue(repo: str, number: int) -> Issue:
    """Get a single issue by number.

    Args:
        repo: Repository in "owner/name" format.
        number: Issue number.

    Returns:
        The Issue object.

    Raises:
        GitHubIssuesError: If the gh command fails.
    """
    result = subprocess.run(
        [
            "gh",
            "issue",
            "view",
            str(number),
            "--json",
            "number,title,body,labels,url,state,milestone",
            "--repo",
            repo,
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise GitHubIssuesError(f"gh issue view #{number} failed: {result.stderr.strip()}")

    try:
        item = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GitHubIssuesError(f"gh issue view returned non-JSON output: {exc}")

    return Issue(
        number=item["number"],
        title=item.get("title", ""),
        body=item.get("body") or "",
        labels=[label_obj["name"] for label_obj in item.get("labels", [])],
        url=item.get("url", ""),
        state=item.get("state", "open").lower(),
        milestone=(item.get("milestone") or {}).get("title"),
    )


def _run_gh(args: list[str], action: str) -> bool:
    """Run a `gh` write command, logging failures instead of raising.

    Args:
        args: Full `gh` argv, body text passed as an argument (never shell-
            interpolated) so newlines, backticks and HTML comments survive.
        action: Human-readable description for logs, e.g. "post comment on issue #3".

    Returns:
        True on success; False after logging `gh`'s stderr otherwise.
    """
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        logger.error("Failed to %s: %s", action, result.stderr.strip())
        return False
    logger.info("OK: %s", action)
    return True


def post_issue_comment(repo: str, number: int, body: str, dry_run: bool = False) -> bool:
    """Post a comment on an issue.

    Args:
        repo: Repository in "owner/name" format.
        number: Issue number.
        body: Full comment body, passed to `gh` as an argument.
        dry_run: Log what would be sent and return True without invoking `gh`.

    Returns:
        True on success (including dry runs); False after logging `gh`'s stderr.
    """
    if dry_run:
        logger.info(
            "[DRY RUN] Would post this comment on issue #%s in %s:\n%s",
            number,
            repo,
            body,
        )
        return True
    return _run_gh(
        ["gh", "issue", "comment", str(number), "--repo", repo, "--body", body],
        f"post comment on issue #{number}",
    )


def add_issue_labels(
    repo: str, number: int, labels: list[str], dry_run: bool = False
) -> bool:
    """Add labels to an issue.

    Labels must already exist in the repository; `gh` resolves names to IDs and
    fails on unknown ones. An empty label list is a no-op returning True.

    Args:
        repo: Repository in "owner/name" format.
        number: Issue number.
        labels: Label names to add, one `--add-label` flag each (gh's flag is
            comma-splitting, so a label containing a comma cannot be passed
            this way).
        dry_run: Log what would be sent and return True without invoking `gh`.

    Returns:
        True on success (including dry runs and empty label lists);
        False after logging `gh`'s stderr.
    """
    if not labels:
        return True
    if dry_run:
        logger.info(
            "[DRY RUN] Would add labels %s to issue #%s in %s", labels, number, repo
        )
        return True
    args: list[str] = ["gh", "issue", "edit", str(number), "--repo", repo]
    for label in labels:
        args += ["--add-label", label]
    return _run_gh(args, f"add labels to issue #{number}")


def remove_issue_label(
    repo: str, number: int, label: str, dry_run: bool = False
) -> bool:
    """Remove a label from an issue, idempotently.

    `gh issue edit --remove-label` is *not* idempotent: it resolves the label
    to an ID and uses the GraphQL ``removeLabelsFromLabelable`` mutation, which
    errors when the label is not currently on the issue. Callers remove labels
    unconditionally, so membership is checked first via :func:`get_issue` and
    an absent label is success without invoking `gh`. Matching is
    case-insensitive, mirroring `gh`'s own label matching.

    Args:
        repo: Repository in "owner/name" format.
        number: Issue number.
        label: Label name to remove.
        dry_run: Log what would be sent and return True without invoking `gh`.

    Returns:
        True on success (including dry runs and already-absent labels);
        False after logging the failure.
    """
    if dry_run:
        logger.info(
            "[DRY RUN] Would remove label %r from issue #%s in %s", label, number, repo
        )
        return True
    try:
        issue = get_issue(repo, number)
    except GitHubIssuesError:
        logger.error("Failed to remove label %r from issue #%s: could not read it", label, number)
        return False
    if not any(existing.lower() == label.lower() for existing in issue.labels):
        logger.info("Label %r is not on issue #%s; nothing to remove", label, number)
        return True
    return _run_gh(
        ["gh", "issue", "edit", str(number), "--repo", repo, "--remove-label", label],
        f"remove label {label!r} from issue #{number}",
    )


def create_issue(repo: str, title: str, body: str = "") -> str | None:
    """Create a new GitHub issue.

    Runs ``gh issue create --repo <repo> --title <title> [--body <body>]``
    with the title and body passed as arguments (never shell-interpolated), so
    newlines, backticks and Markdown survive. The body flag is omitted when
    the body is empty.

    Args:
        repo: Repository in "owner/name" format.
        title: Issue title.
        body: Optional issue body.

    Returns:
        The created issue's URL, which `gh` prints on stdout, or None after
        logging `gh`'s stderr on failure (the same advisory contract as
        :func:`post_issue_comment` / :func:`add_issue_labels`).
    """
    args: list[str] = ["gh", "issue", "create", "--repo", repo, "--title", title]
    if body:
        args += ["--body", body]
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        logger.error("Failed to create issue in %s: %s", repo, result.stderr.strip())
        return None
    url = result.stdout.strip()
    logger.info("OK: created issue %s in %s", url, repo)
    return url


def update_issue(
    repo: str, number: int, title: str, body: str = "", dry_run: bool = False
) -> bool:
    """Update an issue's title and/or body via ``gh issue edit``.

    Only the title and body are changed -- labels, assignees, milestone, state
    and comments are left untouched. The title and body are passed as arguments
    (never shell-interpolated), so newlines, backticks and Markdown survive. The
    ``--body`` flag is omitted when the body is empty, so an empty body leaves
    the existing body alone rather than clearing it.

    Args:
        repo: Repository in "owner/name" format.
        number: Issue number.
        title: New issue title.
        body: New issue body.
        dry_run: Log what would be sent and return True without invoking `gh`.

    Returns:
        True on success (including dry runs); False after logging `gh`'s stderr.
    """
    if dry_run:
        logger.info(
            "[DRY RUN] Would update issue #%s in %s:\nTitle: %s\nBody:\n%s",
            number,
            repo,
            title,
            body,
        )
        return True
    args: list[str] = ["gh", "issue", "edit", str(number), "--repo", repo, "--title", title]
    if body:
        args += ["--body", body]
    return _run_gh(args, f"update issue #{number} in {repo}")


def get_issue_comments(repo: str, number: int) -> list[IssueComment]:
    """Get all comments on an issue, in ascending created_at order.

    GitHub's API already returns comments in ascending created_at order, but
    this is explicitly (re-)sorted rather than trusted, so callers can rely on
    the last element being the most recent even if that default ever changes.

    Args:
        repo: Repository in "owner/name" format.
        number: Issue number.

    Returns:
        List of IssueComment objects, sorted by creation time (oldest first).

    Raises:
        GitHubIssuesError: If the gh command fails.
    """
    path = f"repos/{repo}/issues/{number}/comments"
    items = _gh_api_list(path)

    comments = [
        IssueComment(
            author=(item.get("user") or {}).get("login", "unknown"),
            body=item.get("body", ""),
            created_at=item.get("created_at", ""),
        )
        for item in items
    ]
    comments.sort(key=lambda c: c.created_at)
    return comments
