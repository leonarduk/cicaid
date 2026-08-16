"""Unit tests for linked-issue extraction (issue #409).

A PR body may mention several issues; only the closing reference (Closes/Fixes)
is the issue the AI reviewer should evaluate against. A contextual ``Refs #N``
must not be treated as the linked issue.
"""

from __future__ import annotations

from cicaid_devtools.lib.linked_issue import extract_linked_issue_number, main


def test_closes_wins_over_earlier_contextual_refs():
    # Refs #1 is context; Closes #2 is the real linked issue.
    assert extract_linked_issue_number("Body with Refs #1 and Closes #2.") == 2


def test_refs_only_yields_no_linked_issue():
    assert extract_linked_issue_number("Context only: Refs #1.") is None


def test_no_reference_yields_no_linked_issue():
    assert extract_linked_issue_number("No issue references here.") is None


def test_closes_preferred_over_fixes():
    # Closes wins even when Fixes appears first in the body.
    assert extract_linked_issue_number("Fixes #3, then Closes #4.") == 4


def test_fixes_used_when_closes_absent():
    assert extract_linked_issue_number("This Fixes #7 in prod.") == 7


def test_title_and_body_are_searched():
    assert extract_linked_issue_number("Title: Fixes #7\nBody: whatever") == 7


def test_main_prints_issue_number_from_argument(capsys):
    assert main(["Refs #1\nCloses #2"]) == 0
    assert capsys.readouterr().out.strip() == "2"


def test_main_prints_nothing_without_linked_issue(capsys):
    assert main(["only Refs #1"]) == 0
    assert capsys.readouterr().out.strip() == ""
