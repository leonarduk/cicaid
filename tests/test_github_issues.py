"""Tests for cicaid_devtools.lib.github_issues."""

import json
import locale
import subprocess
from unittest.mock import patch

import pytest

from cicaid_devtools.lib.github_issues import (
    GitHubIssuesError,
    Issue,
    IssueComment,
    add_issue_labels,
    create_issue,
    get_issue,
    get_issue_comments,
    list_open_issues,
    post_issue_comment,
    remove_issue_label,
    update_issue,
)


# ------------------------------------------------------------------- fixtures


@pytest.fixture
def mock_subprocess():
    """Patch subprocess.run for all tests in this module."""
    with patch("cicaid_devtools.lib.github_issues.subprocess.run") as mock:
        yield mock


# ------------------------------------------------------------------- list_open_issues


def test_list_open_issues_invokes_gh_executable(mock_subprocess):
    """Regression test: list_open_issues must invoke the `gh` executable.

    A prior version built args=["issue", "list", ...] and passed it straight
    to subprocess.run without prepending "gh", which would raise
    FileNotFoundError against a real subprocess (there is no "issue"
    executable). Every mocked test here would have passed anyway, so this
    explicitly asserts the first argument.
    """
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "list"],
        returncode=0,
        stdout=json.dumps([]),
        stderr="",
    )

    list_open_issues("owner/repo")

    call_args = mock_subprocess.call_args[0][0]
    assert call_args[0] == "gh"
    assert call_args[1:3] == ["issue", "list"]


def test_list_open_issues_basic(mock_subprocess):
    """Test list_open_issues with a basic response."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "list"],
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "number": 1,
                    "title": "First issue",
                    "body": "This is the body",
                    "labels": [{"name": "bug"}, {"name": "urgent"}],
                },
                {
                    "number": 2,
                    "title": "Second issue",
                    "body": None,
                    "labels": [],
                },
            ]
        ),
        stderr="",
    )

    result = list_open_issues("owner/repo")

    assert len(result) == 2
    assert result[0] == Issue(
        number=1,
        title="First issue",
        body="This is the body",
        labels=["bug", "urgent"],
    )
    assert result[1] == Issue(
        number=2,
        title="Second issue",
        body="",  # null body coerced to ""
        labels=[],
    )


def test_list_open_issues_with_label(mock_subprocess):
    """Test list_open_issues with label filter."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "list"],
        returncode=0,
        stdout=json.dumps([]),
        stderr="",
    )

    list_open_issues("owner/repo", label="enhancement")

    # Verify the gh command was called with --label
    call_args = mock_subprocess.call_args
    assert "--label" in call_args[0][0]
    assert "enhancement" in call_args[0][0]


def test_list_open_issues_with_custom_limit(mock_subprocess):
    """Test list_open_issues with custom limit."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "list"],
        returncode=0,
        stdout=json.dumps([]),
        stderr="",
    )

    list_open_issues("owner/repo", limit=500)

    # Verify the gh command was called with --limit 500
    call_args = mock_subprocess.call_args
    assert "--limit" in call_args[0][0]
    assert "500" in call_args[0][0]


def test_list_open_issues_with_closed_state(mock_subprocess):
    """Test list_open_issues with state='closed' fetches closed issues."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "list"],
        returncode=0,
        stdout=json.dumps(
            [{"number": 5, "title": "Closed one", "body": "done", "labels": [], "state": "closed"}]
        ),
        stderr="",
    )

    result = list_open_issues("owner/repo", state="closed")

    call_args = mock_subprocess.call_args[0][0]
    assert "--state" in call_args
    assert call_args[call_args.index("--state") + 1] == "closed"
    assert result[0].state == "closed"


def test_list_open_issues_empty_body_coerced_to_empty_string(mock_subprocess):
    """Test that null bodies are coerced to empty strings."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "list"],
        returncode=0,
        stdout=json.dumps([{"number": 1, "title": "No body", "body": None, "labels": []}]),
        stderr="",
    )

    result = list_open_issues("owner/repo")

    assert result[0].body == ""


def test_list_open_issues_gh_error(mock_subprocess):
    """Test that gh errors raise GitHubIssuesError."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "list"],
        returncode=1,
        stdout="",
        stderr="gh: not authenticated",
    )

    with pytest.raises(GitHubIssuesError, match="gh issue list failed"):
        list_open_issues("owner/repo")


