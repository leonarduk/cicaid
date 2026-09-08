from pathlib import Path

from cicaid_devtools.repo_privacy import (
    MARKER_FILE,
    to_private,
    to_public,
)


def _write_workflow(root: Path, name: str, content: str) -> Path:
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    path = workflows / name
    path.write_text(content, encoding="utf-8")
    return path


def test_to_private_converts_ubuntu_latest(tmp_path):
    path = _write_workflow(
        tmp_path,
        "ci.yml",
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps: []\n",
    )
    report = to_private(tmp_path, dry_run=False)
    assert ".github/workflows/ci.yml" in report.workflows_converted
    text = path.read_text(encoding="utf-8")
    assert "    # runs-on: ubuntu-latest\n" in text
    assert "    runs-on: [self-hosted, linux, x64]\n" in text


def test_to_private_converts_windows_latest(tmp_path):
    path = _write_workflow(
        tmp_path,
        "build.yml",
        "jobs:\n  build:\n    runs-on: windows-latest\n    steps: []\n",
    )
    to_private(tmp_path, dry_run=False)
    text = path.read_text(encoding="utf-8")
    assert "    # runs-on: windows-latest\n" in text
    assert "    runs-on: [self-hosted, windows, x64]\n" in text


def test_to_private_is_idempotent(tmp_path):
    path = _write_workflow(
        tmp_path,
        "ci.yml",
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps: []\n",
    )
    to_private(tmp_path, dry_run=False)
    first = path.read_text(encoding="utf-8")
    report_second = to_private(tmp_path, dry_run=False)
    second = path.read_text(encoding="utf-8")
    assert first == second
    assert report_second.workflows_converted == []


def test_to_private_removes_codeql_and_dependency_review(tmp_path):
    _write_workflow(tmp_path, "codeql.yml", "name: CodeQL\n")
    _write_workflow(tmp_path, "dependency-review.yml", "name: Dependency Review\n")
    report = to_private(tmp_path, dry_run=False)
    assert sorted(report.workflows_removed) == [
        ".github/workflows/codeql.yml",
        ".github/workflows/dependency-review.yml",
    ]
    assert not (tmp_path / ".github/workflows/codeql.yml").exists()
    assert not (tmp_path / ".github/workflows/dependency-review.yml").exists()


def test_to_private_removal_is_noop_when_absent(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    report = to_private(tmp_path, dry_run=False)
    assert report.workflows_removed == []


def test_to_private_adds_marker_file(tmp_path):
    report = to_private(tmp_path, dry_run=False)
    assert report.marker_added is True
    assert (tmp_path / MARKER_FILE).exists()


def test_to_private_marker_not_duplicated(tmp_path):
    (tmp_path / MARKER_FILE).write_text("", encoding="utf-8")
    report = to_private(tmp_path, dry_run=False)
    assert report.marker_added is False


def test_to_private_dry_run_does_not_write(tmp_path):
    path = _write_workflow(
        tmp_path,
        "ci.yml",
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps: []\n",
    )
    original = path.read_text(encoding="utf-8")
    report = to_private(tmp_path, dry_run=True)
    assert path.read_text(encoding="utf-8") == original
    assert ".github/workflows/ci.yml" in report.workflows_converted
    assert not (tmp_path / MARKER_FILE).exists()


def test_to_public_restores_original_runs_on(tmp_path):
    path = _write_workflow(
        tmp_path,
        "ci.yml",
        "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps: []\n",
    )
    to_private(tmp_path, dry_run=False)
    report = to_public(tmp_path, dry_run=False)
    text = path.read_text(encoding="utf-8")
    assert text == "jobs:\n  build:\n    runs-on: ubuntu-latest\n    steps: []\n"
    assert ".github/workflows/ci.yml" in report.workflows_reverted
    assert report.workflows_flagged == []


def test_to_public_flags_self_hosted_without_comment(tmp_path):
    _write_workflow(
        tmp_path,
        "ci.yml",
        "jobs:\n  build:\n    runs-on: [self-hosted, linux, x64]\n    steps: []\n",
    )
    report = to_public(tmp_path, dry_run=False)
    assert ".github/workflows/ci.yml" in report.workflows_flagged
    assert report.workflows_reverted == []


def test_to_public_restores_codeql_and_dependency_review(tmp_path):
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    report = to_public(tmp_path, dry_run=False)
    assert sorted(report.workflows_restored) == [
        ".github/workflows/codeql.yml",
        ".github/workflows/dependency-review.yml",
    ]
    assert "CodeQL" in (tmp_path / ".github/workflows/codeql.yml").read_text(encoding="utf-8")
    assert "Dependency Review" in (tmp_path / ".github/workflows/dependency-review.yml").read_text(
        encoding="utf-8"
    )


def test_to_public_does_not_clobber_existing_workflows(tmp_path):
    path = _write_workflow(tmp_path, "codeql.yml", "custom content\n")
    to_public(tmp_path, dry_run=False)
    assert path.read_text(encoding="utf-8") == "custom content\n"


def test_to_public_removes_marker_file(tmp_path):
    (tmp_path / MARKER_FILE).write_text("", encoding="utf-8")
    report = to_public(tmp_path, dry_run=False)
    assert report.marker_removed is True
    assert not (tmp_path / MARKER_FILE).exists()


def test_to_public_marker_removal_is_noop_when_absent(tmp_path):
    report = to_public(tmp_path, dry_run=False)
    assert report.marker_removed is False


def test_to_public_dry_run_does_not_write(tmp_path):
    path = _write_workflow(
        tmp_path,
        "ci.yml",
        "jobs:\n  build:\n    # runs-on: ubuntu-latest\n    runs-on: [self-hosted, linux, x64]\n"
        "    steps: []\n",
    )
    original = path.read_text(encoding="utf-8")
    (tmp_path / MARKER_FILE).write_text("", encoding="utf-8")
    to_public(tmp_path, dry_run=True)
    assert path.read_text(encoding="utf-8") == original
    assert (tmp_path / MARKER_FILE).exists()
    assert not (tmp_path / ".github/workflows/codeql.yml").exists()
