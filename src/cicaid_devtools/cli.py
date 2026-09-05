"""Umbrella CLI: `cicaid <command> [args...]` dispatches to the same entry points
installed individually (sync-issues, work-on-issue, ...) so there's one name to
remember instead of seventeen. Run `cicaid` with no arguments, or `cicaid --help`,
to list every command with a one-line description; the individual flat commands
keep working unchanged for anything already scripted against them.

Extensions (e.g. cicaid-pro, the private LLM-backed command package) register
their own commands under the "cicaid.commands" entry-point group in their own
package metadata, discovered at runtime -- this package never hardcodes what
an extension provides, so it never needs updating (or a new release) just
because an extension added a command.
"""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import importlib.util
import sys
import webbrowser
from pathlib import Path

from cicaid_devtools.version_checker import check_and_prompt

ENTRY_POINT_GROUP = "cicaid.commands"
WIKI_URL = "https://github.com/leonarduk/cicaid/wiki"

# This package's own commands -- always available regardless of what
# extensions are installed. Kept in the same order as the README's command
# table so `cicaid --help` and the docs read the same way.
COMMANDS: dict[str, tuple[str, str]] = {
    "sync-issues": ("cicaid_devtools.sync_issues", "Sync GitHub issues to local markdown files"),
    "work-on-issue": ("cicaid_devtools.work_on_issue", "Check out a branch for an issue"),
    "work-on-pr": ("cicaid_devtools.work_on_pr", "Check out the branch for an open PR"),
    "run-ci-checks": ("cicaid_devtools.run_ci_checks", "Run the local CI check suite"),
    "publish-pr": ("cicaid_devtools.lib.publish_pr", "Publish a PR from the current branch"),
    "add-issue-to-pr": ("cicaid_devtools.add_issue_to_pr", "Link an issue to its PR"),
    "dependabot-auto-merge": (
        "cicaid_devtools.dependabot_auto_merge",
        "Auto-merge green Dependabot PRs",
    ),
    "update-issue": (
        "cicaid_devtools.update_issue",
        "Update a GitHub issue from a changed .issue-<id>.md file",
    ),
    "update-prs": (
        "cicaid_devtools.update_prs",
        "Update open PRs that are behind their base branch",
    ),
    "graphify-repos": (
        "cicaid_devtools.graphify_repos",
        "Run graphify across a configured list of repos",
    ),
    "merge-pr": ("cicaid_devtools.merge_pr", "Merge an open PR"),
}

# Groups this package's own commands for `cicaid --help` -- purely a display
# aid (numeric shortcuts and dispatch still key off COMMANDS' flat insertion
# order, unaffected by this). Any command not listed here (currently none of
# this package's own, but always true of extension commands) falls into a
# trailing "Extensions"/"Other" section in print_help.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "Issues": ("sync-issues", "work-on-issue", "update-issue"),
    "Pull requests": (
        "work-on-pr",
        "publish-pr",
        "add-issue-to-pr",
        "dependabot-auto-merge",
        "update-prs",
        "merge-pr",
    ),
    "CI & repo tooling": ("run-ci-checks", "graphify-repos"),
}


def _describe(module_name: str) -> str:
    """First line of ``module_name``'s docstring, read without executing it.

    Some command modules do real work at import time (e.g. a live git-remote
    lookup) -- building the help menu must not trigger that, so the source is
    parsed with ``ast`` instead of actually importing the module.
    """
    try:
        spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError):
        return ""
    if spec is None or spec.origin is None:
        return ""
    try:
        source = Path(spec.origin).read_text(encoding="utf-8")
        doc = ast.get_docstring(ast.parse(source, filename=spec.origin))
    except (OSError, SyntaxError):
        return ""
    if not doc:
        return ""
    # Match this package's own descriptions, which are terse phrases with no
    # trailing period.
    return doc.strip().splitlines()[0].rstrip(".")


def discover_commands() -> dict[str, tuple[str, str]]:
    """This package's own commands, plus any installed extension's.

    Extensions register commands under the "cicaid.commands" entry-point
    group in their own package metadata (see cicaid-pro's pyproject.toml for
    an example) -- only commands from packages actually installed right now
    show up here, and this package's own commands take precedence on a name
    collision.
    """
    commands = dict(COMMANDS)
    for entry_point in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
        if entry_point.name in commands:
            continue
        module_name = entry_point.value.split(":", 1)[0]
        commands[entry_point.name] = (module_name, _describe(module_name))
    return commands