def test_list_open_issues_invalid_json(mock_subprocess):
    """Test that invalid JSON raises GitHubIssuesError."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "list"],
        returncode=0,
        stdout="not json",
        stderr="",
    )

    with pytest.raises(GitHubIssuesError, match="non-JSON output"):
        list_open_issues("owner/repo")


# ------------------------------------------------------------------- get_issue


def test_get_issue_basic(mock_subprocess):
    """Test get_issue with a basic response."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "view"],
        returncode=0,
        stdout=json.dumps(
            {
                "number": 42,
                "title": "The answer",
                "body": "The answer to everything",
                "labels": [{"name": "feature"}, {"name": "discussion"}],
            }
        ),
        stderr="",
    )

    result = get_issue("owner/repo", 42)

    assert result == Issue(
        number=42,
        title="The answer",
        body="The answer to everything",
        labels=["feature", "discussion"],
    )


def test_get_issue_populates_url_and_state(mock_subprocess):
    """Test get_issue requests and populates url and state, not just the defaults."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "view"],
        returncode=0,
        stdout=json.dumps(
            {
                "number": 7,
                "title": "Closed one",
                "body": "done",
                "labels": [],
                "url": "https://github.com/owner/repo/issues/7",
                "state": "CLOSED",
            }
        ),
        stderr="",
    )

    result = get_issue("owner/repo", 7)

    assert result.url == "https://github.com/owner/repo/issues/7"
    assert result.state == "closed"
    # The --json fields requested must include url and state, or gh would
    # never return them in the first place.
    call_args = mock_subprocess.call_args[0][0]
    json_fields = call_args[call_args.index("--json") + 1]
    assert "url" in json_fields
    assert "state" in json_fields


def test_get_issue_null_body(mock_subprocess):
    """Test get_issue handles null body."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "view"],
        returncode=0,
        stdout=json.dumps(
            {
                "number": 1,
                "title": "No body here",
                "body": None,
                "labels": [],
            }
        ),
        stderr="",
    )

    result = get_issue("owner/repo", 1)

    assert result.body == ""


def test_get_issue_no_labels(mock_subprocess):
    """Test get_issue with issue that has no labels."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "view"],
        returncode=0,
        stdout=json.dumps(
            {
                "number": 1,
                "title": "Unlabeled",
                "body": "No labels",
                "labels": [],
            }
        ),
        stderr="",
    )

    result = get_issue("owner/repo", 1)

    assert result.labels == []


def test_get_issue_gh_error(mock_subprocess):
    """Test that gh errors raise GitHubIssuesError."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "view"],
        returncode=1,
        stdout="",
        stderr="HTTP 404: Not Found (repository not found)",
    )

    with pytest.raises(GitHubIssuesError, match="gh issue view #1 failed"):
        get_issue("owner/repo", 1)


def test_get_issue_invalid_json(mock_subprocess):
    """Test that invalid JSON raises GitHubIssuesError."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "issue", "view"],
        returncode=0,
        stdout="garbage",
        stderr="",
    )

    with pytest.raises(GitHubIssuesError, match="non-JSON output"):
        get_issue("owner/repo", 1)


# ------------------------------------------------------------------- get_issue_comments


def test_get_issue_comments_basic(mock_subprocess):
    """Test get_issue_comments with basic comments."""
    # Mock the subprocess for _gh_api_list call
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "api"],
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "user": {"login": "alice"},
                    "body": "First comment",
                    "created_at": "2026-08-12T10:00:00Z",
                },
                {
                    "user": {"login": "bob"},
                    "body": "Second comment",
                    "created_at": "2026-08-12T10:01:00Z",
                },
            ]
        ),
        stderr="",
    )

    result = get_issue_comments("owner/repo", 1)

    assert len(result) == 2
    assert result[0] == IssueComment(
        author="alice",
        body="First comment",
        created_at="2026-08-12T10:00:00Z",
    )
    assert result[1] == IssueComment(
        author="bob",
        body="Second comment",
        created_at="2026-08-12T10:01:00Z",
    )


def test_get_issue_comments_sorts_out_of_order_input(mock_subprocess):
    """Test that comments are sorted by created_at even if gh returns them out of order."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "api"],
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "user": {"login": "newest"},
                    "body": "Newest comment",
                    "created_at": "2026-08-03T10:00:00Z",
                },
                {
                    "user": {"login": "oldest"},
                    "body": "Oldest comment",
                    "created_at": "2026-08-01T10:00:00Z",
                },
                {
                    "user": {"login": "middle"},
                    "body": "Middle comment",
                    "created_at": "2026-08-02T10:00:00Z",
                },
            ]
        ),
        stderr="",
    )

    result = get_issue_comments("owner/repo", 1)

    assert [c.author for c in result] == ["oldest", "middle", "newest"]
    assert result[-1].author == "newest"


