import subprocess
from unittest.mock import patch

import pytest

from cicaid_devtools.lib.github_repo import get_repo_info, get_repo_root


def _completed(stdout: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


@pytest.mark.parametrize(
    "remote_url,expected",
    [
        ("https://github.com/leonarduk/cicaid.git", ("leonarduk", "cicaid")),
        ("https://github.com/leonarduk/cicaid", ("leonarduk", "cicaid")),
        ("git@github.com:leonarduk/allotmint-mcp.git", ("leonarduk", "allotmint-mcp")),
        ("git@github.com:leonarduk/allotmint-mcp.git\n", ("leonarduk", "allotmint-mcp")),
    ],
)
def test_get_repo_info_parses_remote_url(remote_url, expected):
    with patch("subprocess.run", return_value=_completed(remote_url)):
        assert get_repo_info() == expected


def test_get_repo_info_raises_on_non_github_remote():
    with patch("subprocess.run", return_value=_completed("https://gitlab.com/foo/bar.git")):
        with pytest.raises(ValueError):
            get_repo_info()


def test_get_repo_info_raises_when_git_fails():
    with patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["git"]),
    ):
        with pytest.raises(ValueError):
            get_repo_info()


def test_get_repo_root_strips_trailing_whitespace():
    with patch("subprocess.run", return_value=_completed("/home/user/repo\n")):
        assert get_repo_root() == "/home/user/repo"


def test_get_repo_root_raises_when_not_a_git_repo():
    with patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(128, ["git"]),
    ):
        with pytest.raises(ValueError):
            get_repo_root()
