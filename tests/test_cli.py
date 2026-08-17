import sys

import pytest

from cicaid_devtools import cli


# Commands whose module ships in this (free-shell) package. The rest are
# part of the private cicaid-pro package and are expected to fail import —
# see test_pro_only_commands_report_unavailable below.
_LOCAL_COMMANDS = {
    "sync-issues",
    "work-on-issue",
    "work-on-pr",
    "run-ci-checks",
    "publish-pr",
    "add-issue-to-pr",
    "dependabot-auto-merge",
    "setup-review-actions",
    "update-issue",
}


def test_every_local_command_module_and_main_resolve():
    """Guards against a typo'd module path or a target missing main(), for
    every command this package actually ships."""
    import importlib

    for command, (module_name, description) in cli.COMMANDS.items():
        assert description
        if command not in _LOCAL_COMMANDS:
            continue
        module = importlib.import_module(module_name)
        assert callable(module.main), f"{command} -> {module_name}.main is not callable"


@pytest.mark.parametrize(
    "command", [c for c in cli.COMMANDS if c not in _LOCAL_COMMANDS]
)
def test_pro_only_commands_report_unavailable(command, capsys):
    """A cicaid-pro command run without cicaid-pro installed reports a
    clear pointer instead of a raw ModuleNotFoundError traceback."""
    assert cli.main([command]) == 2
    captured = capsys.readouterr()
    assert "cicaid-pro" in captured.err
    assert command in captured.err


def test_no_args_prints_help(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "Usage: cicaid <command|number>" in out
    assert "(or: cicaid 1)" in out
    assert "sync-issues (1)" in out
    assert "run-ci-checks (9)" in out


@pytest.mark.parametrize("flag", ["-h", "--help", "help"])
def test_help_aliases_print_help(capsys, flag):
    assert cli.main([flag]) == 0
    assert "Usage: cicaid <command|number>" in capsys.readouterr().out


def test_help_command_dispatches_target_help(monkeypatch):
    calls = []

    class FakeModule:
        @staticmethod
        def main():
            calls.append(list(sys.argv))
            raise SystemExit(0)

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: FakeModule)
    assert cli.main(["help", "create-issue"]) == 0
    assert calls == [["create-issue", "--help"]]


def test_help_command_accepts_numeric_shortcut(monkeypatch):
    calls = []

    class FakeModule:
        @staticmethod
        def main():
            calls.append(list(sys.argv))
            return 0

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: FakeModule)
    assert cli.main(["help", "1"]) == 0
    assert calls == [["sync-issues", "--help"]]


def test_help_unknown_command_errors(capsys):
    assert cli.main(["help", "not-a-real-command"]) == 1
    captured = capsys.readouterr()
    assert "Unknown command: 'not-a-real-command'" in captured.err


def test_help_rejects_extra_arguments(capsys):
    assert cli.main(["help", "create-issue", "extra"]) == 1
    assert "Usage: cicaid help <command|number>" in capsys.readouterr().err


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


def test_numeric_shortcut_dispatches_to_correct_command(monkeypatch, capsys):
    """`cicaid 1` should dispatch to sync-issues, `cicaid 15` to dependabot-auto-merge."""
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
    assert "Running: cicaid sync-issues" in capsys.readouterr().out

    # Last command (dependabot-auto-merge)
    assert cli.main(["15"]) == 0
    assert resolved[-1] == "dependabot-auto-merge"
    assert "Running: cicaid dependabot-auto-merge" in capsys.readouterr().out

    # Middle command (run-ci-checks, position 9)
    assert cli.main(["9"]) == 0
    assert resolved[-1] == "run-ci-checks"
    assert "Running: cicaid run-ci-checks" in capsys.readouterr().out


def test_numeric_shortcut_passes_remaining_args(monkeypatch, capsys):
    calls: list[list[str]] = []

    class FakeModule:
        @staticmethod
        def main():
            calls.append(list(sys.argv))
            return 0

    monkeypatch.setattr(cli.importlib, "import_module", lambda name: FakeModule)
    assert cli.main(["6", "123"]) == 0
    assert calls == [["work-on-issue", "123"]]
    assert "Running: cicaid work-on-issue" in capsys.readouterr().out


def test_numeric_shortcut_help_displays_numbers(capsys):
    """The help output should include numeric shortcuts alongside command names."""
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "Usage: cicaid <command|number>" in out
    assert "(or: cicaid 1)" in out
    assert "sync-issues (1)" in out
    assert "publish-pr (12)" in out


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


@pytest.mark.parametrize("command", ["sync-issues"])
def test_help_command_shows_real_module_help(capsys, command):
    """`cicaid help <command>` against the real module (not a fake) exits 0 and
    prints argparse usage rather than starting the interactive workflow."""
    assert cli.main(["help", command]) == 0
    assert "usage:" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["sync-issues"])
def test_help_command_shows_meaningful_parameter_info(capsys, command):
    """`cicaid help <command>` must explain how the command actually behaves
    (it takes no flags, so the usage/parameter info lives in the epilog), not
    just show a bare `usage: <name> [-h]` line."""
    assert cli.main(["help", command]) == 0
    output = capsys.readouterr().out
    assert "GITHUB_TOKEN" in output
    assert "no flags" in output


@pytest.mark.parametrize("command", ["sync-issues"])
def test_real_module_still_accepts_unknown_args(monkeypatch, command):
    """Adding an argparse parser for --help support must not start rejecting
    arguments the command previously ignored (it never read sys.argv)."""
    module_name, _ = cli.COMMANDS[command]
    import importlib

    module = importlib.import_module(module_name)
    monkeypatch.setattr(sys, "argv", [command, "--some-legacy-flag"])

    def fake_get_github_token():
        raise SystemExit(1)

    monkeypatch.setattr(module, "get_github_token", fake_get_github_token)

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    # A SystemExit(1) here means execution reached get_github_token(); argparse
    # would instead raise SystemExit(2) ("unrecognized arguments") before that.
    assert exc_info.value.code == 1
