import sys

import pytest

from cicaid_devtools import cli


def test_every_command_module_and_main_resolve():
    """Guards against a typo'd module path or a target missing main()."""
    import importlib

    for command, (module_name, description) in cli.COMMANDS.items():
        assert description
        module = importlib.import_module(module_name)
        assert callable(module.main), f"{command} -> {module_name}.main is not callable"


def test_no_args_prints_help(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "Usage: cicaid <command>" in out
    assert "sync-issues" in out
    assert "run-ci-checks" in out


@pytest.mark.parametrize("flag", ["-h", "--help", "help"])
def test_help_aliases_print_help(capsys, flag):
    assert cli.main([flag]) == 0
    assert "Usage: cicaid <command>" in capsys.readouterr().out


def test_unknown_command_errors_and_lists_commands(capsys):
    assert cli.main(["not-a-real-command"]) == 1
    captured = capsys.readouterr()
    assert "Unknown command: 'not-a-real-command'" in captured.err
    assert "Usage: cicaid <command>" in captured.out


def test_dispatches_to_target_command_with_remaining_args(monkeypatch):
    calls = []

    class FakeModule:
        @staticmethod
        def main():
            calls.append(list(sys.argv))
            return 0

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: FakeModule)
    assert cli.main(["run-ci-checks", "--list"]) == 0
    assert calls == [["run-ci-checks", "--list"]]


def test_restores_sys_argv_after_dispatch(monkeypatch):
    class FakeModule:
        @staticmethod
        def main():
            return 0

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: FakeModule)
    original = list(sys.argv)
    cli.main(["sync-issues"])
    assert sys.argv == original


def test_restores_sys_argv_even_if_target_raises(monkeypatch):
    class FakeModule:
        @staticmethod
        def main():
            raise RuntimeError("boom")

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: FakeModule)
    original = list(sys.argv)
    with pytest.raises(RuntimeError):
        cli.main(["sync-issues"])
    assert sys.argv == original


def test_none_return_from_target_treated_as_success(monkeypatch):
    class FakeModule:
        @staticmethod
        def main():
            return None

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: FakeModule)
    assert cli.main(["publish-pr"]) == 0
