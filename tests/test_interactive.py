from cicaid_devtools.lib import interactive


def test_is_interactive_false_when_env_set(monkeypatch):
    monkeypatch.setenv(interactive.NON_INTERACTIVE_ENV, "1")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    assert interactive.is_interactive() is False


def test_is_interactive_false_when_not_a_tty(monkeypatch):
    monkeypatch.delenv(interactive.NON_INTERACTIVE_ENV, raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    assert interactive.is_interactive() is False


def test_is_interactive_true_when_tty_and_env_unset(monkeypatch):
    monkeypatch.delenv(interactive.NON_INTERACTIVE_ENV, raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    assert interactive.is_interactive() is True


def test_is_interactive_false_when_stdout_piped_by_default(monkeypatch):
    monkeypatch.delenv(interactive.NON_INTERACTIVE_ENV, raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    assert interactive.is_interactive() is False


def test_is_interactive_ignores_piped_stdout_when_not_required(monkeypatch):
    monkeypatch.delenv(interactive.NON_INTERACTIVE_ENV, raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    assert interactive.is_interactive(require_stdout=False) is True
