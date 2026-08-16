import subprocess
from unittest.mock import MagicMock, patch

import pytest

from cicaid_devtools import work_on_issue as woi
from cicaid_devtools.work_on_issue import (
    create_branch,
    find_pr_branch_for_issue,
    pop_stash,
    referenced_issue_ids,
    slugify,
    stash_if_dirty,
)


# ───────────────────────────────── slugify ─────────────────────────────────


def test_slugify_normal_title():
    assert slugify("Fix the login bug") == "fix-the-login-bug"


def test_slugify_truncates_to_50_chars():
    assert len(slugify("x " * 60)) <= 50


def test_slugify_never_ends_in_hyphen():
    assert not slugify("Trailing punctuation!!!").endswith("-")


def test_slugify_falls_back_to_hash_for_emoji_only_title():
    slug = slugify("🎉🎉🎉")
    assert slug != ""
    assert all(c in "0123456789abcdef" for c in slug)
    assert len(slug) == 8


def test_slugify_is_deterministic_for_hash_fallback():
    assert slugify("🎉🎉🎉") == slugify("🎉🎉🎉")


# ──────────────────────── referenced_issue_ids ─────────────────────────────


def test_referenced_issue_ids_extracts_closes_reference():
    assert referenced_issue_ids("Some body\n\nCloses #155") == {155}


def test_referenced_issue_ids_empty_when_no_reference():
    assert referenced_issue_ids("Just a plain description") == set()


# ───────────────────────── find_pr_branch_for_issue ─────────────────────────


def test_find_pr_branch_for_issue_finds_direct_reference():
    """An open PR that closes this issue directly -> return its branch."""
    with patch.object(woi.requests, "get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"number": 200, "body": "Closes #156", "head": {"ref": "fix/other"}}
            ],
        )
        mock_get.return_value.raise_for_status = MagicMock()

        result = find_pr_branch_for_issue("owner", "repo", 156, "title\nbody")

        assert result == (200, "fix/other")


def test_find_pr_branch_for_issue_follows_duplicate_reference():
    """Issue #156 says 'Closes #155'; a PR closing #155 resolves #156 too."""
    with patch.object(woi.requests, "get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "number": 156,
                    "body": "Closes #155",
                    "head": {"ref": "fix/issue-155-update-readme"},
                }
            ],
        )
        mock_get.return_value.raise_for_status = MagicMock()

        result = find_pr_branch_for_issue(
            "owner", "repo", 156, "[Issue #155] title\nCloses #155"
        )

        assert result == (156, "fix/issue-155-update-readme")


def test_find_pr_branch_for_issue_returns_none_when_no_match():
    with patch.object(woi.requests, "get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"number": 1, "body": "Closes #999", "head": {"ref": "fix/x"}}],
        )
        mock_get.return_value.raise_for_status = MagicMock()

        assert find_pr_branch_for_issue("owner", "repo", 156, "title\nbody") is None


def test_find_pr_branch_for_issue_returns_none_on_request_failure(caplog):
    import requests as req

    with patch.object(woi.requests, "get") as mock_get:
        mock_get.side_effect = req.ConnectionError("network down")

        result = find_pr_branch_for_issue("owner", "repo", 156, "title\nbody")

        assert result is None
        assert "Could not check for an existing linked PR" in caplog.text


# ──────────────────────────── create_branch ────────────────────────────────


def test_create_branch_skips_creation_when_branch_exists():
    """GET returns 200 → skip creation, do not POST."""
    with patch.object(woi.requests, "get") as mock_get, patch.object(
        woi.requests, "post"
    ) as mock_post:
        mock_get.return_value = MagicMock(status_code=200)

        create_branch("testowner", "testrepo", "fix/issue-1-slug", "abc123")

        mock_get.assert_called_once()
        mock_post.assert_not_called()


def test_create_branch_creates_when_branch_absent():
    """GET returns 404 → proceed with POST creation."""
    with patch.object(woi.requests, "get") as mock_get, patch.object(
        woi.requests, "post"
    ) as mock_post:
        mock_get.return_value = MagicMock(status_code=404)
        mock_post.return_value = MagicMock()
        mock_post.return_value.raise_for_status = MagicMock()

        create_branch("testowner", "testrepo", "fix/issue-1-slug", "abc123")

        mock_get.assert_called_once()
        mock_post.assert_called_once()


