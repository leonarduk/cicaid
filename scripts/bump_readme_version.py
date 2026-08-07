"""Rewrite README.md's pinned install commands to a given release version.

Run by the release workflow after a GitHub Release is published, so the README
always shows the version that was just released instead of going stale (see
allotmint-mcp README review, 2026-08-07 -- the README still pointed at v0.1.0
after two later releases because nobody remembered to hand-edit it).

Usage: python scripts/bump_readme_version.py v0.3.0
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

README_PATH = Path(__file__).resolve().parent.parent / "README.md"

BLOCKS = {
    "cicaid-version": "cicaid-devtools",
    "cicaid-version-dotenv": "cicaid-devtools[dotenv]",
}


def render_block(package_spec: str, version: str, version_num: str) -> str:
    url = (
        f"https://github.com/leonarduk/cicaid/releases/download/"
        f"{version}/cicaid_devtools-{version_num}-py3-none-any.whl"
    )
    return f'```bash\npip install "{package_spec} @ {url}"\n```'


def bump(text: str, version: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
        raise ValueError(f"expected a vX.Y.Z tag, got {version!r}")
    version_num = version[1:]

    for marker, package_spec in BLOCKS.items():
        pattern = re.compile(
            rf"(<!-- {re.escape(marker)}:start -->\n).*?(\n<!-- {re.escape(marker)}:end -->)",
            re.DOTALL,
        )
        if not pattern.search(text):
            raise ValueError(f"marker {marker!r} not found in README.md")
        replacement = render_block(package_spec, version, version_num)
        text = pattern.sub(lambda m: m.group(1) + replacement + m.group(2), text)
    return text


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python scripts/bump_readme_version.py vX.Y.Z", file=sys.stderr)
        return 1
    version = sys.argv[1]

    original = README_PATH.read_text(encoding="utf-8")
    updated = bump(original, version)

    if updated == original:
        print("README.md already up to date; nothing to change.")
        return 0

    README_PATH.write_text(updated, encoding="utf-8")
    print(f"Updated README.md to {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