def _extension_distributions() -> dict[str, str]:
    """Command name -> providing distribution name, for non-COMMANDS entries.

    Derived from entry-point metadata rather than a hardcoded pro-command
    list, so this stays correct however many extension packages are
    installed and whatever commands they register.
    """
    extensions = {}
    for entry_point in importlib.metadata.entry_points(group=ENTRY_POINT_GROUP):
        if entry_point.name in COMMANDS:
            continue
        dist = getattr(entry_point, "dist", None)
        dist_name = dist.name if dist else "an extension"
        extensions[entry_point.name] = dist_name
    return extensions


def _numeric_shortcuts(commands: dict[str, tuple[str, str]]) -> dict[str, str]:
    """Numeric shortcut -> command name, derived from insertion order (1-indexed)."""
    return {str(i): name for i, name in enumerate(commands, start=1)}


# Words that merely join parts of a command name (commit-and-push, work-on-issue)
# rather than naming something, dropped when deriving abbreviations so the
# abbreviation reads as the command's actual content words. Extension commands
# are discovered at runtime, so this list is the only place abbreviations are
# "configured"; everything else derives from each command name itself.
_CONNECTOR_WORDS = frozenset(
    {"and", "or", "with", "to", "from", "on", "by", "of", "for", "in", "at"}
)


def _command_signature(name: str) -> str:
    """Meaningful-word initials of a command name, e.g. ``commit-and-push`` -> ``cp``.

    Connector words (``and``, ``on``, ``with``, ...) are skipped so the
    abbreviation comes from the command's real content words (never ``ca`` for
    commit-and-push). A name left with a single content word falls back to its
    first two letters.
    """
    words = [word for word in name.split("-") if word not in _CONNECTOR_WORDS]
    if not words:
        return ""
    if len(words) == 1:
        return words[0][:2]
    return "".join(word[0] for word in words)


def _abbreviations(commands: dict[str, tuple[str, str]]) -> dict[str, str]:
    """Unique abbreviation -> command name, derived from each command's name.

    Abbreviations start as the first two characters of a command's
    meaningful-word signature and are extended one character at a time when
    that would collide with an already-assigned abbreviation, so no two
    commands ever share one. A command whose signature runs out without
    finding a free abbreviation (e.g. two names with identical content-word
    initials) gets none and stays callable by full name or number. Commands
    earlier in ``commands`` (this package's own) win shorter abbreviations
    over later extension commands.
    """
    abbreviations: dict[str, str] = {}
    for name in commands:
        signature = _command_signature(name)
        for length in range(2, len(signature) + 1):
            candidate = signature[:length]
            if candidate not in abbreviations:
                abbreviations[candidate] = name
                break
    return abbreviations


def print_help(commands: dict[str, tuple[str, str]]) -> None:
    """Print the command list, e.g. for `cicaid` with no arguments.

    Commands are grouped by category (see CATEGORIES) so the list reads as a
    map of what's available rather than one flat, arbitrarily-ordered block.
    Each command shows its unique two-letter abbreviation when it has one.
    Numeric shortcuts still dispatch (legacy convenience) but are no longer
    listed here.
    """
    extension_dists = _extension_distributions()
    command_abbreviations = {name: abbr for abbr, name in _abbreviations(commands).items()}
    print("Usage: cicaid <command|abbreviation> [args...]")
    print("       cicaid help <command|abbreviation>  (detailed command help)")
    print("       cicaid sync-issues         (or: cicaid si) — sync GitHub issues")
    print("       cicaid <command> --help    (that command's full flags)")

    width = max(len(name) for name in commands)

    def print_command(name: str) -> None:
        _, description = commands[name]
        abbreviation = command_abbreviations.get(name)
        label = f"{name} ({abbreviation})" if abbreviation else name
        suffix = f" [{extension_dists[name]}]" if name in extension_dists else ""
        print(f"  {label.ljust(width + 5)}  {description}{suffix}")

    categorized: set[str] = set()
    for category, names in CATEGORIES.items():
        present = [name for name in names if name in commands]
        if not present:
            continue
        categorized.update(present)
        print(f"\n{category}:")
        for name in present:
            print_command(name)

    leftover = [name for name in commands if name not in categorized]
    if leftover:
        heading = "Extensions" if extension_dists else "Other"
        print(f"\n{heading}:")
        for name in leftover:
            print_command(name)

    if not extension_dists:
        print(
            "\ncicaid-pro adds LLM-backed commands (issue triage, PR review, "
            "AI-assisted issue creation, ...) -- see "
            "https://github.com/leonarduk/cicaid-pro"
        )
    print(f"\nFull docs: {WIKI_URL}")


