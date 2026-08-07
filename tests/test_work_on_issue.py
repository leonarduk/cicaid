from unittest.mock import MagicMock, patch

import pytest

from cicaid_devtools import work_on_issue as woi
from cicaid_devtools.work_on_issue import create_branch, slugify


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
