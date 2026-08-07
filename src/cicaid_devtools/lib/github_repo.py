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


def get_actual_repo_name() -> str:
    """Return the repo name from git remote, keeping any ``.wiki`` suffix.

    Unlike :func:`get_repo_info`, this does *not* strip ``.wiki`` so that
    callers can target the current (possibly wiki) repository for branch
    and PR operations.
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
        raise ValueError(f"Could not determine repo from remote: {exc}") from exc

    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", result.stdout.strip())
    if match:
        return match.group(2)
    raise ValueError("Could not determine repo from git remote origin")


def is_wiki_repo() -> bool:
    """Return ``True`` when the current checkout is a ``.wiki`` repository."""
    try:
        return get_actual_repo_name().endswith(".wiki")
    except ValueError:
        return False


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
