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


def test_fetch_issue_uses_authenticated_gh_api():
    """fetch_issue must go through `gh api` (authenticated) rather than an
    unauthenticated HTTP request, so private repos are readable (issue #2)."""
    with patch("cicaid_devtools.lib.publish_pr.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout='{"number": 328, "title": "T", "body": "B"}', stderr=""
        )
        issue = publish_pr.fetch_issue("leonarduk", "private-repo", 328)

    mock_run.assert_called_once()
    args = mock_run.call_args.args[0]
    assert args == ["gh", "api", "repos/leonarduk/private-repo/issues/328"]
    assert issue == {"number": 328, "title": "T", "body": "B"}


def test_fetch_issue_404_error_mentions_private_repo_access(caplog):
    """A 404 from `gh api` is worded as 'not found, or not accessible' since
    GitHub returns 404 (not 403) for issues the caller lacks access to."""
    with patch("cicaid_devtools.lib.publish_pr.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)"
        )
        issue = publish_pr.fetch_issue("leonarduk", "private-repo", 328)

    assert issue is None
    assert "not found, or not accessible" in caplog.text
    assert "gh auth status" in caplog.text


def test_fetch_issue_non_404_error_is_reported_plainly(caplog):
    """Non-404 `gh api` failures (e.g. network errors) skip the private-repo
    wording and just surface gh's stderr."""
    with patch("cicaid_devtools.lib.publish_pr.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="gh: connection refused"
        )
        issue = publish_pr.fetch_issue("leonarduk", "some-repo", 1)

    assert issue is None
    assert "connection refused" in caplog.text
    assert "not accessible" not in caplog.text


class _FakeResp:
    """Minimal requests.Response stand-in for the LM Studio helpers."""

    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


# --- LM Studio provider (issue #25) ---


def test_get_lmstudio_server_url_defaults():
    assert publish_pr.get_lmstudio_server_url() == "http://localhost:1234"
    assert publish_pr.get_lmstudio_server_url(host="127.0.0.1", port=9000) == "http://127.0.0.1:9000"


def test_is_lmstudio_running_true_with_loaded_models():
    with patch("cicaid_devtools.lib.publish_pr.requests.get") as mock_get:
        mock_get.return_value = _FakeResp(200, {"data": [{"id": "qwen2.5-coder-7b"}]})
        assert publish_pr.is_lmstudio_running() is True


def test_is_lmstudio_running_false_without_loaded_models():
    with patch("cicaid_devtools.lib.publish_pr.requests.get") as mock_get:
        mock_get.return_value = _FakeResp(200, {"data": []})
        assert publish_pr.is_lmstudio_running() is False


def test_is_lmstudio_running_false_on_error():
    with patch("cicaid_devtools.lib.publish_pr.requests.get") as mock_get:
        mock_get.side_effect = requests_exception()
        assert publish_pr.is_lmstudio_running() is False


def requests_exception():
    import requests

    return requests.RequestException("connection refused")


def test_get_lmstudio_model_env_wins(monkeypatch):
    monkeypatch.setenv("LMSTUDIO_MODEL", "explicit-model")
    assert publish_pr.get_lmstudio_model() == "explicit-model"


def test_get_lmstudio_model_autopicks_coder_model():
    with patch("cicaid_devtools.lib.publish_pr.requests.get") as mock_get:
        mock_get.return_value = _FakeResp(
            200, {"data": [{"id": "llama-3.2-3b"}, {"id": "qwen2.5-coder-7b"}]}
        )
        assert publish_pr.get_lmstudio_model() == "qwen2.5-coder-7b"


def test_get_lmstudio_model_none_when_nothing_loaded():
    with patch("cicaid_devtools.lib.publish_pr.requests.get") as mock_get:
        mock_get.return_value = _FakeResp(200, {"data": []})
        assert publish_pr.get_lmstudio_model() is None


def test_get_lmstudio_model_none_on_error():
    with patch("cicaid_devtools.lib.publish_pr.requests.get") as mock_get:
        mock_get.side_effect = requests_exception()
        assert publish_pr.get_lmstudio_model() is None


def test_generate_pr_body_with_lmstudio_success():
    with patch("cicaid_devtools.lib.publish_pr.requests.post") as mock_post:
        mock_post.return_value = _FakeResp(
            200, {"choices": [{"message": {"content": "## What\nLM Studio body"}}]}
        )
        body = publish_pr.generate_pr_body_with_lmstudio("Title", "Body", "qwen2.5-coder-7b")

    assert body == "## What\nLM Studio body"
    args, kwargs = mock_post.call_args
    assert args[0] == "http://localhost:1234/v1/chat/completions"
    assert kwargs["json"]["model"] == "qwen2.5-coder-7b"
    assert kwargs["json"]["messages"][0]["role"] == "user"
    assert "Issue title: Title" in kwargs["json"]["messages"][0]["content"]


def test_generate_pr_body_with_lmstudio_none_when_no_model():
    assert publish_pr.generate_pr_body_with_lmstudio("Title", "Body", "") is None


def test_generate_pr_body_with_lmstudio_none_on_non_200():
    with patch("cicaid_devtools.lib.publish_pr.requests.post") as mock_post:
        mock_post.return_value = _FakeResp(500, {})
        assert publish_pr.generate_pr_body_with_lmstudio("Title", "Body", "m") is None


def test_generate_pr_body_with_lmstudio_none_on_missing_choices():
    with patch("cicaid_devtools.lib.publish_pr.requests.post") as mock_post:
        mock_post.return_value = _FakeResp(200, {})
        assert publish_pr.generate_pr_body_with_lmstudio("Title", "Body", "m") is None


def test_generate_pr_body_with_lmstudio_none_on_empty_content():
    with patch("cicaid_devtools.lib.publish_pr.requests.post") as mock_post:
        mock_post.return_value = _FakeResp(200, {"choices": [{"message": {"content": "   "}}]})
        assert publish_pr.generate_pr_body_with_lmstudio("Title", "Body", "m") is None


def test_generate_pr_body_with_lmstudio_none_on_request_error():
    with patch("cicaid_devtools.lib.publish_pr.requests.post") as mock_post:
        mock_post.side_effect = requests_exception()
        assert publish_pr.generate_pr_body_with_lmstudio("Title", "Body", "m") is None


def test_get_llm_provider_defaults_to_ollama(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert publish_pr.get_llm_provider(None) == "ollama"


def test_get_llm_provider_uses_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "lmstudio")
    assert publish_pr.get_llm_provider(None) == "lmstudio"


def test_get_llm_provider_arg_wins_over_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    assert publish_pr.get_llm_provider("lmstudio") == "lmstudio"


def test_get_llm_provider_rejects_unknown(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    import pytest

    with pytest.raises(ValueError):
        publish_pr.get_llm_provider("bogus")
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    with pytest.raises(ValueError):
        publish_pr.get_llm_provider(None)
