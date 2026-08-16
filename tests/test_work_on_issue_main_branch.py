from subprocess import CompletedProcess
from unittest.mock import Mock, call

import pytest

from cicaid_devtools import work_on_issue


@pytest.mark.parametrize("branch_name", ["main", "master", "trunk"])
def test_get_main_branch_sha_uses_remote_head(monkeypatch, branch_name):
    sha = "a" * 40
    mock_run = Mock(
        side_effect=[
            CompletedProcess([], 0, f"refs/remotes/origin/{branch_name}\n", ""),
            CompletedProcess([], 0, f"{sha}\n", ""),
        ]
    )
    monkeypatch.setattr(work_on_issue.subprocess, "run", mock_run)

    assert work_on_issue.get_main_branch_sha("owner", "repo") == sha
    assert mock_run.call_args_list == [
        call(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        ),
        call(
            ["git", "rev-parse", f"refs/remotes/origin/{branch_name}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        ),
    ]


@pytest.mark.parametrize(
    "symbolic_ref",
    [
        CompletedProcess([], 1, "", "fatal: ref is not a symbolic ref"),
        CompletedProcess([], 0, "refs/remotes/upstream/main\n", ""),
    ],
)
def test_get_main_branch_sha_exits_when_remote_head_is_unavailable(
    monkeypatch, caplog, symbolic_ref
):
    monkeypatch.setattr(work_on_issue.subprocess, "run", lambda *args, **kwargs: symbolic_ref)

    with pytest.raises(SystemExit) as exc_info:
        work_on_issue.get_main_branch_sha("owner", "repo")

    assert exc_info.value.code == 1
    assert "Failed to determine the default branch from origin/HEAD" in caplog.text


def test_get_main_branch_sha_exits_when_sha_lookup_fails(monkeypatch, caplog):
    mock_run = Mock(
        side_effect=[
            CompletedProcess([], 0, "refs/remotes/origin/trunk\n", ""),
            CompletedProcess([], 1, "", "fatal: unknown revision"),
        ]
    )
    monkeypatch.setattr(work_on_issue.subprocess, "run", mock_run)

    with pytest.raises(SystemExit) as exc_info:
        work_on_issue.get_main_branch_sha("owner", "repo")

    assert exc_info.value.code == 1
    assert "Failed to get default branch SHA for origin/trunk" in caplog.text
