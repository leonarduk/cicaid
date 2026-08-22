"""Tests for scripts/version_bump.py's detect_repo_url()."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from version_bump import detect_repo_url  # noqa: E402


def _with_remote(remote: str) -> MagicMock:
    return MagicMock(returncode=0, stdout=f"{remote}\n")


@patch("version_bump.subprocess.run")
def test_detect_repo_url_handles_ssh_shorthand(mock_run):
    mock_run.return_value = _with_remote("git@github.com:owner/repo.git")
    assert detect_repo_url() == "https://github.com/owner/repo"


@patch("version_bump.subprocess.run")
def test_detect_repo_url_handles_https(mock_run):
    mock_run.return_value = _with_remote("https://github.com/owner/repo.git")
    assert detect_repo_url() == "https://github.com/owner/repo"


@patch("version_bump.subprocess.run")
def test_detect_repo_url_handles_ssh_url_form(mock_run):
    mock_run.return_value = _with_remote("ssh://git@github.com/owner/repo.git")
    assert detect_repo_url() == "https://github.com/owner/repo"


@patch("version_bump.subprocess.run")
def test_detect_repo_url_handles_git_protocol(mock_run):
    mock_run.return_value = _with_remote("git://github.com/owner/repo.git")
    assert detect_repo_url() == "https://github.com/owner/repo"


@patch("version_bump.subprocess.run")
def test_detect_repo_url_returns_empty_on_unparseable_remote(mock_run):
    mock_run.return_value = _with_remote("not-a-git-url-at-all")
    assert detect_repo_url() == ""


@patch("version_bump.subprocess.run")
def test_detect_repo_url_returns_empty_when_no_remote(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="")
    assert detect_repo_url() == ""