def test_get_issue_comments_preserves_order(mock_subprocess):
    """Test that comments are returned in ascending created_at order."""
    # GitHub's API returns comments in ascending order by default,
    # and callers depend on the last element being the most recent.
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "api"],
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "user": {"login": "author1"},
                    "body": "Comment 1",
                    "created_at": "2026-08-01T10:00:00Z",
                },
                {
                    "user": {"login": "author2"},
                    "body": "Comment 2",
                    "created_at": "2026-08-02T10:00:00Z",
                },
                {
                    "user": {"login": "author3"},
                    "body": "Comment 3 (most recent)",
                    "created_at": "2026-08-03T10:00:00Z",
                },
            ]
        ),
        stderr="",
    )

    result = get_issue_comments("owner/repo", 1)

    # Last element should be the most recent
    assert result[-1].author == "author3"
    assert result[-1].body == "Comment 3 (most recent)"


def test_get_issue_comments_empty(mock_subprocess):
    """Test get_issue_comments with no comments."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "api"],
        returncode=0,
        stdout=json.dumps([]),
        stderr="",
    )

    result = get_issue_comments("owner/repo", 1)

    assert result == []


def test_get_issue_comments_missing_author(mock_subprocess):
    """Test get_issue_comments handles missing author gracefully."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "api"],
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "user": None,
                    "body": "Comment with no author",
                    "created_at": "2026-08-12T10:00:00Z",
                },
            ]
        ),
        stderr="",
    )

    result = get_issue_comments("owner/repo", 1)

    assert result[0].author == "unknown"


def test_get_issue_comments_paginated_output(mock_subprocess):
    """Test get_issue_comments handles --paginate with multiple JSON arrays."""
    # When --paginate returns multiple JSON arrays, _gh_api_list concatenates them
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "api"],
        returncode=0,
        stdout='[{"user":{"login":"alice"},"body":"Page 1","created_at":"2026-08-12T10:00:00Z"}]\n[{"user":{"login":"bob"},"body":"Page 2","created_at":"2026-08-12T10:01:00Z"}]',
        stderr="",
    )

    result = get_issue_comments("owner/repo", 1)

    assert len(result) == 2
    assert result[0].author == "alice"
    assert result[1].author == "bob"


def test_get_issue_comments_gh_error(mock_subprocess):
    """Test that gh errors raise GitHubIssuesError."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "api"],
        returncode=1,
        stdout="",
        stderr="gh: not authenticated",
    )

    with pytest.raises(GitHubIssuesError, match="gh api .* failed"):
        get_issue_comments("owner/repo", 1)


def test_get_issue_comments_invalid_json(mock_subprocess):
    """Test that invalid JSON in paginated output raises GitHubIssuesError."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "api"],
        returncode=0,
        stdout="not json at all",
        stderr="",
    )

    with pytest.raises(GitHubIssuesError):
        get_issue_comments("owner/repo", 1)


