"""Tests for cicaid_devtools.update_issue (the `update-issue` command)."""

import github_issues  # same top-level module update_issue.py imports (see conftest.py)

from cicaid_devtools.lib.github_issues import Issue
from cicaid_devtools.update_issue import main, parse_issue_file

OWNER = "leonarduk"
REPO_NAME = "cicaid"
REPO = f"{OWNER}/{REPO_NAME}"


def _write_issue_file(tmp_path, issue_id, title, body):
    path = tmp_path / f".issue-{issue_id}.md"
    path.write_text(f"{title}\n\n{body}\n", encoding="utf-8")
    return path


def _issue(number=367, title="Old title", body="## What\n\nOld body", url=None):
    return Issue(
        number=number,
        title=title,
        body=body,
        url=url or f"https://github.com/{REPO}/issues/{number}",
    )


def _patch_github(monkeypatch, current):
    """Stub repo lookup / issue fetch and record update_issue() calls.

    Returns the list of (repo, number, title, body) tuples passed to the
    (faked) lib update_issue.
    """
    monkeypatch.setattr(
        "cicaid_devtools.update_issue.get_repo_info", lambda: (OWNER, REPO_NAME)
    )
    monkeypatch.setattr("cicaid_devtools.update_issue.get_issue", lambda repo, number: current)
    calls = []
    monkeypatch.setattr(
        "cicaid_devtools.update_issue.update_issue",
        lambda repo, number, title, body: calls.append((repo, number, title, body)) or True,
    )
    return calls


# ------------------------------------------------------------- parse_issue_file


def test_parse_issue_file_title_and_body(tmp_path):
    path = _write_issue_file(tmp_path, 367, "A title", "## What\n\nA body")

    assert parse_issue_file(path) == ("A title", "## What\n\nA body")


def test_parse_issue_file_title_only(tmp_path):
    path = _write_issue_file(tmp_path, 367, "A title", "")

    assert parse_issue_file(path) == ("A title", "")


# --------------------------------------------------------------- main: happy path


def test_main_updates_issue_after_confirmation(tmp_path, monkeypatch):
    _write_issue_file(tmp_path, 367, "New title", "## What\n\nNew body")
    monkeypatch.chdir(tmp_path)
    calls = _patch_github(monkeypatch, _issue())
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    assert main(["367"]) == 0
    assert calls == [(REPO, 367, "New title", "## What\n\nNew body")]


def test_main_yes_skips_confirmation(tmp_path, monkeypatch):
    _write_issue_file(tmp_path, 367, "New title", "## What\n\nNew body")
    monkeypatch.chdir(tmp_path)
    calls = _patch_github(monkeypatch, _issue())

    def fail_input(prompt=""):
        raise AssertionError("input() must not be called with --yes")

    monkeypatch.setattr("builtins.input", fail_input)

    assert main(["367", "--yes"]) == 0
    assert calls == [(REPO, 367, "New title", "## What\n\nNew body")]


def test_main_non_interactive_env_skips_prompt_and_fails(tmp_path, monkeypatch):
    _write_issue_file(tmp_path, 367, "New title", "## What\n\nNew body")
    monkeypatch.chdir(tmp_path)
    calls = _patch_github(monkeypatch, _issue())
    monkeypatch.setenv("CICAID_NON_INTERACTIVE", "1")

    def fail_input(prompt=""):
        raise AssertionError("input() must not be called when CICAID_NON_INTERACTIVE is set")

    monkeypatch.setattr("builtins.input", fail_input)

    assert main(["367"]) == 1
    assert calls == []


def test_main_declines_confirmation(tmp_path, monkeypatch, capsys):
    _write_issue_file(tmp_path, 367, "New title", "## What\n\nNew body")
    monkeypatch.chdir(tmp_path)
    calls = _patch_github(monkeypatch, _issue())
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    assert main(["367"]) == 0
    assert calls == []
    assert "Aborted." in capsys.readouterr().out


# --------------------------------------------------------------- main: safety paths


def test_main_noop_when_local_matches_remote(tmp_path, monkeypatch, caplog):
    _write_issue_file(tmp_path, 367, "Same title", "Same body")
    monkeypatch.chdir(tmp_path)
    calls = _patch_github(monkeypatch, _issue(title="Same title", body="Same body"))
    caplog.set_level("INFO", logger="cicaid_devtools.update_issue")

    assert main(["367"]) == 0
    assert calls == []
    assert "nothing to update" in caplog.text


