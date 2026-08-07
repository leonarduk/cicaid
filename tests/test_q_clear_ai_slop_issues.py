import subprocess
from unittest.mock import patch

import pytest

from cicaid_devtools.q_clear_ai_slop_issues import (
    CloseCandidate,
    GhIssue,
    _closing_comment,
    _deduplicate_candidates,
    _find_already_closed,
    _find_approve_artifacts,
    _find_duplicates,
    _find_superseded,
    _jaccard,
    _normalise_title,
    _parse_llm_response,
    _resolve_repo,
    _title_looks_like_approve,
)


def issue(number, title, body="", state="open", url=""):
    return GhIssue(number=number, title=title, body=body, state=state, url=url or f"#{number}")


# --------------------------------------------------------------------- _jaccard


def test_jaccard_identical_sets():
    assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0


def test_jaccard_disjoint_sets():
    assert _jaccard({"a"}, {"b"}) == 0.0


def test_jaccard_both_empty():
    assert _jaccard(set(), set()) == 1.0


def test_jaccard_one_empty():
    assert _jaccard(set(), {"a"}) == 0.0


def test_jaccard_partial_overlap():
    assert _jaccard({"a", "b"}, {"b", "c"}) == pytest.approx(1 / 3)


# --------------------------------------------------------------- _normalise_title


def test_normalise_title_strips_noise_prefix():
    assert _normalise_title("Add tests for the widget") == "tests for the widget"


def test_normalise_title_strips_markdown():
    # "fix " is itself a _NOISE_PREFIXES entry, so it's stripped along with the
    # markdown -- that's intentional (it's what makes "Fix X" and "X" match).
    assert _normalise_title("**Fix** the `widget`") == "the widget"


def test_normalise_title_lowercases_and_collapses_whitespace():
    assert _normalise_title("Reword   THE    Widget") == "reword the widget"


# ------------------------------------------------------------ approval detection


@pytest.mark.parametrize(
    "title",
    ["APPROVE", "Approved", "LGTM", "Looks good to me", "Ship it", ":+1: nice work"],
)
def test_title_looks_like_approve_true(title):
    assert _title_looks_like_approve(title) is True


def test_title_looks_like_approve_false_for_normal_title():
    assert _title_looks_like_approve("Add caching to the market data client") is False


# --------------------------------------------------------------------- _find_*


def test_find_duplicates_clusters_similar_titles():
    issues = [
        issue(1, "Add tests for the widget parser"),
        issue(2, "Consider adding tests for the widget parser"),
        issue(3, "Completely unrelated issue about deployment"),
    ]
    candidates = _find_duplicates(issues, threshold=0.65)
    assert len(candidates) == 1
    assert candidates[0].issue.number == 2
    assert "Duplicate of #1" in candidates[0].evidence


def test_find_duplicates_none_below_threshold():
    issues = [issue(1, "Add tests for widgets"), issue(2, "Fix the deployment pipeline")]
    assert _find_duplicates(issues) == []


def test_find_duplicates_needs_at_least_two_issues():
    assert _find_duplicates([issue(1, "Solo issue")]) == []


def test_find_already_closed_exact_match():
    open_issues = [issue(5, "Add tests for the parser")]
    closed_issues = [issue(2, "Add tests for the parser")]
    candidates = _find_already_closed(open_issues, closed_issues)
    assert len(candidates) == 1
    assert candidates[0].issue.number == 5
    assert "#2" in candidates[0].evidence


def test_find_already_closed_no_closed_issues_returns_empty():
    assert _find_already_closed([issue(1, "Anything")], []) == []


def test_find_approve_artifacts_detects_title_and_body():
    issues = [
        issue(1, "APPROVE", body=""),
        issue(2, "A normal title", body="LGTM, ship it"),
        issue(3, "A real feature request", body="We should add X because Y."),
    ]
    candidates = _find_approve_artifacts(issues)
    numbers = {c.issue.number for c in candidates}
    assert numbers == {1, 2}


def test_find_superseded_detects_reference_to_newer_open_issue():
    issues = [
        issue(1, "Old issue", body="This is superseded by #2"),
        issue(2, "New issue"),
    ]
    candidates = _find_superseded(issues)
    assert len(candidates) == 1
    assert candidates[0].issue.number == 1
    assert "#2" in candidates[0].evidence


def test_find_superseded_ignores_reference_to_closed_or_missing_issue():
    issues = [issue(1, "Old issue", body="This is superseded by #999")]
    assert _find_superseded(issues) == []


# ---------------------------------------------------------------- dedup / comment


def test_deduplicate_candidates_keeps_first_occurrence():
    dup_issue = issue(1, "Dup")
    candidates = [
        CloseCandidate(issue=dup_issue, reason="duplicate", evidence="first"),
        CloseCandidate(issue=dup_issue, reason="approve-artifact", evidence="second"),
    ]
    result = _deduplicate_candidates(candidates)
    assert len(result) == 1
    assert result[0].evidence == "first"


def test_closing_comment_mentions_script_name():
    candidate = CloseCandidate(issue=issue(1, "x"), reason="duplicate", evidence="Duplicate of #2")
    comment = _closing_comment(candidate)
    assert "q_clear_ai_slop_issues.py" in comment
    assert "Duplicate of #2" in comment


# ------------------------------------------------------------------ LLM response


def test_parse_llm_response_valid_json():
    open_issues = [issue(1, "First"), issue(2, "Second")]
    response = '[{"number": 1, "reason": "duplicate", "evidence": "dupe of #2"}]'
    candidates = _parse_llm_response(response, open_issues)
    assert len(candidates) == 1
    assert candidates[0].issue.number == 1
    assert candidates[0].reason == "duplicate"


def test_parse_llm_response_ignores_unknown_issue_numbers():
    open_issues = [issue(1, "First")]
    response = '[{"number": 999, "reason": "duplicate", "evidence": "x"}]'
    assert _parse_llm_response(response, open_issues) == []


def test_parse_llm_response_tolerates_surrounding_text():
    open_issues = [issue(1, "First")]
    response = 'Here is my answer:\n[{"number": 1, "reason": "superseded", "evidence": "x"}]\nDone.'
    candidates = _parse_llm_response(response, open_issues)
    assert len(candidates) == 1


def test_parse_llm_response_no_json_array_returns_empty():
    assert _parse_llm_response("no json here", [issue(1, "x")]) == []


def test_parse_llm_response_unknown_reason_normalised():
    open_issues = [issue(1, "First")]
    response = '[{"number": 1, "reason": "made-up-reason", "evidence": "x"}]'
    candidates = _parse_llm_response(response, open_issues)
    assert candidates[0].reason == "unknown"


# ------------------------------------------------------------------- _resolve_repo


def test_resolve_repo_explicit_owner_name():
    assert _resolve_repo("someowner/somerepo") == ("someowner", "somerepo")


def test_resolve_repo_explicit_invalid_form_exits():
    with pytest.raises(SystemExit):
        _resolve_repo("not-a-valid-repo-spec")


def test_resolve_repo_falls_back_to_git_remote():
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="git@github.com:leonarduk/cicaid.git\n", stderr=""
    )
    with patch("subprocess.run", return_value=completed):
        assert _resolve_repo(None) == ("leonarduk", "cicaid")
