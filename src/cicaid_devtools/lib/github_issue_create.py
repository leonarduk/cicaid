"""GitHub-plumbing helpers for creating an issue: auth token resolution and
the API/gh-CLI creation calls themselves.

Split out of create_issue.py so callers that only need to *create* an issue
(setup_review_actions.py's scaffolding) don't have to pull in that module's
interactive LLM-assisted drafting flow (llm_common/issue_review) — this
module has no LLM dependency at all.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile

import requests

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def get_github_token() -> str:
    """Get GitHub token from GITHUB_TOKEN env var or ``gh auth token``."""
    token = os.getenv("GITHUB_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    logger.error("GITHUB_TOKEN env var not set and 'gh auth token' failed.")
    sys.exit(1)


def create_issue_via_api(
    owner: str,
    repo: str,
    title: str,
    body: str,
    labels: list[str],
    token: str,
) -> str | None:
    """Create a GitHub issue via the REST API.  Returns the HTML URL on success."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }
    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("html_url")
    except requests.RequestException as exc:
        logger.error("API request failed: %s", exc)
        return None


def create_issue_via_gh(
    owner: str,
    repo: str,
    title: str,
    body: str,
    labels: list[str],
) -> str | None:
    """Create a GitHub issue via the ``gh`` CLI.  Returns the URL on success."""
    # Write body to a temp file so the CLI can read it safely on all platforms.
    body_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            encoding="utf-8",
            delete=False,
        ) as tf:
            tf.write(body)
            body_path = tf.name

        cmd = [
            "gh",
            "issue",
            "create",
            "--repo",
            f"{owner}/{repo}",
            "--title",
            title,
            "--body-file",
            body_path,
        ]
        for label in labels:
            cmd.extend(["--label", label])

        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)

        if result.returncode != 0:
            logger.error("gh CLI error: %s", result.stderr)
            return None

        url = result.stdout.strip()
        return url if url else None
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("gh CLI error: %s", exc)
        return None
    finally:
        if body_path and os.path.exists(body_path):
            os.unlink(body_path)