def test_create_branch_proceeds_when_get_fails(caplog):
    """GET raises RequestException → log warning, proceed with POST."""
    import requests as req

    with patch.object(woi.requests, "get") as mock_get, patch.object(
        woi.requests, "post"
    ) as mock_post:
        mock_get.side_effect = req.ConnectionError("network down")
        mock_post.return_value = MagicMock()
        mock_post.return_value.raise_for_status = MagicMock()

        create_branch("testowner", "testrepo", "fix/issue-1-slug", "abc123")

        assert "Could not check for existing branch" in caplog.text
        mock_post.assert_called_once()


def test_create_branch_proceeds_on_unexpected_get_status(caplog):
    """GET returns 403 (not 200 or 404) → log warning, proceed with POST."""
    with patch.object(woi.requests, "get") as mock_get, patch.object(
        woi.requests, "post"
    ) as mock_post:
        mock_get.return_value = MagicMock(status_code=403)
        mock_post.return_value = MagicMock()
        mock_post.return_value.raise_for_status = MagicMock()

        create_branch("testowner", "testrepo", "fix/issue-1-slug", "abc123")

        assert "Unexpected status 403" in caplog.text
        mock_post.assert_called_once()


def test_create_branch_handles_422_race_condition(caplog):
    """GET returned 404 but POST gets 422 (race) → log warning, do not exit."""
    import requests as req

    with patch.object(woi.requests, "get") as mock_get, patch.object(
        woi.requests, "post"
    ) as mock_post:
        mock_get.return_value = MagicMock(status_code=404)
        mock_resp = MagicMock(
            status_code=422, text='{"message": "Reference already exists"}'
        )
        mock_resp.raise_for_status.side_effect = req.HTTPError(response=mock_resp)
        mock_post.return_value = mock_resp

        create_branch("testowner", "testrepo", "fix/issue-1-slug", "abc123")

        assert "already exists" in caplog.text


def test_create_branch_exits_on_other_http_error():
    """POST gets a non-422 HTTPError → sys.exit(1)."""
    import requests as req

    with patch.object(woi.requests, "get") as mock_get, patch.object(
        woi.requests, "post"
    ) as mock_post:
        mock_get.return_value = MagicMock(status_code=404)
        mock_resp = MagicMock(status_code=500, text="Internal Server Error")
        mock_resp.raise_for_status.side_effect = req.HTTPError(response=mock_resp)
        mock_post.return_value = mock_resp

        with pytest.raises(SystemExit) as exc_info:
            create_branch("testowner", "testrepo", "fix/issue-1-slug", "abc123")

        assert exc_info.value.code == 1


def test_create_branch_exits_on_other_request_exception():
    """POST raises non-HTTP RequestException → sys.exit(1)."""
    import requests as req

    with patch.object(woi.requests, "get") as mock_get, patch.object(
        woi.requests, "post"
    ) as mock_post:
        mock_get.return_value = MagicMock(status_code=404)
        mock_post.side_effect = req.ConnectionError("network down during POST")

        with pytest.raises(SystemExit) as exc_info:
            create_branch("testowner", "testrepo", "fix/issue-1-slug", "abc123")

        assert exc_info.value.code == 1


# ────────────────────────── stash_if_dirty / pop_stash ─────────────────────


