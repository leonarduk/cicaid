import json
import subprocess
from pathlib import Path
from unittest.mock import patch

from cicaid_devtools import add_issue_to_pr


def test_update_pr_body_uses_rest_api_without_org_scope() -> None:
    pr = add_issue_to_pr.PullRequest(number=42, title="A change", body="Details")

    def successful_api_call(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args[:4] == [
            "api",
            "--method",
            "PATCH",
            "repos/example/project/pulls/42",
        ]
        assert args[4] == "--input"
        payload = json.loads(Path(args[5]).read_text(encoding="utf-8"))
        assert payload == {"body": "Details\n\nCloses #99"}
        return subprocess.CompletedProcess(args, returncode=0, stdout="{}", stderr="")

    with patch.object(add_issue_to_pr, "run_gh", side_effect=successful_api_call) as run_gh:
        assert add_issue_to_pr.update_pr_body("example", "project", pr, 99)

    run_gh.assert_called_once()


def test_update_pr_body_reports_rest_api_failure() -> None:
    pr = add_issue_to_pr.PullRequest(number=42, title="A change", body="")
    failure = subprocess.CompletedProcess(
        ["gh", "api"], returncode=1, stdout="", stderr="permission denied"
    )

    with patch.object(add_issue_to_pr, "run_gh", return_value=failure):
        assert not add_issue_to_pr.update_pr_body("example", "project", pr, 99)


def test_update_pr_body_handles_missing_body() -> None:
    pr = add_issue_to_pr.PullRequest(number=42, title="A change", body=None)  # type: ignore[arg-type]

    def successful_api_call(args: list[str]) -> subprocess.CompletedProcess[str]:
        payload = json.loads(Path(args[-1]).read_text(encoding="utf-8"))
        assert payload == {"body": "Closes #99"}
        return subprocess.CompletedProcess(args, returncode=0, stdout="{}", stderr="")

    with patch.object(add_issue_to_pr, "run_gh", side_effect=successful_api_call):
        assert add_issue_to_pr.update_pr_body("example", "project", pr, 99)


def test_filter_existing_labels_drops_missing_labels() -> None:
    listing = subprocess.CompletedProcess(
        ["gh", "label", "list"],
        returncode=0,
        stdout=json.dumps([{"name": "bug"}, {"name": "documentation"}]),
        stderr="",
    )

    with patch.object(add_issue_to_pr, "run_gh", return_value=listing):
        result = add_issue_to_pr.filter_existing_labels(
            "example", "project", ["bug", "Medium Value"]
        )

    assert result == ["bug"]


def test_filter_existing_labels_drops_all_when_query_fails() -> None:
    failure = subprocess.CompletedProcess(
        ["gh", "label", "list"], returncode=1, stdout="", stderr="not found"
    )

    with patch.object(add_issue_to_pr, "run_gh", return_value=failure):
        result = add_issue_to_pr.filter_existing_labels(
            "example", "project", ["bug", "Medium Value"]
        )

    assert result == []


def test_fetch_repo_labels_handles_bad_json() -> None:
    bad = subprocess.CompletedProcess(
        ["gh", "label", "list"], returncode=0, stdout="not json", stderr=""
    )

    with patch.object(add_issue_to_pr, "run_gh", return_value=bad):
        assert add_issue_to_pr.fetch_repo_labels("example", "project") is None


def test_fetch_repo_labels_handles_unexpected_json_shape() -> None:
    wrong_shape = subprocess.CompletedProcess(
        ["gh", "label", "list"], returncode=0, stdout="null", stderr=""
    )

    with patch.object(add_issue_to_pr, "run_gh", return_value=wrong_shape):
        assert add_issue_to_pr.fetch_repo_labels("example", "project") is None


def test_filter_existing_labels_matches_case_insensitively() -> None:
    listing = subprocess.CompletedProcess(
        ["gh", "label", "list"],
        returncode=0,
        stdout=json.dumps([{"name": "medium value"}]),
        stderr="",
    )

    with patch.object(add_issue_to_pr, "run_gh", return_value=listing):
        result = add_issue_to_pr.filter_existing_labels("example", "project", ["Medium Value"])

    # Keeps the repo's own canonical spelling rather than the requested one.
    assert result == ["medium value"]
