import logging

from cicaid_devtools import dependabot_auto_merge as dam


def _check(name: str, conclusion: str = "SUCCESS", status: str = "COMPLETED") -> dict:
    return {"name": name, "workflowName": "CI", "status": status, "conclusion": conclusion}


def test_checks_have_passed_true_when_all_succeeded() -> None:
    checks = [
        _check("lint"),
        _check("tests", conclusion="NEUTRAL"),
        _check("build", conclusion="SKIPPED"),
    ]
    assert dam.checks_have_passed(checks) is True


def test_checks_have_passed_false_when_empty() -> None:
    assert dam.checks_have_passed([]) is False


def test_checks_have_passed_false_when_one_failed() -> None:
    checks = [_check("lint"), _check("tests", conclusion="FAILURE")]
    assert dam.checks_have_passed(checks) is False


def test_checks_have_passed_false_when_still_running() -> None:
    checks = [_check("lint"), _check("tests", conclusion="", status="IN_PROGRESS")]
    assert dam.checks_have_passed(checks) is False


def test_checks_have_passed_uses_latest_duplicate() -> None:
    checks = [
        {
            "name": "tests",
            "workflowName": "CI",
            "status": "COMPLETED",
            "conclusion": "CANCELLED",
            "completedAt": "1",
        },
        {
            "name": "tests",
            "workflowName": "CI",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "completedAt": "2",
        },
    ]
    assert dam.checks_have_passed(checks) is True


def test_describe_unresolved_checks_reports_failing_and_pending() -> None:
    checks = [
        _check("lint"),
        _check("tests", conclusion="FAILURE"),
        _check("build", conclusion="", status="QUEUED"),
    ]
    description = dam._describe_unresolved_checks(checks)
    assert "tests=FAILURE" in description
    assert "build=QUEUED" in description
    assert "lint" not in description


def test_describe_unresolved_checks_when_no_checks_reported() -> None:
    assert dam._describe_unresolved_checks([]) == "no checks reported yet"


def test_process_pr_skip_message_names_failing_check(caplog) -> None:
    pr = dam.PullRequest(
        number=8092,
        title="build(deps): bump foo",
        head_ref_name="dependabot/pip/foo",
        checks=[_check("lint"), _check("tests", conclusion="FAILURE")],
    )
    with caplog.at_level(logging.INFO):
        result = dam.process_pr(pr, dry_run=True)

    assert result is True
    assert "tests=FAILURE" in caplog.text
    assert "checks not all passed" in caplog.text


def test_is_mergeable_rejects_conflicting() -> None:
    pr = dam.PullRequest(
        number=1, title="t", head_ref_name="h", mergeable="CONFLICTING", mergeable_state="clean"
    )
    assert dam.is_mergeable(pr) is False


def test_is_mergeable_accepts_behind_blocked_unstable() -> None:
    for state in ("clean", "behind", "blocked", "unstable"):
        pr = dam.PullRequest(
            number=1, title="t", head_ref_name="h", mergeable="MERGEABLE", mergeable_state=state
        )
        assert dam.is_mergeable(pr) is True


def test_is_mergeable_rejects_unknown_state() -> None:
    pr = dam.PullRequest(
        number=1, title="t", head_ref_name="h", mergeable="MERGEABLE", mergeable_state=""
    )
    assert dam.is_mergeable(pr) is False
