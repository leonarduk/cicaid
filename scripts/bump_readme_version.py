"""Rewrite README.md's pinned install commands to a given release version.

Run by the release workflow after a GitHub Release is published, so the README
always shows the version that was just released instead of going stale.

Usage: python scripts/bump_readme_version.py v0.3.0

The release download URL is auto-detected from the ``origin`` git remote.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from version_bump import bump as _bump  # noqa: E402
from version_bump import detect_repo_url  # noqa: E402

README_PATH = Path(__file__).resolve().parent.parent / "README.md"

BLOCKS = {
    "cicaid-version": "cicaid-devtools",
    "cicaid-version-dotenv": "cicaid-devtools[dotenv]",
}

# Markers whose content is just the bare tag (e.g. the "latest release" example
# in the Releasing section), not a pip install command.
TAG_ONLY_BLOCKS = ("cicaid-latest-tag",)


def bump(text: str, version: str, repo_url: str | None = None) -> str:
    return _bump(text, version, blocks=BLOCKS, tag_only_blocks=TAG_ONLY_BLOCKS, repo_url=repo_url)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Rewrite README.md install commands to a given release version"
    )
    parser.add_argument("version", nargs="?", help="Release version tag (e.g. v0.3.0)")
    parser.add_argument(
        "--repo-url",
        default=None,
        help="GitHub repo base URL (e.g. https://github.com/owner/repo). "
        "Auto-detected from git remote if omitted.",
    )
    args = parser.parse_args()

    if not args.version:
        print("Usage: python scripts/bump_readme_version.py vX.Y.Z", file=sys.stderr)
        return 1

    repo_url = args.repo_url or detect_repo_url()

    original = README_PATH.read_text(encoding="utf-8")
    updated = bump(original, args.version, repo_url)

    if updated == original:
        print("README.md already up to date; nothing to change.")
        return 0

    README_PATH.write_text(updated, encoding="utf-8")
    print(f"Updated README.md to {args.version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
