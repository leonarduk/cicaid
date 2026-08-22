import json
import subprocess
from unittest.mock import patch

import pytest

from cicaid_devtools import update_prs


def _pr_list_result(items: list[dict]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["gh", "pr", "list"], returncode=0, stdout=json.dumps(items), stderr=""
    )


def _compare_result(behind_by: int) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["gh", "api"], returncode=0, stdout=f"{behind_by}\n", stderr=""
    )


def _pr(**overrides) -> update_prs.PullRequest:
    defaults = dict(
        number=1,
        title="A change",
        author="octocat",
        base_ref="main",
        head_ref="feature",
        mergeable_state="clean",
    )
    defaults.update(overrides)
    return update_prs.PullRequest(**defaults)


def test_fetch_open_prs_parses_author_refs_and_state() -> None:
    listing = _pr_list_result(
        [
            {
                "number": 1,
                "title": "A change",
                "author": {"login": "octocat"},
                "baseRefName": "main",
                "headRefName": "feature",
                "mergeStateStatus": "BEHIND",
            }
        ]
    )
    with patch.object(update_prs, "run_gh", return_value=listing):
        prs = update_prs.fetch_open_prs("example", "project")

    assert prs == [_pr(mergeable_state="behind")]


def test_fetch_behind_by_parses_integer_output() -> None:
    with patch.object(update_prs, "run_gh", return_value=_compare_result(5)):
        assert update_prs.fetch_behind_by("example", "project", "main", "feature") == 5


def test_fetch_behind_by_returns_none_on_failure() -> None:
    failure = subprocess.CompletedProcess(
        ["gh", "api"], returncode=1, stdout="", stderr="not found"
    )
    with patch.object(update_prs, "run_gh", return_value=failure):
        assert update_prs.fetch_behind_by("example", "project", "main", "feature") is None


def test_fetch_behind_by_returns_none_on_unparseable_output() -> None:
    bad = subprocess.CompletedProcess(["gh", "api"], returncode=0, stdout="null\n", stderr="")
    with patch.object(update_prs, "run_gh", return_value=bad):
        assert update_prs.fetch_behind_by("example", "project", "main", "feature") is None


def test_process_pr_skips_dirty_prs_without_querying_compare() -> None:
    pr = _pr(mergeable_state="dirty")

    with patch.object(update_prs, "run_gh") as run_gh:
        assert update_prs.process_pr("example", "project", pr, dry_run=False, rebase=False)

    run_gh.assert_not_called()


def test_process_pr_skips_when_not_behind() -> None:
    pr = _pr()

    with patch.object(update_prs, "run_gh", return_value=_compare_result(0)) as run_gh:
        assert update_prs.process_pr("example", "project", pr, dry_run=False, rebase=False)

    run_gh.assert_called_once()


def test_process_pr_skips_when_behind_count_unknown() -> None:
    pr = _pr()
    failure = subprocess.CompletedProcess(["gh", "api"], returncode=1, stdout="", stderr="boom")

    with patch.object(update_prs, "run_gh", return_value=failure):
        assert update_prs.process_pr("example", "project", pr, dry_run=False, rebase=False)


def test_process_pr_updates_branch_when_behind() -> None:
    pr = _pr()
    update_success = subprocess.CompletedProcess(
        ["gh", "pr", "update-branch"], returncode=0, stdout="", stderr=""
    )

    with patch.object(
        update_prs, "run_gh", side_effect=[_compare_result(3), update_success]
    ) as run_gh:
        assert update_prs.process_pr("example", "project", pr, dry_run=False, rebase=False)

    assert run_gh.call_args_list[1].args[0] == [
        "pr",
        "update-branch",
        "--repo",
        "example/project",
        "1",
    ]


def test_process_pr_passes_rebase_flag() -> None:
    pr = _pr()
    update_success = subprocess.CompletedProcess(
        ["gh", "pr", "update-branch"], returncode=0, stdout="", stderr=""
    )

    with patch.object(
        update_prs, "run_gh", side_effect=[_compare_result(3), update_success]
    ) as run_gh:
        assert update_prs.process_pr("example", "project", pr, dry_run=False, rebase=True)

    assert run_gh.call_args_list[1].args[0] == [
        "pr",
        "update-branch",
        "--repo",
        "example/project",
        "1",
        "--rebase",
    ]


def test_process_pr_dry_run_does_not_call_update_branch() -> None:
    pr = _pr()

    with patch.object(update_prs, "run_gh", return_value=_compare_result(3)) as run_gh:
        assert update_prs.process_pr("example", "project", pr, dry_run=True, rebase=False)

    run_gh.assert_called_once()


def test_process_pr_reports_failure() -> None:
    pr = _pr()
    failure = subprocess.CompletedProcess(
        ["gh", "pr", "update-branch"], returncode=1, stdout="", stderr="conflict"
    )

    with patch.object(update_prs, "run_gh", side_effect=[_compare_result(3), failure]):
        assert not update_prs.process_pr("example", "project", pr, dry_run=False, rebase=False)


def test_resolve_repo_rejects_malformed_explicit_repo() -> None:
    with pytest.raises(SystemExit) as exc_info:
        update_prs.resolve_repo("not-a-valid-repo")
    assert exc_info.value.code == 1
