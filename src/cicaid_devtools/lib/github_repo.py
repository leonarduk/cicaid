"""Helpers for identifying the GitHub repository in the current checkout."""

from __future__ import annotations
import logging


logger = logging.getLogger(__name__)
import re
import subprocess


def get_repo_info() -> tuple[str, str]:
    """Extract the GitHub owner and repository name from ``origin``.

    If the current checkout is a ``.wiki`` repository (e.g.
    ``leonarduk/cicaid.wiki``), the returned name is the corresponding
    non-wiki repository (e.g. ``cicaid``), because wiki repos don't have
    their own issues or pull-requests.
    """
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Could not determine GitHub repo from git remote origin: {exc}") from exc

    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", result.stdout.strip())
    if match:
        owner = match.group(1)
        repo = match.group(2)
        if repo.endswith(".wiki"):
            repo = repo[: -len(".wiki")]
        return owner, repo
    raise ValueError("Could not determine GitHub repo from git remote origin")


def get_repo_root() -> str:
    """Return the absolute path to the current git repository's root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"Could not determine repo root from git: {exc}") from exc
    return result.stdout.strip()
