import pytest

from cicaid_devtools import work_on_pr


def _sample_prs():
    return [
        {
            "number": 1,
            "title": "A change",
            "head": {"ref": "feature"},
            "user": {"login": "octocat"},
        }
    ]


def test_prompt_for_pr_exits_when_not_interactive(monkeypatch):
    monkeypatch.setattr(work_on_pr, "is_interactive", lambda: False)

    def fail_input(prompt=""):
        raise AssertionError("input() must not be called when not interactive")

    monkeypatch.setattr("builtins.input", fail_input)

    with pytest.raises(SystemExit) as exc_info:
        work_on_pr.prompt_for_pr(_sample_prs())
    assert exc_info.value.code == 1


def test_prompt_for_pr_prompts_when_interactive(monkeypatch):
    monkeypatch.setattr(work_on_pr, "is_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "1")

    prs = _sample_prs()
    assert work_on_pr.prompt_for_pr(prs) == prs[0]