def _offer_to_open_wiki() -> None:
    """Ask to open the GitHub wiki in a browser; a silent no-op off a real TTY.

    Only called from an explicit `cicaid help` (not the bare `cicaid` or
    `--help`/`-h` banner), so it doesn't intrude on scripted/non-interactive
    use -- and stdin not being a TTY (piped input, CI, tests) skips the
    prompt entirely rather than blocking on it.
    """
    if not sys.stdin.isatty():
        return
    try:
        choice = input("\nOpen full docs in your browser? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return
    if choice in ("y", "yes"):
        webbrowser.open(WIKI_URL)


def _resolve_command(command: str, shortcuts: dict[str, str]) -> str:
    """Resolve a command name or its numeric/abbreviation shortcut."""
    return shortcuts.get(command, command)


_UNKNOWN_COMMAND_SUFFIX = "an installed extension package (e.g. cicaid-pro) may provide it"


def _dispatch(command: str, args: list[str], commands: dict[str, tuple[str, str]]) -> int:
    """Run a command with ``args``, restoring the caller's ``sys.argv``."""
    module_name, _ = commands[command]
    module = importlib.import_module(module_name)

    # The targets generally read sys.argv themselves (via argparse.parse_args()).
    original_argv = sys.argv
    sys.argv = [command, *args]
    try:
        try:
            return module.main() or 0
        except SystemExit as exc:
            # argparse implements --help by raising SystemExit(0).  Turn that into
            # the normal main() return value for callers of cli.main(), while not
            # masking parser errors or exits from ordinary command execution.
            if ("--help" in args or "-h" in args) and exc.code in (None, 0):
                return 0
            raise
    finally:
        sys.argv = original_argv


def main(argv: list[str] | None = None) -> int:
    """Provide the `cicaid` CLI entry point."""
    argv = list(sys.argv[1:] if argv is None else argv)

    check_and_prompt()

    commands = discover_commands()
    # Abbreviations and numbers both resolve to command names; full names pass
    # through unchanged. Keys can't collide (letters vs. digits). Numbers stay
    # dispatchable as a legacy convenience but are no longer shown in the menu.
    shortcuts = {**_numeric_shortcuts(commands), **_abbreviations(commands)}

    if not argv or argv[0] in ("-h", "--help"):
        print_help(commands)
        return 0

    if argv[0] == "help":
        if len(argv) == 1:
            print_help(commands)
            _offer_to_open_wiki()
            return 0
        if len(argv) > 2:
            print("Usage: cicaid help <command|abbreviation>", file=sys.stderr)
            return 1

        command = _resolve_command(argv[1], shortcuts)
        if command not in commands:
            print(
                f"Unknown command: {argv[1]!r} -- {_UNKNOWN_COMMAND_SUFFIX}.\n",
                file=sys.stderr,
            )
            print_help(commands)
            return 1
        return _dispatch(command, ["--help"], commands)

    command, rest = argv[0], argv[1:]
    # Resolve numeric/abbreviation shortcuts to their corresponding command names.
    if command in shortcuts:
        command = _resolve_command(command, shortcuts)
        print(f"Running: cicaid {command}")
    if command not in commands:
        print(
            f"Unknown command: {command!r} -- {_UNKNOWN_COMMAND_SUFFIX}.\n",
            file=sys.stderr,
        )
        print_help(commands)
        return 1

    return _dispatch(command, rest, commands)


if __name__ == "__main__":
    raise SystemExit(main())
