from cicaid_devtools.review_issue import (
    FALLBACK_TEMPLATE_SECTIONS,
    apply_known_file_paths,
    files_affected_is_unresolved,
    load_template_sections,
    looks_like_content_loss,
    missing_sections,
    strip_files_affected_section,
)


def test_missing_sections_finds_absent_headings():
    body = "## What\nSome text\n\n## Why\nMore text\n"
    assert missing_sections(body, ["What", "Why", "How"]) == ["How"]


def test_missing_sections_tolerates_deeper_heading_levels():
    body = "### Why\nText here\n"
    assert missing_sections(body, ["Why"]) == []


def test_missing_sections_all_present_returns_empty():
    body = "## A\n\n## B\n"
    assert missing_sections(body, ["A", "B"]) == []


def test_strip_files_affected_section_removes_it():
    body = "## Why\nBecause.\n\n## Files Affected\n- foo.py\n\n## How\nDo it.\n"
    stripped = strip_files_affected_section(body)
    assert "Files Affected" not in stripped
    assert "## Why" in stripped
    assert "## How" in stripped


def test_strip_files_affected_section_noop_when_absent():
    body = "## Why\nBecause.\n"
    assert strip_files_affected_section(body) == body


def test_apply_known_file_paths_replaces_existing_section():
    body = "## Files Affected\nsome guess.py\n\n## How\nDo it.\n"
    result = apply_known_file_paths(body, {"foo.py": ["src/foo.py"]})
    assert "src/foo.py" in result
    assert "some guess.py" not in result


def test_apply_known_file_paths_writes_unknown_when_no_hints():
    body = "## Files Affected\nUnknown\n\n## How\nDo it.\n"
    result = apply_known_file_paths(body, {})
    assert "Unknown" in result


def test_apply_known_file_paths_inserts_missing_section():
    body = "## How\nDo it.\n"
    result = apply_known_file_paths(
        body, {"foo.py": ["src/foo.py"]}, sections=["How", "Files Affected", "Constraints"]
    )
    assert "## Files Affected" in result
    assert "src/foo.py" in result


def test_looks_like_content_loss_true_for_much_shorter_revision():
    original = "x" * 100
    revised = "x" * 10
    assert looks_like_content_loss(original, revised) is True


def test_looks_like_content_loss_false_for_similar_length():
    original = "x" * 100
    revised = "x" * 90
    assert looks_like_content_loss(original, revised) is False


def test_looks_like_content_loss_false_for_empty_original():
    assert looks_like_content_loss("", "anything") is False


def test_files_affected_is_unresolved_true_when_unknown():
    body = "## Files Affected\nUnknown\n\n## How\nDo it.\n"
    assert files_affected_is_unresolved(body) is True


def test_files_affected_is_unresolved_false_when_resolved():
    body = "## Files Affected\n- src/foo.py\n\n## How\nDo it.\n"
    assert files_affected_is_unresolved(body) is False


def test_files_affected_is_unresolved_true_when_section_missing():
    body = "## How\nDo it.\n"
    assert files_affected_is_unresolved(body) is True


def test_load_template_sections_falls_back_when_no_template_in_repo():
    # cicaid's own repo has no .github/ISSUE_TEMPLATE/bug_report.md, so this
    # exercises the real fallback path (lazy resolution via get_repo_root()).
    assert load_template_sections() == FALLBACK_TEMPLATE_SECTIONS


def test_load_template_sections_falls_back_for_missing_explicit_path(tmp_path):
    assert load_template_sections(tmp_path / "does-not-exist.md") == FALLBACK_TEMPLATE_SECTIONS


def test_load_template_sections_parses_explicit_template(tmp_path):
    template = tmp_path / "bug_report.md"
    template.write_text("## What\n...\n## Why\n...\n", encoding="utf-8")
    assert load_template_sections(template) == ["What", "Why"]
