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
    assert "Usage: cicaid <command|number>" in out
    assert "(or: cicaid 1)" in out
    assert "sync-issues (1)" in out
    assert "run-ci-checks (7)" in out


@pytest.mark.parametrize("flag", ["-h", "--help", "help"])
def test_help_aliases_print_help(capsys, flag):
    assert cli.main([flag]) == 0
    assert "Usage: cicaid <command|number>" in capsys.readouterr().out


def test_unknown_command_errors_and_lists_commands(capsys):
    assert cli.main(["not-a-real-command"]) == 1
    captured = capsys.readouterr()
    assert "Unknown command: 'not-a-real-command'" in captured.err
    assert "Usage: cicaid <command|number>" in captured.out


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


def test_numeric_shortcut_dispatches_to_correct_command(monkeypatch):
    """`cicaid 1` should dispatch to sync-issues, `cicaid 15` to publish-pr."""
    resolved: list[str] = []

    class FakeModule:
        @staticmethod
        def main():
            resolved.append(sys.argv[0])
            return 0

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: FakeModule)

    # First command (sync-issues)
    assert cli.main(["1"]) == 0
    assert resolved[-1] == "sync-issues"

    # Last command (publish-pr)
    assert cli.main(["15"]) == 0
    assert resolved[-1] == "publish-pr"

    # Middle command (run-ci-checks, position 7)
    assert cli.main(["7"]) == 0
    assert resolved[-1] == "run-ci-checks"


def test_numeric_shortcut_passes_remaining_args(monkeypatch):
    calls: list[list[str]] = []

    class FakeModule:
        @staticmethod
        def main():
            calls.append(list(sys.argv))
            return 0

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: FakeModule)
    assert cli.main(["4", "123"]) == 0
    assert calls == [["work-on-issue", "123"]]


def test_numeric_shortcut_help_displays_numbers(capsys):
    """The help output should include numeric shortcuts alongside command names."""
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "Usage: cicaid <command|number>" in out
    assert "(or: cicaid 1)" in out
    assert "sync-issues (1)" in out
    assert "publish-pr (15)" in out


def test_numeric_shortcut_out_of_range_is_unknown(capsys):
    """A number beyond the last command should be treated as unknown."""
    assert cli.main(["99"]) == 1
    captured = capsys.readouterr()
    assert "Unknown command: '99'" in captured.err


def test_numeric_shortcuts_cover_all_commands():
    """Every command should have exactly one numeric shortcut."""
    assert len(cli.NUMERIC_SHORTCUTS) == len(cli.COMMANDS)
    # All shortcuts should be 1..N and map to valid commands.
    for num_str, name in cli.NUMERIC_SHORTCUTS.items():
        assert 1 <= int(num_str) <= len(cli.COMMANDS)
        assert name in cli.COMMANDS
    # Every command should be covered.
    covered = set(cli.NUMERIC_SHORTCUTS.values())
    assert covered == set(cli.COMMANDS)