def test_get_issue_comments_non_list_json_raises(mock_subprocess):
    """Test that a paginated page decoding to a non-list JSON value raises cleanly."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=["gh", "api"],
        returncode=0,
        stdout=json.dumps({"message": "Not Found"}),
        stderr="",
    )

    with pytest.raises(GitHubIssuesError, match="non-list JSON value"):
        get_issue_comments("owner/repo", 1)


# ------------------------------------------------------------------- issue #360: UTF-8 decoding


def test_read_helpers_pass_encoding_utf8(mock_subprocess):
    """Regression test for #360: gh read helpers must request UTF-8 decoding.

    On Windows, ``text=True`` without ``encoding=`` decodes child output with
    the locale encoding (cp1252), but ``gh`` always emits UTF-8. Non-ASCII
    issue content then kills the reader thread with UnicodeDecodeError and
    leaves ``result.stdout`` None, crashing ``json.loads``. While
    ``subprocess.run`` is patched, the ``encoding`` kwarg is the observable
    contract that keeps the decode path deterministic on every platform.
    """
    cases = [
        (
            list_open_issues,
            ("owner/repo",),
            json.dumps([{"number": 1, "title": "t", "body": "b", "labels": []}]),
        ),
        (
            get_issue,
            ("owner/repo", 1),
            json.dumps({"number": 1, "title": "t", "body": "b", "labels": []}),
        ),
        (get_issue_comments, ("owner/repo", 1), json.dumps([])),
    ]
    for helper, args, payload in cases:
        mock_subprocess.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=payload, stderr=""
        )
        helper(*args)
        assert mock_subprocess.call_args.kwargs["encoding"] == "utf-8", (
            f"{helper.__name__} must decode gh output as UTF-8"
        )


def test_get_issue_decodes_multibyte_utf8_output(mock_subprocess):
    """Regression test for #360: multi-byte UTF-8 gh output decodes cleanly.

    Mirrors ``subprocess.run(text=True)`` decoding semantics: captured bytes
    are decoded with the ``encoding`` kwarg when provided, otherwise with the
    locale encoding. Before the fix no encoding was passed, so on a cp1252
    Windows locale this reproduced the reported UnicodeDecodeError followed by
    the json.loads(None) crash.
    """
    payload = json.dumps(
        {"number": 1, "title": "Café — naïve résumé", "body": "naïve", "labels": []}
    ).encode("utf-8")

    def decode_like_subprocess(args, **kwargs):
        encoding = kwargs.get("encoding") or locale.getpreferredencoding(False)
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=payload.decode(encoding), stderr=""
        )

    mock_subprocess.side_effect = decode_like_subprocess
    issue = get_issue("owner/repo", 1)
    assert issue.title == "Café — naïve résumé"


# ------------------------------------------------------------------- post_issue_comment


def test_post_issue_comment_success(mock_subprocess):
    """Test post_issue_comment invokes gh with the body as an argument."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )
    body = "## Plan\n```python\nx = 1\n```\n<!-- note -->"

    assert post_issue_comment("owner/repo", 42, body) is True

    call_args = mock_subprocess.call_args[0][0]
    assert call_args == [
        "gh",
        "issue",
        "comment",
        "42",
        "--repo",
        "owner/repo",
        "--body",
        body,
    ]


def test_post_issue_comment_dry_run_logs_body_without_subprocess(mock_subprocess, caplog):
    """Test dry_run logs the full body and provably invokes no subprocess."""
    caplog.set_level("INFO", logger="cicaid_devtools.lib.github_issues")

    assert post_issue_comment("owner/repo", 42, "the plan", dry_run=True) is True

    mock_subprocess.assert_not_called()
    assert "the plan" in caplog.text


def test_post_issue_comment_failure_logs_stderr(mock_subprocess, caplog):
    """Test a non-zero gh exit returns False and logs stderr."""
    caplog.set_level("ERROR", logger="cicaid_devtools.lib.github_issues")
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="gh: not authenticated"
    )

    assert post_issue_comment("owner/repo", 42, "body") is False
    assert "gh: not authenticated" in caplog.text


# ------------------------------------------------------------------- add_issue_labels


