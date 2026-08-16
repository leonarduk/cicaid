"""Extract the issue number a PR closes from its title/body text.

Only closing keywords (``Closes``/``Fixes``) count. A contextual ``Refs #N``
reference must NOT be treated as the linked issue, otherwise the AI reviewer
evaluates the diff against the wrong issue's acceptance criteria and rejects
correct work (issue #409).

Used by the ``Get linked issue body`` step of ``_ai-pr-review.yml`` (both the
checked-in workflow and the template ``setup_review_actions.py`` installs into
downstream repos), so the extraction logic lives in one testable place instead
of duplicated bash greps.
"""

from __future__ import annotations

import argparse
import re
import sys

# Priority order matters: a body may reference several issues, and the PR's
# closing directive is the one to review against. Matches the priority order of
# pr_review.py's extract_issue_body (Closes before Fixes).
_CLOSING_PATTERNS = [
    r"Closes\s+#(\d+)",
    r"Fixes\s+#(\d+)",
]


def extract_linked_issue_number(text: str) -> int | None:
    """Return the issue number a PR body/title closes, or ``None``.

    ``Closes`` wins over ``Fixes`` when both appear (first closing keyword in
    priority order, not body position). ``Refs``/``Relates to`` references are
    deliberately ignored.
    """
    for pattern in _CLOSING_PATTERNS:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def main(argv: list[str] | None = None) -> int:
    """Print the linked issue number read from stdin (or an argument), else nothing."""
    parser = argparse.ArgumentParser(
        description="Print the issue number a PR closes; empty output means none.",
    )
    parser.add_argument("text", nargs="?", help="Text to search; when omitted, stdin is read.")
    args = parser.parse_args(argv)

    text = args.text if args.text is not None else sys.stdin.read()
    issue_number = extract_linked_issue_number(text)
    if issue_number is not None:
        print(issue_number)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
