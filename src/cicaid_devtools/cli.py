"""Umbrella CLI: `cicaid <command> [args...]` dispatches to the same entry points
installed individually (sync-issues, work-on-issue, ...) so there's one name to
remember instead of fifteen. Run `cicaid` with no arguments, or `cicaid --help`,
to list every command with a one-line description; the individual flat commands
keep working unchanged for anything already scripted against them.
"""

from __future__ import annotations

import importlib
import sys

# (module, one-line description) -- kept in the same order as the README's command
# table so `cicaid --help` and the docs read the same way.
COMMANDS: dict[str, tuple[str, str]] = {
    "sync-issues": ("cicaid_devtools.a_sync_issues", "Sync GitHub issues to local markdown files"),
    "create-issue": ("cicaid_devtools.b_create_issue", "Draft and create a new GitHub issue"),
    "triage-issues": ("cicaid_devtools.c_triage_issues", "Triage unmilestoned open issues"),
    "work-on-issue": ("cicaid_devtools.d_work_on_issue", "Check out a branch for an issue"),
    "work-on-pr": ("cicaid_devtools.e_work_on_pr", "Check out the branch for an open PR"),
    "implement-issue-with-aider": (
        "cicaid_devtools.f_implement_issue_with_aider",
        "Extract an issue prompt for Aider",
    ),
    "run-ci-checks": ("cicaid_devtools.h_run_ci_checks", "Run the local CI check suite"),
    "local-review": ("cicaid_devtools.i_local_review", "LLM-review uncommitted local changes"),
    "pr-review": ("cicaid_devtools.l_pr_review", "LLM-review an open PR"),
    "dependabot-auto-merge": (
        "cicaid_devtools.m_dependabot_auto_merge",
        "Auto-merge green Dependabot PRs",
    ),
    "review-issue": ("cicaid_devtools.o_review_issue", "Refresh a stale issue with an LLM"),
    "add-issue-to-pr": ("cicaid_devtools.p_add_issue_to_pr", "Link an issue to its PR"),
    "clear-ai-slop-issues": (
        "cicaid_devtools.q_clear_ai_slop_issues",
        "Detect and close duplicate/stale/AI-slop issues",
    ),
    "commit-and-push": (
        "cicaid_devtools.lib.commit_and_push",
        "Commit with an LLM-drafted message and push",
    ),
    "publish-pr": ("cicaid_devtools.lib.publish_pr", "Publish a PR from the current branch"),
}

# Numeric shortcut -> command name, derived from COMMANDS insertion order (1-indexed).
NUMERIC_SHORTCUTS: dict[str, str] = {
    str(i): name for i, name in enumerate(COMMANDS, start=1)
}


def print_help() -> None:
    """Print the command list, e.g. for `cicaid` with no arguments."""
    print("Usage: cicaid <command|number> [args...]")
    print("       cicaid sync-issues         (or: cicaid 1) — sync GitHub issues")
    print("       cicaid <command> --help    (that command's full flags)\n")
    print("Commands:")
    width = max(len(name) for name in COMMANDS)
    for i, (name, (_, description)) in enumerate(COMMANDS.items(), start=1):
        label = f"{name} ({i})"
        print(f"  {label.ljust(width + 5)}  {description}")


def main(argv: list[str] | None = None) -> int:
    """Provide the `cicaid` CLI entry point."""
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv or argv[0] in ("-h", "--help", "help"):
        print_help()
        return 0

    command, rest = argv[0], argv[1:]
    # Resolve numeric shortcuts to their corresponding command names.
    if command in NUMERIC_SHORTCUTS:
        command = NUMERIC_SHORTCUTS[command]
    if command not in COMMANDS:
        print(f"Unknown command: {command!r}\n", file=sys.stderr)
        print_help()
        return 1

    module_name, _ = COMMANDS[command]
    module = importlib.import_module(module_name)

    # The target's main() reads sys.argv itself (via argparse.parse_args()) rather
    # than accepting an argv parameter, so swap it in for the dispatch rather than
    # touching all fifteen main() signatures.
    original_argv = sys.argv
    sys.argv = [command, *rest]
    try:
        return module.main() or 0
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    raise SystemExit(main())
