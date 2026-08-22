"""Shared helper for detecting whether a command may prompt the user.

Several commands (work-on-pr, run-ci-checks, update-issue, the version-update
check) each grew their own ad-hoc guard around ``input()`` -- an isatty check,
a skip-env-var check, or both, with no single switch an AI driver can set.
``is_interactive`` centralizes that check: an agent (Claude Code, aider, ...)
sets ``CICAID_NON_INTERACTIVE`` once and every command that consults this
helper stops prompting, in addition to the existing per-command flags.
"""

from __future__ import annotations

import os
import sys

NON_INTERACTIVE_ENV = "CICAID_NON_INTERACTIVE"


def is_interactive() -> bool:
    """Return False if prompting should be skipped.

    True only when ``CICAID_NON_INTERACTIVE`` is unset/falsy AND both stdin
    and stdout are attached to a TTY.
    """
    if os.environ.get(NON_INTERACTIVE_ENV):
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()
