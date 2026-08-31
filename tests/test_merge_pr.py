import subprocess
from unittest.mock import patch

from cicaid_devtools import merge_pr


def test_merge_pr_uses_squash_by_default() -> None:
    def successful_merge(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args == [
            "pr",
            "merge",
            "42",
            "--repo",
            "example/project",
            "--squash",
        ]
        return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

    with patch.object(merge_pr, "run_gh", side_effect=successful_merge) as run_gh:
        assert merge_pr.merge_pr("example", "project", 42, "squash", False, False)

    run_gh.assert_called_once()


def test_merge_pr_adds_delete_branch_and_admin_flags() -> None:
    def successful_merge(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args == [
            "pr",
            "merge",
            "7",
            "--repo",
            "example/project",
            "--rebase",
            "--delete-branch",
            "--admin",
        ]
        return subprocess.CompletedProcess(args, returncode=0, stdout="", stderr="")

    with patch.object(merge_pr, "run_gh", side_effect=successful_merge):
        assert merge_pr.merge_pr("example", "project", 7, "rebase", True, True)


def test_merge_pr_reports_failure() -> None:
    failure = subprocess.CompletedProcess(
        ["gh", "pr", "merge"], returncode=1, stdout="", stderr="merge conflict"
    )
    with patch.object(merge_pr, "run_gh", return_value=failure):
        assert not merge_pr.merge_pr("example", "project", 42, "squash", False, False)


def test_prompt_for_pr_exits_when_no_open_prs() -> None:
    try:
        merge_pr.prompt_for_pr([])
        raised = False
    except SystemExit:
        raised = True
    assert raised


def test_prompt_for_pr_selects_matching_number() -> None:
    prs = [
        {"number": 1, "title": "First", "headRefName": "a", "author": {"login": "alice"}},
        {"number": 2, "title": "Second", "headRefName": "b", "author": {"login": "bob"}},
    ]
    with patch("builtins.input", return_value="2"):
        assert merge_pr.prompt_for_pr(prs) == prs[1]
