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
import time

import requests

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

MAX_RATE_LIMIT_RETRIES = 4
_INITIAL_BACKOFF_SECONDS = 1
_MAX_RETRY_AFTER_SECONDS = 120


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


def _rate_limit_delay(resp: requests.Response, attempt: int) -> float | None:
    """Return the backoff delay for a rate-limited response, or None if it
    isn't one (403 without a fully-exhausted rate limit, anything else)."""
    if resp.status_code == 429 or (
        resp.status_code == 403 and resp.headers.get("X-RateLimit-Remaining") == "0"
    ):
        retry_after = resp.headers.get("Retry-After")
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except ValueError:
                delay = None
            if delay is not None and delay >= 0:
                return min(delay, _MAX_RETRY_AFTER_SECONDS)
        return _INITIAL_BACKOFF_SECONDS * (2**attempt)
    return None


def create_issue_via_api(
    owner: str,
    repo: str,
    title: str,
    body: str,
    labels: list[str],
    token: str,
) -> str | None:
    """Create a GitHub issue via the REST API.  Returns the HTML URL on success.

    Retries with exponential backoff on a rate-limited response (HTTP 429, or
    403 with ``X-RateLimit-Remaining: 0``), honoring ``Retry-After`` when
    present. Any other failure (including a 403 that isn't a rate limit,
    e.g. a permissions error) is not retried.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }
    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
        except requests.RequestException as exc:
            logger.error("API request failed: %s", exc)
            return None

        delay = _rate_limit_delay(resp, attempt)
        if delay is not None and attempt < MAX_RATE_LIMIT_RETRIES:
            logger.warning(
                "GitHub API rate limit hit (status %d); retrying in %.1fs (attempt %d/%d)",
                resp.status_code,
                delay,
                attempt + 1,
                MAX_RATE_LIMIT_RETRIES,
            )
            time.sleep(delay)
            continue

        try:
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("API request failed: %s", exc)
            return None
        return resp.json().get("html_url")

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