def test_main_noop_when_only_trailing_newline_differs(tmp_path, monkeypatch, caplog):
    """A GitHub body with a trailing newline vs. a stripped local body is not a
    real change -- don't offer a pointless push."""
    path = tmp_path / ".issue-367.md"
    path.write_text("Same title\n\nSame body", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    calls = _patch_github(monkeypatch, _issue(title="Same title", body="Same body\n"))
    caplog.set_level("INFO", logger="cicaid_devtools.update_issue")

    assert main(["367"]) == 0
    assert calls == []
    assert "nothing to update" in caplog.text


def test_main_dry_run_title_change_does_not_print_empty_body_header(
    tmp_path, monkeypatch, capsys
):
    """When only the title changes, don't print a body-diff header with no lines."""
    _write_issue_file(tmp_path, 367, "New title", "Same body")
    monkeypatch.chdir(tmp_path)
    calls = _patch_github(monkeypatch, _issue(title="Old title", body="Same body\n"))

    assert main(["367", "--dry-run"]) == 0
    assert calls == []
    out = capsys.readouterr().out
    assert "Title: 'Old title' -> 'New title'" in out
    assert "Body diff (GitHub -> local):" not in out


def test_main_dry_run_shows_diff_without_pushing(tmp_path, monkeypatch, capsys):
    _write_issue_file(tmp_path, 367, "New title", "## What\n\nNew body")
    monkeypatch.chdir(tmp_path)
    calls = _patch_github(monkeypatch, _issue())
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    assert main(["367", "--dry-run"]) == 0
    assert calls == []
    out = capsys.readouterr().out
    assert "Title: 'Old title' -> 'New title'" in out
    assert "Body diff (GitHub -> local):" in out


def test_main_missing_file_errors(tmp_path, monkeypatch, caplog):
    monkeypatch.chdir(tmp_path)
    calls = _patch_github(monkeypatch, _issue())
    caplog.set_level("ERROR", logger="cicaid_devtools.update_issue")

    assert main(["367"]) == 1
    assert calls == []
    assert "Issue file not found: .issue-367.md" in caplog.text


def test_main_file_without_title_errors(tmp_path, monkeypatch, caplog):
    path = tmp_path / ".issue-367.md"
    path.write_text("\n\n\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    calls = _patch_github(monkeypatch, _issue())
    caplog.set_level("ERROR", logger="cicaid_devtools.update_issue")

    assert main(["367"]) == 1
    assert calls == []
    assert "does not start with an issue title" in caplog.text


def test_main_repo_lookup_failure(tmp_path, monkeypatch, caplog):
    _write_issue_file(tmp_path, 367, "New title", "New body")
    monkeypatch.chdir(tmp_path)

    def fail_repo_info():
        raise ValueError("no origin remote")

    monkeypatch.setattr("cicaid_devtools.update_issue.get_repo_info", fail_repo_info)
    caplog.set_level("ERROR", logger="cicaid_devtools.update_issue")

    assert main(["367"]) == 1
    assert "no origin remote" in caplog.text


def test_main_fetch_failure(tmp_path, monkeypatch, caplog):
    _write_issue_file(tmp_path, 367, "New title", "New body")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "cicaid_devtools.update_issue.get_repo_info", lambda: (OWNER, REPO_NAME)
    )

    def fail_get_issue(repo, number):
        raise github_issues.GitHubIssuesError("gh issue view #367 failed")

    monkeypatch.setattr("cicaid_devtools.update_issue.get_issue", fail_get_issue)
    caplog.set_level("ERROR", logger="cicaid_devtools.update_issue")

    assert main(["367"]) == 1
    assert "Failed to fetch issue #367" in caplog.text


def test_main_push_failure(tmp_path, monkeypatch, caplog):
    _write_issue_file(tmp_path, 367, "New title", "New body")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "cicaid_devtools.update_issue.get_repo_info", lambda: (OWNER, REPO_NAME)
    )
    monkeypatch.setattr("cicaid_devtools.update_issue.get_issue", lambda repo, number: _issue())
    monkeypatch.setattr("cicaid_devtools.update_issue.update_issue", lambda *a, **k: False)
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    assert main(["367"]) == 1
