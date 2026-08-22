"""Shared logic for rewriting pinned install commands to a given release version.

Used by both ``bump_readme_version.py`` (README.md in this repo) and
``bump_wiki_version.py`` (the Quick-Start page on the wiki) so the two stay in
sync — see release.yml, which runs both after a GitHub Release is published.
"""

from __future__ import annotations

import re
import subprocess
import sys


def detect_repo_url() -> str:
    """Auto-detect the GitHub repo base URL from the origin git remote.

    Returns something like ``https://github.com/owner/repo``.
    """
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        print(
            "WARNING: Could not determine repo URL from git remote. "
            "Pass --repo-url explicitly.",
            file=sys.stderr,
        )
        return ""

    remote = result.stdout.strip()
    # Convert SSH-style git@github.com:owner/repo.git → https://github.com/owner/repo
    match = re.match(r"git@github\.com:([^/]+/[^/]+?)(?:\.git)?$", remote)
    if match:
        return f"https://github.com/{match.group(1)}"
    # ssh://git@github.com/owner/repo.git and git://github.com/owner/repo.git
    match = re.match(r"(?:ssh|git)://(?:[^@]+@)?github\.com/([^/]+/[^/]+?)(?:\.git)?$", remote)
    if match:
        return f"https://github.com/{match.group(1)}"
    # Keep HTTPS-style as-is (strip trailing .git)
    match = re.match(r"(https://github\.com/[^/]+/[^/]+?)(?:\.git)?$", remote)
    if match:
        return match.group(1)
    print(
        f"WARNING: Could not parse GitHub URL from remote '{remote}'.",
        file=sys.stderr,
    )
    return ""


def render_block(package_spec: str, version: str, version_num: str, repo_url: str | None = None) -> str:
    if repo_url is None:
        repo_url = detect_repo_url()
    if not repo_url:
        raise ValueError(
            "Repo URL is empty. Pass --repo-url or run inside a GitHub repo clone."
        )
    url = (
        f"{repo_url}/releases/download/"
        f"{version}/cicaid_devtools-{version_num}-py3-none-any.whl"
    )
    return f'```bash\npip install "{package_spec} @ {url}"\n```'


def bump(
    text: str,
    version: str,
    *,
    blocks: dict[str, str],
    tag_only_blocks: tuple[str, ...] = (),
    repo_url: str | None = None,
) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", version):
        raise ValueError(f"expected a vX.Y.Z tag, got {version!r}")
    version_num = version[1:]

    for marker, package_spec in blocks.items():
        pattern = re.compile(
            rf"(<!-- {re.escape(marker)}:start -->\n).*?(\n<!-- {re.escape(marker)}:end -->)",
            re.DOTALL,
        )
        if not pattern.search(text):
            raise ValueError(f"marker {marker!r} not found")
        replacement = render_block(package_spec, version, version_num, repo_url)
        text = pattern.sub(lambda m: m.group(1) + replacement + m.group(2), text)

    for marker in tag_only_blocks:
        pattern = re.compile(rf"(<!-- {re.escape(marker)}:start -->).*?(<!-- {re.escape(marker)}:end -->)")
        if not pattern.search(text):
            raise ValueError(f"marker {marker!r} not found")
        replacement = f"`{version}`"
        text = pattern.sub(lambda m: m.group(1) + replacement + m.group(2), text)
    return text
