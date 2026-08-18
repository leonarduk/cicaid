import sys

import pytest

from cicaid_devtools import cli


def test_every_command_module_and_main_resolve():
    """Guards against a typo'd module path or a target missing main(), for
    every command this package ships."""
    import importlib

    for command, (module_name, description) in cli.COMMANDS.items():
        assert description
        module = importlib.import_module(module_name)
        assert callable(module.main), f"{command} -> {module_name}.main is not callable"


def test_discover_commands_with_nothing_installed_matches_own_commands():
    """In this package's own test env (no extension installed), discovery
    returns exactly this package's own commands -- no cicaid-pro commands
    leak in just because their names are known elsewhere in the codebase."""
    assert cli.discover_commands() == cli.COMMANDS


def test_discover_commands_merges_installed_extensions(monkeypatch):
    """Commands an installed extension registers under the "cicaid.commands"
    entry-point group are merged in -- this package never hardcodes an
    extension's command names. Description extraction is covered separately
    by the _describe tests below."""

    class FakeEntryPoint:
        name = "fake-command"
        value = "fake_extension_module:main"

    def fake_entry_points(*, group):
        assert group == cli.ENTRY_POINT_GROUP
        return [FakeEntryPoint()]

    monkeypatch.setattr(cli.importlib.metadata, "entry_points", fake_entry_points)
    monkeypatch.setattr(cli, "_describe", lambda module_name: f"described {module_name}")

    commands = cli.discover_commands()
    assert commands["fake-command"] == ("fake_extension_module", "described fake_extension_module")
    assert commands["sync-issues"] == cli.COMMANDS["sync-issues"]


def test_describe_reads_docstring_without_executing_module(tmp_path, monkeypatch):
    """_describe must not execute the target module -- some command modules
    do real work (e.g. a live git-remote lookup) at import time, which must
    not happen just from building the help menu."""
    module_path = tmp_path / "side_effecting_module.py"
    module_path.write_text(
        '"""Do a risky thing.\n\nMore details.\n"""\n\nraise RuntimeError("should never execute")\n',
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    assert cli._describe("side_effecting_module") == "Do a risky thing"


def test_describe_returns_empty_for_missing_module():
    assert cli._describe("no_such_module_at_all_xyz") == ""


def test_discover_commands_own_commands_win_on_name_collision(monkeypatch):
    """An extension registering a name that collides with this package's own
    command is ignored -- this package's own commands always take precedence."""

    class FakeEntryPoint:
        name = "sync-issues"
        value = "some_other_module:main"

    monkeypatch.setattr(
        cli.importlib.metadata, "entry_points", lambda *, group: [FakeEntryPoint()]
    )
    assert cli.discover_commands()["sync-issues"] == cli.COMMANDS["sync-issues"]


def test_no_args_prints_help(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "Usage: cicaid <command|number>" in out
    assert "(or: cicaid 1)" in out
    assert "sync-issues (1)" in out
    assert "update-issue (8)" in out


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
    assert cli.main(["help", "sync-issues"]) == 0
    assert calls == [["sync-issues", "--help"]]


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
    assert "extension package" in captured.err


def test_help_rejects_extra_arguments(capsys):
    assert cli.main(["help", "sync-issues", "extra"]) == 1
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
    """`cicaid 1` should dispatch to sync-issues, `cicaid 8` to update-issue."""
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

    # Last command (update-issue)
    assert cli.main(["8"]) == 0
    assert resolved[-1] == "update-issue"
    assert "Running: cicaid update-issue" in capsys.readouterr().out

    # Middle command (run-ci-checks, position 4)
    assert cli.main(["4"]) == 0
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
    assert cli.main(["2", "123"]) == 0
    assert calls == [["work-on-issue", "123"]]
    assert "Running: cicaid work-on-issue" in capsys.readouterr().out


def test_numeric_shortcut_help_displays_numbers(capsys):
    """The help output should include numeric shortcuts alongside command names."""
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "Usage: cicaid <command|number>" in out
    assert "(or: cicaid 1)" in out
    assert "sync-issues (1)" in out
    assert "publish-pr (5)" in out


def test_numeric_shortcut_out_of_range_is_unknown(capsys):
    """A number beyond the last command should be treated as unknown."""
    assert cli.main(["99"]) == 1
    captured = capsys.readouterr()
    assert "Unknown command: '99'" in captured.err


def test_numeric_shortcuts_cover_all_commands():
    """Every command should have exactly one numeric shortcut."""
    commands = cli.discover_commands()
    shortcuts = cli._numeric_shortcuts(commands)
    assert len(shortcuts) == len(commands)
    # All shortcuts should be 1..N and map to valid commands.
    for num_str, name in shortcuts.items():
        assert 1 <= int(num_str) <= len(commands)
        assert name in commands
    # Every command should be covered.
    covered = set(shortcuts.values())
    assert covered == set(commands)


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
