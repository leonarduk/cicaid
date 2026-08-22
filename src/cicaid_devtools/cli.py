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
from pathlib import Path

from cicaid_devtools.version_checker import check_and_prompt

ENTRY_POINT_GROUP = "cicaid.commands"

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


def print_help(commands: dict[str, tuple[str, str]]) -> None:
    """Print the command list, e.g. for `cicaid` with no arguments."""
    extension_dists = _extension_distributions()
    print("Usage: cicaid <command|number> [args...]")
    print("       cicaid help <command|number>  (detailed command help)")
    print("       cicaid sync-issues         (or: cicaid 1) — sync GitHub issues")
    print("       cicaid <command> --help    (that command's full flags)\n")
    print("Commands:")
    width = max(len(name) for name in commands)
    for i, (name, (_, description)) in enumerate(commands.items(), start=1):
        label = f"{name} ({i})"
        suffix = f" [{extension_dists[name]}]" if name in extension_dists else ""
        print(f"  {label.ljust(width + 5)}  {description}{suffix}")
    if not extension_dists:
        print(
            "\ncicaid-pro adds LLM-backed commands (issue triage, PR review, "
            "AI-assisted issue creation, ...) -- see "
            "https://github.com/leonarduk/cicaid-pro"
        )


def _resolve_command(command: str, numeric_shortcuts: dict[str, str]) -> str:
    """Resolve a command name or its numeric shortcut."""
    return numeric_shortcuts.get(command, command)


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
    numeric_shortcuts = _numeric_shortcuts(commands)

    if not argv or argv[0] in ("-h", "--help"):
        print_help(commands)
        return 0

    if argv[0] == "help":
        if len(argv) == 1:
            print_help(commands)
            return 0
        if len(argv) > 2:
            print("Usage: cicaid help <command|number>", file=sys.stderr)
            return 1

        command = _resolve_command(argv[1], numeric_shortcuts)
        if command not in commands:
            print(
                f"Unknown command: {argv[1]!r} -- {_UNKNOWN_COMMAND_SUFFIX}.\n",
                file=sys.stderr,
            )
            print_help(commands)
            return 1
        return _dispatch(command, ["--help"], commands)

    command, rest = argv[0], argv[1:]
    # Resolve numeric shortcuts to their corresponding command names.
    if command in numeric_shortcuts:
        command = _resolve_command(command, numeric_shortcuts)
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