def test_add_issue_labels_success(mock_subprocess):
    """Test add_issue_labels passes one --add-label flag per label."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    assert add_issue_labels("owner/repo", 7, ["Ready", "needs-info"]) is True

    call_args = mock_subprocess.call_args[0][0]
    assert call_args == [
        "gh",
        "issue",
        "edit",
        "7",
        "--repo",
        "owner/repo",
        "--add-label",
        "Ready",
        "--add-label",
        "needs-info",
    ]


def test_add_issue_labels_empty_list_is_noop(mock_subprocess):
    """Test add_issue_labels([]) returns True without invoking gh."""
    assert add_issue_labels("owner/repo", 7, []) is True
    mock_subprocess.assert_not_called()


def test_add_issue_labels_dry_run_no_subprocess(mock_subprocess):
    """Test dry_run invokes no subprocess."""
    assert add_issue_labels("owner/repo", 7, ["Ready"], dry_run=True) is True
    mock_subprocess.assert_not_called()


def test_add_issue_labels_failure_logs_stderr(mock_subprocess, caplog):
    """Test a non-zero gh exit returns False and logs stderr."""
    caplog.set_level("ERROR", logger="cicaid_devtools.lib.github_issues")
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="could not add label: 'Nope' not found"
    )

    assert add_issue_labels("owner/repo", 7, ["Nope"]) is False
    assert "could not add label: 'Nope' not found" in caplog.text


# ------------------------------------------------------------------- remove_issue_label


def test_remove_issue_label_success(mock_subprocess):
    """Test removing a present label runs gh issue edit."""
    mock_subprocess.side_effect = [
        subprocess.CompletedProcess(  # get_issue read
            args=[],
            returncode=0,
            stdout=json.dumps(
                {"number": 7, "title": "t", "body": "b", "labels": [{"name": "Ready"}]}
            ),
            stderr="",
        ),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ]

    assert remove_issue_label("owner/repo", 7, "Ready") is True

    edit_args = mock_subprocess.call_args_list[1][0][0]
    assert edit_args == [
        "gh",
        "issue",
        "edit",
        "7",
        "--repo",
        "owner/repo",
        "--remove-label",
        "Ready",
    ]


def test_remove_issue_label_absent_label_is_success_without_edit(mock_subprocess):
    """Test removing an absent label returns True without running gh issue edit."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps(
            {"number": 7, "title": "t", "body": "b", "labels": [{"name": "Ready"}]}
        ),
        stderr="",
    )

    assert remove_issue_label("owner/repo", 7, "needs-info") is True

    # Only the get_issue read ran; no edit subprocess was invoked.
    assert mock_subprocess.call_count == 1
    read_args = mock_subprocess.call_args[0][0]
    assert read_args[:3] == ["gh", "issue", "view"]


def test_remove_issue_label_matches_case_insensitively(mock_subprocess):
    """Test removal matches gh's case-insensitive label matching."""
    mock_subprocess.side_effect = [
        subprocess.CompletedProcess(  # get_issue read
            args=[],
            returncode=0,
            stdout=json.dumps(
                {"number": 7, "title": "t", "body": "b", "labels": [{"name": "Ready"}]}
            ),
            stderr="",
        ),
        subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
    ]

    assert remove_issue_label("owner/repo", 7, "ready") is True
    assert mock_subprocess.call_count == 2


def test_remove_issue_label_dry_run_no_subprocess(mock_subprocess):
    """Test dry_run invokes no subprocess at all."""
    assert remove_issue_label("owner/repo", 7, "Ready", dry_run=True) is True
    mock_subprocess.assert_not_called()


def test_remove_issue_label_read_failure_returns_false(mock_subprocess, caplog):
    """Test a failed get_issue read makes removal return False, not raise."""
    caplog.set_level("ERROR", logger="cicaid_devtools.lib.github_issues")
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="gh: not authenticated"
    )

    assert remove_issue_label("owner/repo", 7, "Ready") is False
    assert "could not read it" in caplog.text


def test_remove_issue_label_edit_failure_logs_stderr(mock_subprocess, caplog):
    """Test a non-zero gh issue edit exit returns False and logs stderr."""
    caplog.set_level("ERROR", logger="cicaid_devtools.lib.github_issues")
    mock_subprocess.side_effect = [
        subprocess.CompletedProcess(  # get_issue read
            args=[],
            returncode=0,
            stdout=json.dumps(
                {"number": 7, "title": "t", "body": "b", "labels": [{"name": "Ready"}]}
            ),
            stderr="",
        ),
        subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="graphql: something failed"
        ),
    ]

    assert remove_issue_label("owner/repo", 7, "Ready") is False
    assert "graphql: something failed" in caplog.text


# ------------------------------------------------------------------- create_issue


