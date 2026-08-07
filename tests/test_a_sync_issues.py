from cicaid_devtools.a_sync_issues import format_issue_file, make_filename, slugify


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Fix the Thing That Broke!") == "fix-the-thing-that-broke"


def test_slugify_strips_leading_trailing_hyphens():
    assert slugify("  --Weird Title--  ") == "weird-title"


def test_slugify_truncates_to_60_chars():
    long_title = "x" * 100
    assert len(slugify(long_title)) == 60


def test_make_filename_combines_id_and_slug():
    assert make_filename(42, "Add logging") == "42_add-logging.md"


def test_format_issue_file_includes_header_fields():
    issue = {
        "number": 7,
        "title": "Something broke",
        "html_url": "https://github.com/leonarduk/cicaid/issues/7",
        "labels": [{"name": "bug"}, {"name": "P1"}],
        "state": "open",
        "body": "Steps to reproduce...",
    }
    content = format_issue_file(issue)
    assert "# 7 — Something broke" in content
    assert "**URL:** https://github.com/leonarduk/cicaid/issues/7" in content
    assert "**Labels:** bug, P1" in content
    assert "**State:** open" in content
    assert "Steps to reproduce..." in content


def test_format_issue_file_handles_null_body():
    issue = {
        "number": 8,
        "title": "No body",
        "html_url": "https://example.com",
        "labels": [],
        "state": "open",
        "body": None,
    }
    content = format_issue_file(issue)
    assert "# 8 — No body" in content
