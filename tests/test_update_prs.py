import json
import subprocess
from unittest.mock import patch

import pytest

from cicaid_devtools import update_prs


def _pr_list_result(items: list[dict]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["gh", "pr", "list"], returncode=0, stdout=json.dumps(items), stderr=""
    )


def _pr(**overrides) -> update_prs.PullRequest:
    defaults = dict(number=1, title="A change", author="octocat", mergeable_state="behind")
    defaults.update(overrides)
    return update_prs.PullRequest(**defaults)


def test_fetch_open_prs_parses_author_and_state() -> None:
    listing = _pr_list_result(
        [
            {
                "number": 1,
                "title": "A change",
                "author": {"login": "octocat"},
                "mergeStateStatus": "BEHIND",
            }
        ]
    )
    with patch.object(update_prs, "run_gh", return_value=listing):
        prs = update_prs.fetch_open_prs("example", "project")

    assert prs == [_pr()]


def test_process_pr_skips_when_not_behind() -> None:
    pr = _pr(mergeable_state="clean")

    with patch.object(update_prs, "run_gh") as run_gh:
        assert update_prs.process_pr("example", "project", pr, dry_run=False, rebase=False)

    run_gh.assert_not_called()


def test_process_pr_updates_branch_when_behind() -> None:
    pr = _pr()
    success = subprocess.CompletedProcess(
        ["gh", "pr", "update-branch"], returncode=0, stdout="", stderr=""
    )

    with patch.object(update_prs, "run_gh", return_value=success) as run_gh:
        assert update_prs.process_pr("example", "project", pr, dry_run=False, rebase=False)

    run_gh.assert_called_once_with(["pr", "update-branch", "--repo", "example/project", "1"])


def test_process_pr_passes_rebase_flag() -> None:
    pr = _pr()
    success = subprocess.CompletedProcess(
        ["gh", "pr", "update-branch"], returncode=0, stdout="", stderr=""
    )

    with patch.object(update_prs, "run_gh", return_value=success) as run_gh:
        assert update_prs.process_pr("example", "project", pr, dry_run=False, rebase=True)

    run_gh.assert_called_once_with(
        ["pr", "update-branch", "--repo", "example/project", "1", "--rebase"]
    )


def test_process_pr_dry_run_does_not_call_gh() -> None:
    pr = _pr()

    with patch.object(update_prs, "run_gh") as run_gh:
        assert update_prs.process_pr("example", "project", pr, dry_run=True, rebase=False)

    run_gh.assert_not_called()


def test_process_pr_reports_failure() -> None:
    pr = _pr()
    failure = subprocess.CompletedProcess(
        ["gh", "pr", "update-branch"], returncode=1, stdout="", stderr="conflict"
    )

    with patch.object(update_prs, "run_gh", return_value=failure):
        assert not update_prs.process_pr("example", "project", pr, dry_run=False, rebase=False)


def test_resolve_repo_rejects_malformed_explicit_repo() -> None:
    with pytest.raises(SystemExit) as exc_info:
        update_prs.resolve_repo("not-a-valid-repo")
    assert exc_info.value.code == 1
