"""Tests for cicaid_devtools.lib.publish_pr PR creation (--draft flag)."""

import subprocess
from unittest.mock import patch

from cicaid_devtools.lib import publish_pr


def _completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _capture_gh_pr_create(run_mock):
    """Return the args list of the `gh pr create` subprocess call, if any."""
    for call in run_mock.call_args_list:
        args = call.args[0]
        if list(args[:3]) == ["gh", "pr", "create"]:
            return args
    return None


def test_create_pr_passes_draft_when_flag_set():
    """--draft must be appended to `gh pr create` when draft=True."""
    with patch("cicaid_devtools.lib.publish_pr.subprocess.run") as mock_run:
        mock_run.side_effect = [
            _completed(""),  # find_existing_pr -> gh pr list (no existing PR)
            _completed("https://github.com/owner/repo/pull/42\n"),  # gh pr create
        ]
        url = publish_pr.create_pr(
            "owner", "repo", "fix/issue-1-slug", "main", "Title", "Body", draft=True
        )

    assert url == "https://github.com/owner/repo/pull/42"
    gh_cmd = _capture_gh_pr_create(mock_run)
    assert gh_cmd is not None
    assert "--draft" in gh_cmd
    # --draft is a boolean flag; it must appear once and not take an argument.
    assert gh_cmd.count("--draft") == 1


def test_create_pr_omits_draft_by_default():
    """Without the flag, `gh pr create` must not receive --draft."""
    with patch("cicaid_devtools.lib.publish_pr.subprocess.run") as mock_run:
        mock_run.side_effect = [
            _completed(""),  # find_existing_pr -> gh pr list (no existing PR)
            _completed("https://github.com/owner/repo/pull/42\n"),  # gh pr create
        ]
        url = publish_pr.create_pr("owner", "repo", "fix/issue-1-slug", "main", "Title", "Body")

    assert url == "https://github.com/owner/repo/pull/42"
    gh_cmd = _capture_gh_pr_create(mock_run)
    assert gh_cmd is not None
    assert "--draft" not in gh_cmd


def test_create_pr_draft_still_returns_existing_pr():
    """An existing open (incl. draft) PR is returned instead of creating a new one."""
    with patch("cicaid_devtools.lib.publish_pr.subprocess.run") as mock_run:
        mock_run.return_value = _completed("https://github.com/owner/repo/pull/7\n")
        url = publish_pr.create_pr(
            "owner", "repo", "fix/issue-1-slug", "main", "Title", "Body", draft=True
        )

    assert url == "https://github.com/owner/repo/pull/7"
    # Only the find_existing_pr / gh pr list call should have run; no create.
    assert _capture_gh_pr_create(mock_run) is None


def test_placeholder_body_does_not_leak_issue_headings():
    """Issue bodies with their own markdown headings must not inject nested
    sections into the placeholder PR body (issue #365)."""
    issue_body = (
        "## What\n\n"
        "The gh read helpers run subprocess.run without encoding.\n\n"
        "## Why\n\n"
        "On Windows, text=True decodes with the locale encoding.\n"
    )
    body = publish_pr.create_placeholder_pr_body(360, "Title", issue_body)

    # Exactly one of each standard section, in order -- no duplicates.
    headings = [line for line in body.splitlines() if line.startswith("## ")]
    assert headings == ["## What", "## Why", "## Testing", "## Checklist"]

    # The issue's own heading lines must not appear as nested sections.
    assert body.count("## What") == 1
    assert body.count("## Why") == 1

    # Issue-derived text lands in the Why section, headings stripped.
    assert "The gh read helpers run subprocess.run without encoding" in body
    assert "On Windows, text=True decodes with the locale encoding" in body
    assert "## Why\n\n## What" not in body

    # Closes directive is preserved.
    assert "Closes #360" in body


def test_placeholder_body_falls_back_to_comment_without_issue_body():
    """An empty (or heading-only) issue body still yields a non-empty Why
    section and the Closes directive (issue #365)."""
    for issue_body in ("", "## What\n\n## Why\n\n## How\n"):
        body = publish_pr.create_placeholder_pr_body(1, "Title", issue_body)
        assert "<!-- Explain why this change matters -->" in body
        assert "Closes #1" in body
        headings = [line for line in body.splitlines() if line.startswith("## ")]
        assert headings == ["## What", "## Why", "## Testing", "## Checklist"]