def test_stash_if_dirty_skips_when_clean():
    """Empty `git status --porcelain` output → no stash created, returns False."""
    with patch.object(woi.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(stdout="")

        result = stash_if_dirty(145)

        assert result is False
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ["git", "status", "--porcelain"]


def test_stash_if_dirty_stashes_when_dirty():
    """Non-empty status output → `git stash push -u` is run, returns True."""
    with patch.object(woi.subprocess, "run") as mock_run:
        mock_run.side_effect = [
            MagicMock(stdout=" M README.md\n"),
            MagicMock(),
        ]

        result = stash_if_dirty(145)

        assert result is True
        assert mock_run.call_count == 2
        stash_call = mock_run.call_args_list[1][0][0]
        assert stash_call[:3] == ["git", "stash", "push"]
        assert "-u" in stash_call
        assert mock_run.call_args_list[1][1]["check"] is True


def test_pop_stash_succeeds():
    """`git stash pop` exits 0 → returns True, no error logged."""
    with patch.object(woi.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        assert pop_stash() is True


def test_pop_stash_reports_conflict(caplog):
    """`git stash pop` exits non-zero (conflict) → returns False, logs guidance."""
    with patch.object(woi.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="CONFLICT (content): README.md"
        )

        result = pop_stash()

        assert result is False
        assert "Could not automatically restore" in caplog.text
        assert "git stash pop" in caplog.text


# ─────────────────────── main(): stash restored on early failure ───────────


def test_main_restores_stash_when_a_step_fails_before_the_final_pop(monkeypatch):
    """A failure after stashing (e.g. `git fetch` fails) must still restore
    the stash via the `finally` block, instead of leaving it dangling."""
    monkeypatch.setattr(woi, "get_repo_info", lambda: ("testowner", "testrepo"))
    monkeypatch.setattr(woi, "is_wiki_repo", lambda: False)
    monkeypatch.setattr(
        woi,
        "fetch_issue",
        lambda owner, repo, issue_id, token=None: {"title": "Some issue", "body": "body"},
    )
    monkeypatch.setattr(woi, "find_pr_branch_for_issue", lambda *a, **k: None)
    monkeypatch.setattr(woi, "stash_if_dirty", lambda issue_id: True)
    pop_mock = MagicMock(return_value=True)
    monkeypatch.setattr(woi, "pop_stash", pop_mock)

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["git", "fetch"]:
            raise subprocess.CalledProcessError(1, cmd)
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(woi.subprocess, "run", fake_run)
    monkeypatch.setattr(woi.sys, "argv", ["cicaid-work-on-issue", "145"])

    with pytest.raises(SystemExit) as exc_info:
        woi.main()

    assert exc_info.value.code == 1
    pop_mock.assert_called_once()


def test_main_does_not_double_pop_stash_on_success(monkeypatch):
    """The deliberate final pop must not be repeated by the `finally` guard
    once the workflow reaches it successfully."""
    monkeypatch.setattr(woi, "get_repo_info", lambda: ("testowner", "testrepo"))
    monkeypatch.setattr(woi, "is_wiki_repo", lambda: False)
    monkeypatch.setattr(
        woi,
        "fetch_issue",
        lambda owner, repo, issue_id, token=None: {"title": "Some issue", "body": "body"},
    )
    monkeypatch.setattr(woi, "find_pr_branch_for_issue", lambda *a, **k: None)
    monkeypatch.setattr(woi, "stash_if_dirty", lambda issue_id: True)
    pop_mock = MagicMock(return_value=True)
    monkeypatch.setattr(woi, "pop_stash", pop_mock)

    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["git", "rev-parse"] and "--verify" in cmd:
            return MagicMock(returncode=1, stdout="", stderr="")
        if cmd[:2] == ["git", "rev-parse"]:
            return MagicMock(returncode=0, stdout="fix/issue-145-some-issue\n", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(woi.subprocess, "run", fake_run)
    monkeypatch.setattr(woi.sys, "argv", ["cicaid-work-on-issue", "145"])
    monkeypatch.setattr(woi.Path, "write_text", lambda self, *a, **k: None)

    woi.main()

    pop_mock.assert_called_once()


def test_create_branch_includes_auth_header_when_token_provided():
    """Token is passed through to both GET and POST Authorization headers."""
    with patch.object(woi.requests, "get") as mock_get, patch.object(
        woi.requests, "post"
    ) as mock_post:
        mock_get.return_value = MagicMock(status_code=404)
        mock_post.return_value = MagicMock()
        mock_post.return_value.raise_for_status = MagicMock()

        create_branch(
            "testowner", "testrepo", "fix/issue-1-slug", "abc123", token="ghp_test"
        )

        expected_headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": "token ghp_test",
        }
        mock_get.assert_called_once()
        assert mock_get.call_args[1]["headers"] == expected_headers
        mock_post.assert_called_once()
        assert mock_post.call_args[1]["headers"] == expected_headers
