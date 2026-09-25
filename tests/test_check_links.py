"""Tests for cicaid_devtools.check_links."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cicaid_devtools import check_links


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=path, capture_output=True)


def _commit(path: Path, msg: str = "init") -> None:
    subprocess.run(["git", "add", "-A"], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=path, capture_output=True)


def _make_repo(parent: Path, name: str, files: dict[str, str]) -> Path:
    repo = parent / name
    repo.mkdir(parents=True, exist_ok=True)
    _init_repo(repo)
    for rel, content in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    _commit(repo)
    return repo


# --- same-repo relative links ---


def test_relative_link_to_missing_path(tmp_path, capsys):
    repo = _make_repo(tmp_path, "myrepo", {"README.md": "[broken](./docs/missing.md)\n"})
    assert check_links.check_links(repo) == 1
    err = capsys.readouterr().err
    assert "README.md:1" in err
    assert "does not exist" in err


def test_relative_link_to_existing_path(tmp_path, capsys):
    repo = _make_repo(
        tmp_path,
        "myrepo",
        {"README.md": "[guide](./docs/guide.md)\n", "docs/guide.md": "# Guide\n"},
    )
    assert check_links.check_links(repo) == 0
    assert capsys.readouterr().err == ""


def test_relative_link_missing_anchor(tmp_path, capsys):
    repo = _make_repo(
        tmp_path,
        "myrepo",
        {
            "README.md": "[section](./docs/guide.md#nonexistent)\n",
            "docs/guide.md": "# Guide\n\nSome text.\n",
        },
    )
    assert check_links.check_links(repo) == 1
    assert "anchor" in capsys.readouterr().err


def test_relative_link_valid_anchor(tmp_path, capsys):
    repo = _make_repo(
        tmp_path,
        "myrepo",
        {
            "README.md": "[install](./docs/guide.md#installation)\n",
            "docs/guide.md": "# Guide\n\n## Installation\n\nSteps.\n",
        },
    )
    assert check_links.check_links(repo) == 0
    assert capsys.readouterr().err == ""


def test_multiple_errors_all_reported(tmp_path, capsys):
    repo = _make_repo(
        tmp_path,
        "myrepo",
        {"README.md": "[a](./missing1.md)\n[b](./missing2.md)\n"},
    )
    assert check_links.check_links(repo) == 1
    err = capsys.readouterr().err
    assert "missing1.md" in err
    assert "missing2.md" in err


# --- sibling-repo blob links ---


def test_sibling_repo_link_missing_at_ref(tmp_path, capsys):
    parent = tmp_path / "repos"
    parent.mkdir()
    repo = _make_repo(
        parent,
        "myrepo",
        {"README.md": "[sib](https://github.com/leonarduk/sibling/blob/main/docs/missing.md)\n"},
    )
    _make_repo(parent, "sibling", {"README.md": "# Sibling\n"})

    assert check_links.check_links(repo) == 1
    err = capsys.readouterr().err
    assert "sibling" in err
    assert "does not exist" in err


def test_sibling_repo_link_exists_at_ref(tmp_path, capsys):
    parent = tmp_path / "repos"
    parent.mkdir()
    repo = _make_repo(
        parent,
        "myrepo",
        {"README.md": "[sib](https://github.com/leonarduk/sibling/blob/main/docs/guide.md)\n"},
    )
    _make_repo(parent, "sibling", {"docs/guide.md": "# Guide\n"})

    assert check_links.check_links(repo) == 0
    assert capsys.readouterr().err == ""


def test_sibling_repo_link_unmerged_branch_warning(tmp_path, capsys):
    parent = tmp_path / "repos"
    parent.mkdir()
    repo = _make_repo(
        parent,
        "myrepo",
        {"README.md": "[sib](https://github.com/leonarduk/sibling/blob/feature/docs/new.md)\n"},
    )
    sibling = _make_repo(parent, "sibling", {"README.md": "# Sibling\n"})
    # Add file on a feature branch
    (sibling / "docs").mkdir(exist_ok=True)
    (sibling / "docs" / "new.md").write_text("# New\n", encoding="utf-8")
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=sibling, capture_output=True)
    _commit(sibling, "add new doc")
    subprocess.run(["git", "checkout", "main"], cwd=sibling, capture_output=True)

    assert check_links.check_links(repo) == 0  # warning only, not error
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "unmerged" in err


def test_sibling_repo_no_local_checkout_skipped(tmp_path, capsys):
    """If the sibling repo isn't checked out locally, the link is skipped."""
    repo = _make_repo(
        tmp_path,
        "myrepo",
        {"README.md": "[sib](https://github.com/leonarduk/other/blob/main/x.md)\n"},
    )
    assert check_links.check_links(repo) == 0
    assert capsys.readouterr().err == ""


# --- external / non-file links ---


def test_external_links_are_skipped(tmp_path, capsys):
    repo = _make_repo(
        tmp_path,
        "myrepo",
        {
            "README.md": (
                "[ext](https://example.com/page)\n"
                "[mail](mailto:foo@bar.com)\n"
                "[anchor](#section)\n"
            )
        },
    )
    assert check_links.check_links(repo) == 0
    assert capsys.readouterr().err == ""


# --- extract_links unit tests ---


def test_extract_links_finds_all():
    text = "[a](./x.md)\nplain line\n[b](https://github.com/leonarduk/r/blob/main/y.md)\n"
    links = check_links._extract_links(text)
    assert links == [(1, "./x.md"), (3, "https://github.com/leonarduk/r/blob/main/y.md")]


def test_extract_links_with_title():
    text = '[a](./x.md "My Title")\n'
    links = check_links._extract_links(text)
    assert links == [(1, "./x.md")]
