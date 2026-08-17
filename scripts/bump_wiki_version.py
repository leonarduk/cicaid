"""Rewrite the wiki's Quick-Start page install commands to a given release version.

Run by the release workflow after a GitHub Release is published, alongside
bump_readme_version.py, so the wiki never drifts out of sync with the README.

Usage: python scripts/bump_wiki_version.py v0.3.0 --repo-url https://github.com/owner/repo path/to/Quick-Start.md

The wiki is a separate git repo (``<repo>.wiki.git``) with its own ``origin``
remote pointing at the *.wiki* repo, so unlike bump_readme_version.py the repo
URL used for download links cannot be auto-detected from it and must be passed
explicitly (or via the GITHUB_REPOSITORY env var, as set by GitHub Actions).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from version_bump import bump as _bump  # noqa: E402

BLOCKS = {
    "cicaid-version": "cicaid-devtools",
    "cicaid-version-dotenv": "cicaid-devtools[dotenv]",
}


def bump(text: str, version: str, repo_url: str | None = None) -> str:
    return _bump(text, version, blocks=BLOCKS, repo_url=repo_url)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Rewrite the wiki Quick-Start page install commands to a given release version"
    )
    parser.add_argument("version", nargs="?", help="Release version tag (e.g. v0.3.0)")
    parser.add_argument(
        "path",
        nargs="?",
        default="Quick-Start.md",
        help="Path to the wiki page to update (default: Quick-Start.md in the current directory)",
    )
    parser.add_argument(
        "--repo-url",
        default=None,
        help="GitHub repo base URL (e.g. https://github.com/owner/repo). "
        "Defaults to https://github.com/$GITHUB_REPOSITORY if unset.",
    )
    args = parser.parse_args()

    if not args.version:
        print("Usage: python scripts/bump_wiki_version.py vX.Y.Z [path/to/Quick-Start.md]", file=sys.stderr)
        return 1

    repo_url = args.repo_url
    if not repo_url:
        gh_repo = os.environ.get("GITHUB_REPOSITORY")
        repo_url = f"https://github.com/{gh_repo}" if gh_repo else ""
    if not repo_url:
        print(
            "Repo URL could not be determined. Pass --repo-url or set GITHUB_REPOSITORY.",
            file=sys.stderr,
        )
        return 1

    page_path = Path(args.path)
    try:
        original = page_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(
            f"{page_path} does not exist. Create the wiki page first, "
            "then re-run this script.",
            file=sys.stderr,
        )
        return 1
    updated = bump(original, args.version, repo_url)

    if updated == original:
        print(f"{page_path.name} already up to date; nothing to change.")
        return 0

    page_path.write_text(updated, encoding="utf-8")
    print(f"Updated {page_path.name} to {args.version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
