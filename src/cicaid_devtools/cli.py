"""Umbrella CLI: `cicaid <command> [args...]` dispatches to the same entry points
installed individually (sync-issues, work-on-issue, ...) so there's one name to
remember instead of seventeen. Run `cicaid` with no arguments, or `cicaid --help`,
to list every command with a one-line description; the individual flat commands
keep working unchanged for anything already scripted against them.
"""

from __future__ import annotations

import importlib
import sys

from cicaid_devtools.version_checker import check_and_prompt

# (module, one-line description) -- kept in the same order as the README's command
# table so `cicaid --help` and the docs read the same way.
COMMANDS: dict[str, tuple[str, str]] = {
    "sync-issues": ("cicaid_devtools.sync_issues", "Sync GitHub issues to local markdown files"),
    "triage-issues": ("cicaid_devtools.triage_issues", "Triage unmilestoned open issues"),
    "clear-ai-slop-issues": (
        "cicaid_devtools.clear_ai_slop_issues",
        "Detect and close duplicate/stale/AI-slop issues",
    ),
    "review-issue": ("cicaid_devtools.review_issue", "Refresh a stale issue with an LLM"),
    "create-issue": ("cicaid_devtools.create_issue", "Draft and create a new GitHub issue"),
    "work-on-issue": ("cicaid_devtools.work_on_issue", "Check out a branch for an issue"),
    "implement-issue-with-aider": (
        "cicaid_devtools.implement_issue_with_aider",
        "Extract an issue prompt for Aider",
    ),
    "work-on-pr": ("cicaid_devtools.work_on_pr", "Check out the branch for an open PR"),
    "run-ci-checks": ("cicaid_devtools.run_ci_checks", "Run the local CI check suite"),
    "local-review": ("cicaid_devtools.local_review", "LLM-review uncommitted local changes"),
    "commit-and-push": (
        "cicaid_devtools.lib.commit_and_push",
        "Commit with an LLM-drafted message and push",
    ),
    "publish-pr": ("cicaid_devtools.lib.publish_pr", "Publish a PR from the current branch"),
    "pr-review": ("cicaid_devtools.pr_review", "LLM-review an open PR"),
    "add-issue-to-pr": ("cicaid_devtools.add_issue_to_pr", "Link an issue to its PR"),
    "dependabot-auto-merge": (
        "cicaid_devtools.dependabot_auto_merge",
        "Auto-merge green Dependabot PRs",
    ),
    "setup-review-actions": (
        "cicaid_devtools.setup_review_actions",
        "Scaffold AI review GitHub Actions into a repo (branch + PR + issue)",
    ),
    "update-issue": (
        "cicaid_devtools.update_issue",
        "Update a GitHub issue from a changed .issue-<id>.md file",
    ),
}

# Numeric shortcut -> command name, derived from COMMANDS insertion order (1-indexed).
NUMERIC_SHORTCUTS: dict[str, str] = {
    str(i): name for i, name in enumerate(COMMANDS, start=1)
}


def print_help() -> None:
    """Print the command list, e.g. for `cicaid` with no arguments."""
    print("Usage: cicaid <command|number> [args...]")
    print("       cicaid help <command|number>  (detailed command help)")
    print("       cicaid sync-issues         (or: cicaid 1) — sync GitHub issues")
    print("       cicaid <command> --help    (that command's full flags)\n")
    print("Commands:")
    width = max(len(name) for name in COMMANDS)
    for i, (name, (_, description)) in enumerate(COMMANDS.items(), start=1):
        label = f"{name} ({i})"
        print(f"  {label.ljust(width + 5)}  {description}")


def _resolve_command(command: str) -> str:
    """Resolve a command name or its numeric shortcut."""
    return NUMERIC_SHORTCUTS.get(command, command)


_CORE_MISSING_MESSAGE = (
    "✗ `cicaid {command}` is part of cicaid-core (the LLM review/triage "
    "engine), a private package not installed here — see "
    "https://github.com/leonarduk/cicaid-core for access."
)


def _dispatch(command: str, args: list[str]) -> int:
    """Run a command with ``args``, restoring the caller's ``sys.argv``."""
    module_name, _ = COMMANDS[command]
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        # Only swallow "this specific command's module doesn't exist" (the
        # free shell doesn't ship cicaid-core's LLM-backed commands) — a
        # missing transitive dependency inside a module that DID import must
        # still surface as a real error, not this friendly message.
        if exc.name == module_name:
            print(_CORE_MISSING_MESSAGE.format(command=command), file=sys.stderr)
            return 2
        raise

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

    if not argv or argv[0] in ("-h", "--help"):
        print_help()
        return 0

    if argv[0] == "help":
        if len(argv) == 1:
            print_help()
            return 0
        if len(argv) > 2:
            print("Usage: cicaid help <command|number>", file=sys.stderr)
            return 1

        command = _resolve_command(argv[1])
        if command not in COMMANDS:
            print(f"Unknown command: {argv[1]!r}\n", file=sys.stderr)
            print_help()
            return 1
        return _dispatch(command, ["--help"])

    command, rest = argv[0], argv[1:]
    # Resolve numeric shortcuts to their corresponding command names.
    if command in NUMERIC_SHORTCUTS:
        command = _resolve_command(command)
        print(f"Running: cicaid {command}")
    if command not in COMMANDS:
        print(f"Unknown command: {command!r}\n", file=sys.stderr)
        print_help()
        return 1

    return _dispatch(command, rest)


if __name__ == "__main__":
    raise SystemExit(main())
