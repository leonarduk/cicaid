#!/usr/bin/env python3
"""Validate markdown links in tracked files.

Checks two categories of links found in tracked ``*.md`` files:

* **Same-repo relative links** (e.g. ``[x](./docs/foo.md#bar)``) -- the
  target path must exist in the working tree, and any ``#anchor`` must
  match a heading in the target file.

* **Sibling-repo blob links** (e.g.
  ``https://github.com/leonarduk/cicaid/blob/main/docs/foo.md``) -- the
  path is resolved at the given ref in the sibling checkout (the
  directory next to this repo) via ``git cat-file -e <ref>:<path>``.
  A link to a path that exists only on an unmerged branch produces a
  warning; a link to a path that does not exist at the stated ref is
  an error.

External ``http(s)`` links are out of scope for v1 (network-dependent,
rate-limited, flaky in CI).

Exit status: 0 if no errors, 1 if any errors were found.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# [text](url) or [text](url "title")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

# https://github.com/leonarduk/<repo>/blob/<ref>/<path>
_GITHUB_BLOB_RE = re.compile(
    r"https?://github\.com/leonarduk/([^/]+)/blob/([^/]+)/(.+)"
)

# https://github.com/leonarduk/<repo>/tree/<ref>/<path>
_GITHUB_TREE_RE = re.compile(
    r"https?://github\.com/leonarduk/([^/]+)/tree/([^/]+)/(.+)"
)


def _extract_links(text: str) -> list[tuple[int, str]]:
    """Return (line_number, url) for every markdown link in *text*."""
    links: list[tuple[int, str]] = []
    for line_num, line in enumerate(text.splitlines(), start=1):
        for m in _MD_LINK_RE.finditer(line):
            links.append((line_num, m.group(2)))
    return links


def _heading_anchors(text: str) -> set[str]:
    """Set of GitHub-style anchor slugs for every heading in *text*."""
    anchors: set[str] = set()
    for line in text.splitlines():
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            slug = re.sub(r"[^\w\s-]", "", heading.lower()).replace(" ", "-")
            anchors.add(slug)
    return anchors


def _check_relative(url: str, repo_root: Path) -> str | None:
    """Validate a same-repo relative link. Return an error string or None."""
    path_part, _, anchor = url.partition("#")
    if not path_part:
        return None  # pure in-page anchor; skip for v1

    target = (repo_root / path_part).resolve()
    if not target.is_file():
        return f"relative path '{path_part}' does not exist"

    if anchor:
        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return f"cannot read '{path_part}' to check anchor"
        if anchor.lower().replace(" ", "-") not in _heading_anchors(content):
            return f"anchor '#{anchor}' not found in '{path_part}'"
    return None


def _git_path_exists(repo_dir: Path, ref: str, path: str) -> bool:
    """True if *path* exists at *ref* in the git repo at *repo_dir*."""
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}:{path}"],
        cwd=repo_dir,
        capture_output=True,
    )
    return result.returncode == 0


def _check_sibling(url: str, repo_root: Path) -> tuple[str | None, str | None]:
    """Validate a github.com/leonarduk/<repo>/blob|tree/<ref>/<path> link.

    Returns ``(error, warning)``; either may be None.
    """
    m = _GITHUB_BLOB_RE.match(url) or _GITHUB_TREE_RE.match(url)
    if not m:
        return None, None
    sibling_repo, ref, path = m.groups()

    sibling_dir = repo_root.parent / sibling_repo
    if not (sibling_dir / ".git").exists():
        return None, None  # no local checkout; API check out of scope for v1

    exists_at_ref = _git_path_exists(sibling_dir, ref, path)
    exists_at_main = _git_path_exists(sibling_dir, "main", path)

    if not exists_at_ref:
        hint = ""
        if exists_at_main:
            hint = f" (exists on 'main' but not on '{ref}')"
        else:
            branch_result = subprocess.run(
                ["git", "branch", "--list"],
                cwd=sibling_dir,
                capture_output=True,
                text=True,
            )
            for branch in (b.strip() for b in branch_result.stdout.splitlines()):
                if branch and branch != ref and _git_path_exists(sibling_dir, branch, path):
                    hint = f" (exists on branch '{branch}')"
                    break
        return f"path '{path}' does not exist at ref '{ref}' in {sibling_repo}{hint}", None

    if ref != "main" and not exists_at_main:
        return None, (
            f"path '{path}' exists on '{ref}' but not on 'main' in {sibling_repo} "
            f"(unmerged branch? consider linking the PR URL instead)"
        )

    return None, None


def check_links(repo_root: Path) -> int:
    """Check all tracked ``*.md`` files. Return 0 (clean) or 1 (errors)."""
    result = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("error: git ls-files failed (not a git repo?)", file=sys.stderr)
        return 1

    files = [f for f in result.stdout.splitlines() if f.strip()]
    errors = 0

    for rel in files:
        full = repo_root / rel
        if not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for line_num, url in _extract_links(text):
            if url.startswith(("http://", "https://")):
                if _GITHUB_BLOB_RE.match(url) or _GITHUB_TREE_RE.match(url):
                    err, warn = _check_sibling(url, repo_root)
                    if err:
                        print(f"{rel}:{line_num}: ERROR: {err}", file=sys.stderr)
                        errors += 1
                    if warn:
                        print(f"{rel}:{line_num}: WARNING: {warn}", file=sys.stderr)
                continue  # all other external links: out of scope

            if url.startswith(("mailto:", "#", "data:")):
                continue

            err = _check_relative(url, repo_root)
            if err:
                print(f"{rel}:{line_num}: ERROR: {err}", file=sys.stderr)
                errors += 1

    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    """Provide the ``cicaid check-links`` entry point."""
    parser = argparse.ArgumentParser(
        description="Validate markdown links in tracked files.",
        epilog=(
            "Checks same-repo relative links and sibling-repo blob/tree links. "
            "External http(s) links are skipped. No flags required."
        ),
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repo root (default: auto-detect via git)",
    )
    args = parser.parse_args(argv)

    if args.root:
        root = args.root
    else:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print("error: not inside a git repository", file=sys.stderr)
            return 1
        root = Path(r.stdout.strip())

    return check_links(root)


if __name__ == "__main__":
    raise SystemExit(main())
