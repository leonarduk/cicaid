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