def test_create_issue_success(mock_subprocess):
    """Test create_issue invokes gh issue create and returns the printed URL."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="https://github.com/owner/repo/issues/42\n",
        stderr="",
    )

    assert create_issue("owner/repo", "New issue title") == (
        "https://github.com/owner/repo/issues/42"
    )

    call_args = mock_subprocess.call_args[0][0]
    assert call_args == [
        "gh",
        "issue",
        "create",
        "--repo",
        "owner/repo",
        "--title",
        "New issue title",
    ]


def test_create_issue_with_body_passes_body_as_argument(mock_subprocess):
    """Test the body is passed as a --body argument, never shell-interpolated."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="https://github.com/owner/repo/issues/43\n",
        stderr="",
    )
    body = "## Plan\n```python\nx = 1\n```\n<!-- note -->"

    assert create_issue("owner/repo", "Title", body=body) == (
        "https://github.com/owner/repo/issues/43"
    )

    call_args = mock_subprocess.call_args[0][0]
    assert call_args == [
        "gh",
        "issue",
        "create",
        "--repo",
        "owner/repo",
        "--title",
        "Title",
        "--body",
        body,
    ]


def test_create_issue_empty_body_omits_body_flag(mock_subprocess):
    """Test an empty body omits --body rather than passing an empty argument."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="https://github.com/owner/repo/issues/44\n", stderr=""
    )

    create_issue("owner/repo", "Title", body="")

    call_args = mock_subprocess.call_args[0][0]
    assert "--body" not in call_args


def test_create_issue_failure_logs_stderr(mock_subprocess, caplog):
    """Test a non-zero gh exit returns None and logs stderr."""
    caplog.set_level("ERROR", logger="cicaid_devtools.lib.github_issues")
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="gh: not authenticated"
    )

    assert create_issue("owner/repo", "Title") is None
    assert "gh: not authenticated" in caplog.text


# ------------------------------------------------------------------- update_issue


def test_update_issue_invokes_gh_issue_edit(mock_subprocess):
    """Test update_issue runs gh issue edit with title and body as arguments."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    assert update_issue("owner/repo", 7, "New title", "New body") is True

    call_args = mock_subprocess.call_args[0][0]
    assert call_args == [
        "gh",
        "issue",
        "edit",
        "7",
        "--repo",
        "owner/repo",
        "--title",
        "New title",
        "--body",
        "New body",
    ]


def test_update_issue_body_with_newlines_survives_as_argument(mock_subprocess):
    """Test a multi-line markdown body is passed as one argv element, never
    shell-interpolated."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )
    body = "## Plan\n```python\nx = 1\n```\n<!-- note -->"

    assert update_issue("owner/repo", 7, "Title", body=body) is True

    call_args = mock_subprocess.call_args[0][0]
    assert call_args[-2:] == ["--body", body]


def test_update_issue_empty_body_omits_body_flag(mock_subprocess):
    """Test an empty body omits --body rather than clearing the existing body."""
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    assert update_issue("owner/repo", 7, "New title", body="") is True

    call_args = mock_subprocess.call_args[0][0]
    assert "--body" not in call_args
    assert call_args[-2:] == ["--title", "New title"]


def test_update_issue_failure_logs_stderr(mock_subprocess, caplog):
    """Test a non-zero gh exit returns False and logs stderr."""
    caplog.set_level("ERROR", logger="cicaid_devtools.lib.github_issues")
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="gh: not authenticated"
    )

    assert update_issue("owner/repo", 7, "Title", "Body") is False
    assert "gh: not authenticated" in caplog.text


def test_update_issue_dry_run_skips_gh(mock_subprocess, caplog):
    """Test dry_run logs the intended update without invoking gh."""
    caplog.set_level("INFO", logger="cicaid_devtools.lib.github_issues")
    mock_subprocess.return_value = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="", stderr=""
    )

    assert update_issue("owner/repo", 7, "Title", "Body", dry_run=True) is True
    mock_subprocess.assert_not_called()
    assert "[DRY RUN] Would update issue #7" in caplog.text


# ------------------------------------------------------------------- GitHub errors


def test_github_issues_error_is_exception():
    """Test that GitHubIssuesError is an Exception."""
    err = GitHubIssuesError("test message")
    assert isinstance(err, Exception)
    assert str(err) == "test message"


# ------------------------------------------------------------------- dataclass properties


def test_issue_is_frozen():
    """Test that Issue is immutable."""
    issue = Issue(number=1, title="Test", body="Body", labels=["bug"])
    with pytest.raises(AttributeError):
        issue.number = 2


def test_issue_comment_is_frozen():
    """Test that IssueComment is immutable."""
    comment = IssueComment(author="alice", body="Test", created_at="2026-08-12T10:00:00Z")
    with pytest.raises(AttributeError):
        comment.author = "bob"
